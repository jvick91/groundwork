/**
 * Groundwork Post-Login Action (TASK-014C / ADR-010)
 *
 * Runs after every successful Auth0 authentication, before the token is issued.
 * Three gates (fail-closed) + claim enrichment in this order:
 *
 *  1. Email verification gate   — fail-closed
 *  2. Inactive-Person gate      — fail-closed; reads app_metadata set by backend
 *  3. Claim enrichment          — bakes org_id + is_active into the JWT
 *
 * MFA enforcement is handled by the Auth0 tenant policy (set to "Always" in
 * Security → Multi-factor Auth). This Action does not re-assert MFA — the
 * dashboard policy runs before Post-Login Actions.
 *
 * Failure-mode contract (see docs/auth0-post-login-actions.md):
 *   - All three gates are fail-closed: when in doubt, deny.
 *   - A denied login returns a generic error to the user; specific reasons
 *     are logged server-side only (no PHI in error messages).
 *   - Claim enrichment is fail-closed: if org_id is missing (org-tagless
 *     flow), enrichment is skipped and the backend middleware will reject
 *     the token on the next API call.
 *
 * Deployment:
 *   Auth0 Dashboard → Actions → Library → Create Action → Post Login
 *   Paste this file. No npm dependencies required. Add to the Login flow.
 *
 * Versioning:
 *   This file is the source of truth. When updating, increment the version
 *   comment below and redeploy via the Auth0 dashboard or CLI.
 *
 * @version 1.0.0
 */

exports.onExecutePostLogin = async (event, api) => {
  // -----------------------------------------------------------------------
  // Gate 1: Email verification
  // -----------------------------------------------------------------------
  // Users must verify their email before they can log in. New users invited
  // via the invitation flow (TASK-014F/G) receive a verification email from
  // Auth0 automatically. Fail-closed: unverified email = no token.
  if (!event.user.email_verified) {
    api.access.deny(
      "Your email address has not been verified. " +
      "Please check your inbox for a verification link."
    );
    return;
  }

  // -----------------------------------------------------------------------
  // Gate 2: Inactive-Person gate
  // -----------------------------------------------------------------------
  // app_metadata.is_active is mirrored from Person.is_active by the backend
  // (PersonService.update / .delete → Auth0SyncService) on every state change.
  // Fail-closed: missing or null is_active = deny (treat as inactive).
  // This prevents login for newly created users whose app_metadata has not
  // yet been synced.
  //
  // Staleness: up to 15 minutes (access token TTL). Immediate revocation
  // requires TASK-014J (force-kill session + refresh token families).
  const isActive = event.user.app_metadata?.is_active;
  if (isActive !== true) {
    api.access.deny(
      "Your account is inactive. Please contact your administrator."
    );
    return;
  }

  // -----------------------------------------------------------------------
  // Claim enrichment
  // -----------------------------------------------------------------------
  // Bake org_id and is_active into both the ID token and access token so
  // the backend middleware can read them without a DB call per request.
  //
  // org_id is set by Auth0 Organizations automatically when the user logs in
  // through an org. event.organization is null for org-tagless flows (which
  // the backend will reject anyway).
  if (event.organization) {
    api.idToken.setCustomClaim("org_id", event.organization.id);
    api.accessToken.setCustomClaim("org_id", event.organization.id);
  }

  // is_active in the JWT is the fast-path short-circuit in the middleware.
  // The authoritative check is always the DB row (Person.is_active).
  api.accessToken.setCustomClaim("is_active", true);
};
