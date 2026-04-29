"""
Test-only RSA key material and JWT minting helper (SPEC-007 §13.4, TASK-008).

A fresh RSA keypair is generated once per process import and exposed as
module-level PEM constants. Tests use ``mint_token(**overrides)`` to issue
JWTs signed with the same private key. TASK-014 will configure the auth
middleware to validate against ``PUBLIC_KEY_PEM`` from this module so the
same keypair is used end-to-end without committing secrets.

Generating fresh per process avoids checking key material into the repo
and avoids any risk of a "test" key being mistaken for production.
"""

from __future__ import annotations

import time
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwt
from joserfc.jwk import RSAKey


def _generate_keypair() -> tuple[bytes, bytes]:
    """Generate a 2048-bit RSA keypair and return (private_pem, public_pem)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


PRIVATE_KEY_PEM, PUBLIC_KEY_PEM = _generate_keypair()

TEST_ISSUER = "https://groundwork-test.local/"
TEST_AUDIENCE = "https://api.groundwork.test/"
TEST_KID = "groundwork-test-key"

_PRIVATE_KEY = RSAKey.import_key(PRIVATE_KEY_PEM, parameters={"kid": TEST_KID})


def mint_token(
    *,
    sub: str = "auth0|test-subject",
    iss: str = TEST_ISSUER,
    aud: str | list[str] = TEST_AUDIENCE,
    exp_offset: int = 3600,
    iat_offset: int = 0,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Mint a signed JWT for tests.

    Defaults produce a valid token. Override ``exp_offset`` to make the
    token expired (negative seconds), ``iss`` / ``aud`` to test rejection
    paths, and pass ``extra_claims`` for custom claims (e.g. permissions).
    """
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": sub,
        "iss": iss,
        "aud": aud,
        "iat": now + iat_offset,
        "exp": now + exp_offset,
    }
    if extra_claims:
        claims.update(extra_claims)

    return jwt.encode(
        {"alg": "RS256", "kid": TEST_KID, "typ": "JWT"},
        claims,
        _PRIVATE_KEY,
    )
