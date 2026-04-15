"""
Test application factory.

Wraps create_app() with any test-specific configuration overrides.
"""

from fastapi import FastAPI

from app.main import create_app


def create_test_app() -> FastAPI:
    """Create a FastAPI app instance configured for testing."""
    return create_app()
