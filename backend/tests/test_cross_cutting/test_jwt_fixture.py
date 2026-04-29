"""
Tests for the JWT test fixtures (SPEC-007 §13.4, TASK-008).

Asserts that:
  * The session-scoped key fixtures expose PEM-encoded RSA keys.
  * ``make_token`` mints tokens that decode + verify against the public key.
  * Claim overrides (sub, iss, aud, exp, extra_claims) are respected so
    negative-path tests can be expressed without reimplementing the encoder.
"""

from __future__ import annotations

import time
from typing import Any, cast

import pytest
from joserfc import jwt
from joserfc.errors import BadSignatureError
from joserfc.jwk import RSAKey

from tests.conftest import TokenFactory


def _decode(token: str, public_pem: bytes) -> dict[str, Any]:
    """Verify signature against the test public key and return the claims."""
    key = RSAKey.import_key(public_pem)
    decoded = jwt.decode(token, key)
    return cast(dict[str, Any], decoded.claims)


def test_public_and_private_keys_are_pem_encoded(
    test_public_key_pem: bytes,
    test_private_key_pem: bytes,
) -> None:
    assert test_public_key_pem.startswith(b"-----BEGIN PUBLIC KEY-----")
    assert test_private_key_pem.startswith(b"-----BEGIN PRIVATE KEY-----")


def test_make_token_default_is_valid(
    make_token: TokenFactory,
    test_public_key_pem: bytes,
) -> None:
    token = make_token()
    claims = _decode(token, test_public_key_pem)

    assert claims["sub"] == "auth0|test-subject"
    assert claims["iss"] == "https://groundwork-test.local/"
    assert claims["aud"] == "https://api.groundwork.test/"
    assert claims["exp"] > int(time.time())
    assert claims["iat"] <= int(time.time()) + 1


def test_make_token_overrides_subject_and_audience(
    make_token: TokenFactory,
    test_public_key_pem: bytes,
) -> None:
    token = make_token(sub="auth0|alice", aud="https://other-api/")
    claims = _decode(token, test_public_key_pem)

    assert claims["sub"] == "auth0|alice"
    assert claims["aud"] == "https://other-api/"


def test_make_token_can_produce_expired_token(
    make_token: TokenFactory,
    test_public_key_pem: bytes,
) -> None:
    """Negative-path scenario: middleware in TASK-014 must reject this."""
    token = make_token(exp_offset=-60)
    claims = _decode(token, test_public_key_pem)

    assert claims["exp"] < int(time.time())


def test_make_token_can_inject_custom_claims(
    make_token: TokenFactory,
    test_public_key_pem: bytes,
) -> None:
    """Custom claims (e.g. permissions) flow through unchanged."""
    token = make_token(extra_claims={"permissions": ["org:read", "org:write"]})
    claims = _decode(token, test_public_key_pem)

    assert claims["permissions"] == ["org:read", "org:write"]


def test_make_token_signature_validates_against_test_public_key_only(
    make_token: TokenFactory,
    test_public_key_pem: bytes,
) -> None:
    """Sanity: another keypair must not validate the token.

    Guards against an accidental hard-coded constant: if someone ever
    short-circuits ``mint_token`` to use a static key, this catches it.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    other_pem = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    token = make_token()
    # Test key validates
    _decode(token, test_public_key_pem)
    # Foreign key does not — joserfc raises BadSignatureError on mismatch.
    with pytest.raises(BadSignatureError):
        _decode(token, other_pem)


def test_auth_header_fixture_returns_bearer_token(auth_header: dict[str, str]) -> None:
    assert "Authorization" in auth_header
    assert auth_header["Authorization"].startswith("Bearer ")
    assert len(auth_header["Authorization"]) > len("Bearer ")
