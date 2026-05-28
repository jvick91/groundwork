#!/usr/bin/env python
"""
One-shot bootstrap script (TASK-014E / ADR-013).

Provisions the first Organization, Person(system_admin), and their Auth0
counterparts. Run once inside the container before the first operator login.

Usage
-----
    # 1. Write a random token to the marker file:
    python -c "import secrets; print(secrets.token_urlsafe(32))" \\
        > /var/run/groundwork/bootstrap.token

    # 2. Run the script (reads the same file):
    python scripts/bootstrap.py \\
        --token-file /var/run/groundwork/bootstrap.token \\
        --org-name "acme" \\
        --org-display-name "Acme Corp" \\
        --admin-first "Alice" \\
        --admin-last "Admin" \\
        --admin-email "alice@acme.com"

    # 3. On success the script prints the password-change ticket URL.
    #    Deliver it to the admin out-of-band. The marker file is deleted.

Security model
--------------
- The script must be run from within the container (docker exec / kubectl exec).
  Shell access to the container is the capability gate — no HTTP surface required.
- The marker file is deleted on success, preventing re-bootstrap.
- If Auth0 mutations succeed but the DB write fails, compensating calls roll back
  the Auth0 state and the marker file is left in place for retry.

Credentials
-----------
The script reads the same settings as the FastAPI app (via pydantic-settings +
.env.backend). All required values must be present before running:
    AUTH0_DOMAIN, AUTH0_MANAGEMENT_CLIENT_ID, AUTH0_MANAGEMENT_CLIENT_SECRET,
    AUTH0_MANAGEMENT_AUDIENCE, DATABASE_URL.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the first Groundwork Organization and system admin."
    )
    parser.add_argument(
        "--token-file",
        default="/var/run/groundwork/bootstrap.token",
        help="Path to the one-shot bootstrap token file (default: %(default)s).",
    )
    parser.add_argument("--org-name", required=True, help="Auth0 org slug (lowercase, no spaces).")
    parser.add_argument("--org-display-name", required=True, help="Human-readable org name.")
    parser.add_argument("--admin-first", required=True, help="Admin first name.")
    parser.add_argument("--admin-last", required=True, help="Admin last name.")
    parser.add_argument("--admin-email", required=True, help="Admin email address.")
    parser.add_argument(
        "--token",
        default=None,
        help=(
            "Bootstrap token value. "
            "If omitted the script reads it interactively from stdin "
            "(safer: avoids the token appearing in shell history)."
        ),
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    # Late imports so the module is importable without the full app stack loaded.
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.auth0_management_service import Auth0ManagementService
    from app.services.bootstrap_service import BootstrapRequest, BootstrapService

    token_path = Path(args.token_file)

    # ------------------------------------------------------------------
    # Token validation
    # ------------------------------------------------------------------
    if not token_path.exists():
        print(
            f"ERROR: Token file not found: {token_path}\n"
            "Bootstrap has already been performed, or the file was never created.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        stored_token = token_path.read_text().strip()
    except OSError as exc:
        print(f"ERROR: Cannot read token file: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.token is not None:
        supplied_token = args.token.strip()
    else:
        try:
            supplied_token = input("Bootstrap token: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.", file=sys.stderr)
            sys.exit(1)

    # Constant-time comparison to prevent timing oracle.
    if not hmac.compare_digest(supplied_token, stored_token):
        print("ERROR: Token mismatch.", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Build dependencies
    # ------------------------------------------------------------------
    if not settings.auth0_management_client_id or not settings.auth0_management_client_secret:
        print(
            "ERROR: Auth0 Management API credentials are not configured.\n"
            "Set AUTH0_MANAGEMENT_CLIENT_ID, AUTH0_MANAGEMENT_CLIENT_SECRET, "
            "and AUTH0_MANAGEMENT_AUDIENCE in your environment or .env.backend.",
            file=sys.stderr,
        )
        sys.exit(1)

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    http_client = httpx.AsyncClient(timeout=15.0)

    try:
        management = Auth0ManagementService(http_client)

        async with AsyncSession(engine) as session:
            async with session.begin():
                svc = BootstrapService(session=session, management=management)
                request = BootstrapRequest(
                    org_name=args.org_name,
                    org_display_name=args.org_display_name,
                    admin_first_name=args.admin_first,
                    admin_last_name=args.admin_last,
                    admin_email=args.admin_email,
                )
                result = await svc.execute(request, token_path)
    finally:
        await http_client.aclose()
        await engine.dispose()

    # ------------------------------------------------------------------
    # Success output
    # ------------------------------------------------------------------
    print("\n✓ Bootstrap complete.\n")
    print(f"  Organization ID : {result.organization_id}")
    print(f"  Person ID       : {result.person_id}")
    print(f"  Auth0 User ID   : {result.auth0_user_id}")
    print()
    print("  Password-change ticket URL (deliver out-of-band to the admin):")
    print(f"  {result.password_change_ticket_url}")
    print()
    print("  The bootstrap token file has been deleted.")
    print("  This script cannot be run again without placing a new token file.\n")


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except Exception as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
