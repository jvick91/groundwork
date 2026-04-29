"""
Shared pytest fixtures for async database testing with transaction rollback isolation.

Each test runs inside a transaction that is rolled back after the test completes,
ensuring full isolation without needing to recreate tables between tests.
"""

from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from app.core.database import Base, Database
from app.core.dependencies import get_db
from app.core.settings import settings
from app.main import create_app
from tests.fixtures import jwt_keys

TokenFactory = Callable[..., str]


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def initialize_database() -> AsyncGenerator[None, None]:
    """Initialize the production Database singleton against the test DB.

    The FastAPI lifespan does not run under ``httpx.ASGITransport``, so any
    code that touches ``Database.get_engine()`` (e.g. the readiness probe in
    ``app/routers/health.py``) would otherwise see an uninitialized engine
    and report ``"error"``. Initializing here mirrors production startup.
    """
    Database.initialize(settings.test_database_url)
    yield
    await Database.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    """Create a single async engine for the entire test session."""
    engine = create_async_engine(
        settings.test_database_url,
        pool_pre_ping=True,
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def create_tables(test_engine):
    """Create all tables once at the start of the test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test database session with transaction rollback for isolation."""
    async with test_engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        yield session

        await session.close()
        await transaction.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to the test app with db dependency override."""
    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Auth fixtures (SPEC-007 §13.4)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_public_key_pem() -> bytes:
    """Public key the auth middleware will validate against (TASK-014)."""
    return jwt_keys.PUBLIC_KEY_PEM


@pytest.fixture(scope="session")
def test_private_key_pem() -> bytes:
    """Private key used to mint test tokens. Never used by production code."""
    return jwt_keys.PRIVATE_KEY_PEM


@pytest.fixture
def make_token() -> TokenFactory:
    """Return a callable that mints signed JWTs with overridable claims.

    Defaults produce a token that the auth middleware (TASK-014) will accept.
    Pass overrides to express negative-path scenarios:

        make_token()                            # valid
        make_token(exp_offset=-60)              # expired
        make_token(iss="https://attacker/")     # wrong issuer
        make_token(extra_claims={"permissions": ["org:read"]})

    The signature is a thin wrapper around ``jwt_keys.mint_token`` so tests
    can stay declarative and the underlying minting helper stays free-function
    callable from non-pytest contexts (e.g. integration scripts).
    """

    def _mint(**overrides: Any) -> str:
        return jwt_keys.mint_token(**overrides)

    return _mint


@pytest.fixture
def auth_header(make_token: TokenFactory) -> dict[str, str]:
    """Convenience: a ready-to-use Authorization header with a default valid token."""
    return {"Authorization": f"Bearer {make_token()}"}
