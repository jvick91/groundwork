"""
Shared pytest fixtures for async database testing with transaction rollback isolation.

Each test runs inside a transaction that is rolled back after the test completes,
ensuring full isolation without needing to recreate tables between tests.
"""

import contextlib
from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base, Database
from app.core.dependencies import get_db
from app.main import create_app
from tests.fixtures import jwt_keys

TokenFactory = Callable[..., str]

# Tracks every db_session instance so create_tables teardown can close them
# before drop_all, releasing any table locks held by open/aborted transactions.
_open_sessions: list[AsyncSession] = []


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def initialize_database() -> AsyncGenerator[None, None]:
    """Initialize the production Database singleton against the test DB.

    The FastAPI lifespan does not run under ``httpx.ASGITransport``, so any
    code that touches ``Database.get_engine()`` (e.g. the readiness probe in
    ``app/routers/health.py``) would otherwise see an uninitialized engine
    and report ``"error"``. Initializing here mirrors production startup.
    """
    Database.initialize(settings.test_database_url, poolclass=NullPool)
    yield
    await Database.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    """Create a single async engine for the entire test session.

    ``NullPool`` is intentional: it ensures that asyncpg connections are
    created in the same asyncio event loop that the test coroutine runs in,
    preventing the "Future attached to a different loop" error that occurs
    when the pool's background machinery captures a different loop at startup.
    """
    engine = create_async_engine(
        settings.test_database_url,
        poolclass=NullPool,
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
    # Close all db_session instances before drop_all to release table locks.
    # create_tables teardown runs in the session event loop — the same loop
    # in which test tasks created their asyncpg connections — so
    # await session.close() works without a loop-mismatch.  The try/except
    # ensures that sessions left in an aborted-transaction state (e.g. after
    # an immutability-trigger DBAPIError) are also handled gracefully.
    for session in _open_sessions:
        with contextlib.suppress(Exception):
            await session.close()
    _open_sessions.clear()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="session")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Per-test database session backed by the Database singleton (NullPool).

    Connection is established **lazily** — on first use inside the test body
    — so that the asyncpg protocol's event-loop reference matches the running
    loop of the test task.  Eagerly pre-connecting in fixture setup (via
    ``test_engine.connect()``) can capture a different loop snapshot, causing
    "Future attached to a different loop" errors.

    Isolation strategy: each test uses uuid-unique identifiers, so accumulated
    rows do not interfere.  ``create_tables`` drops all tables at session end.
    Tests that need explicit rollback (e.g. atomicity checks) call
    ``await db_session.rollback()`` directly in the test body — which runs
    inside the test task and has the correct loop context.

    Connection release: ``await session.close()`` runs in the finalizer
    wrapped in ``contextlib.suppress`` so the known greenlet-bridge / task
    mismatch (which would otherwise prevent ``rollback`` from working) is
    tolerated. The previous design accumulated every session for the whole
    test run and only closed at the session-end ``create_tables`` teardown;
    that leaked one Postgres connection per ``db_session``-using test and
    blew through ``max_connections`` once the suite crossed ~100 tests.
    Closing here releases the NullPool connection back to the OS while the
    suppress keeps any greenlet-bridge failure non-fatal — equivalent to
    the suppress used at session-end teardown for the same reason.
    """
    session: AsyncSession = Database.get_session_factory()()
    _open_sessions.append(session)
    try:
        yield session
    finally:
        with contextlib.suppress(Exception):
            await session.close()


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to the test app with db dependency override."""
    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app, raise_app_exceptions=False)
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
