# Auth0 Tenant Setup Runbook

**ADR:** [ADR-010 — Consolidated Auth0 Identity Architecture](../adrs/ADR-010-consolidated-auth-architecture.md)  
**Tasks:** TASK-014B (this runbook), TASK-014C (Post-Login Actions), TASK-014D (Management API)

This document is the authoritative step-by-step guide for configuring an Auth0 tenant for Groundwork. Follow it in order for each environment (dev, staging, prod). All decisions reference ADR-010.

---

## Prerequisites

- Auth0 tenant already created (any region; US is recommended for HIPAA BAA eligibility)
- Admin access to the Auth0 dashboard
- Your environment's backend URL known (e.g. `https://api.groundwork.app`)

---

## 1. Collect your tenant coordinates

Open **Auth0 Dashboard → Settings** and note:

| Value | Where to find it | Env var |
|---|---|---|
| Tenant domain | Top of Settings page, e.g. `your-tenant.us.auth0.com` | `AUTH0_DOMAIN` |
| Tenant region | Embedded in the domain suffix (`.us.`, `.eu.`, `.au.`) | — |

You will fill in all env vars at the end of this runbook (§9).

---

## 2. Enable Organizations

Organizations is the Auth0 feature that issues `org_id`-scoped JWTs — required by ADR-010.

1. **Dashboard → Organizations → Enable Organizations**  
   If the menu item is absent, contact Auth0 support or upgrade your plan (Organizations requires Developer Pro or higher).
2. Leave all settings at defaults for now. You will create the first Organization in TASK-014E (bootstrap).

---

## 3. Create the API (audience)

The API resource represents your backend. Every JWT the frontend requests will include this audience.

1. **Dashboard → Applications → APIs → Create API**
2. Fill in:
   - **Name:** `Groundwork API`
   - **Identifier (audience):** `https://api.groundwork.app/`  
     _(Use your actual domain. This becomes `AUTH0_AUDIENCE`.)_
   - **Signing Algorithm:** `RS256`
3. On the API's **Settings** tab, set:
   - **Token Expiration:** `900` seconds (15 minutes per ADR-010 §3)
   - **Token Expiration For Browser Flows:** `900`
   - **Allow Offline Access:** ✅ Enabled (enables refresh tokens)
4. Click **Save**.

---

## 4. Configure the SPA application

This is the client the frontend uses.

1. **Dashboard → Applications → Create Application**
2. Fill in:
   - **Name:** `Groundwork Web`
   - **Type:** `Single Page Application`
3. On the **Settings** tab, fill in for each environment:

   | Field | Dev | Staging | Prod |
   |---|---|---|---|
   | Allowed Callback URLs | `http://localhost:3000/callback` | `https://staging.groundwork.app/callback` | `https://app.groundwork.app/callback` |
   | Allowed Logout URLs | `http://localhost:3000` | `https://staging.groundwork.app` | `https://app.groundwork.app` |
   | Allowed Web Origins | `http://localhost:3000` | `https://staging.groundwork.app` | `https://app.groundwork.app` |

4. On the **Organizations** tab:
   - **Organizations:** `Business Users`
   - **Login Flow:** `Prompt for Organization`  
     _(This is what triggers the org picker and issues `org_id`-scoped tokens.)_
5. Click **Save**.
6. Note the **Client ID** from the Settings tab — this is what the frontend SDK uses.

---

## 5. Configure token settings

### 5a. Refresh token rotation (ADR-010 §3)

1. **Dashboard → Applications → Groundwork Web → Settings → Refresh Token Rotation**
2. Set:
   - **Rotation:** `Enabled`
   - **Reuse Interval:** `0` seconds
   - **Absolute Expiration:** `Enabled`, `2592000` seconds (30 days)
   - **Inactivity Expiration:** `Enabled`, `1296000` seconds (15 days)
3. Enable **Refresh Token Reuse Detection** (automatically enabled with rotation).

### 5b. Breach detection

1. **Dashboard → Security → Attack Protection → Breached Password Detection**
2. Set to **Enabled — Block** for the highest protection tier.

---

## 6. Configure Universal Login and MFA

### 6a. Universal Login

1. **Dashboard → Branding → Universal Login**
2. Choose **New Universal Login Experience** (required for WebAuthn/passkeys).
3. Upload your logo and set brand colors. Click **Save**.

### 6b. MFA — Universal enforcement (ADR-010 §2)

1. **Dashboard → Security → Multi-factor Auth**
2. Under **Factors**, enable:
   - ✅ **WebAuthn with FIDO Security Keys** (passkeys — primary factor)
   - ✅ **One-time Password** (TOTP — fallback)
   - ✅ **SMS** (fallback; requires Twilio or similar — optional for MVP)
3. Under **Policy**, set to **Always** (universal MFA; no opt-out).
4. Click **Save**.

### 6c. Single connection (ADR-010 §1 — no social/SAML in MVP)

1. **Dashboard → Authentication → Database**
2. Confirm only one connection exists: `Username-Password-Authentication`.
3. Do **not** create any Social or Enterprise connections.

---

## 7. Create the Machine-to-Machine application (Management API)

This M2M app is what TASK-014D uses server-side to manage users and organizations.

1. **Dashboard → Applications → Create Application**
2. Fill in:
   - **Name:** `Groundwork Backend (M2M)`
   - **Type:** `Machine to Machine Application`
3. When prompted to authorize an API, select **Auth0 Management API**.
4. Grant the following permissions (minimum required for TASK-014D through TASK-014G):

   | Permission | Purpose |
   |---|---|
   | `read:users` | Look up users by email during invitation accept |
   | `update:users` | Write `app_metadata` (permissions_version, is_active) |
   | `create:users` | Bootstrap first admin (TASK-014E) |
   | `read:organizations` | Verify org membership |
   | `create:organizations` | Bootstrap first org (TASK-014E) |
   | `create:organization_members` | Add user to org on invite accept |
   | `delete:organization_members` | Force-revoke (TASK-014J) |
   | `read:organization_invitations` | Invitation status checks |
   | `create:organization_invitations` | Send invitations (TASK-014F) |
   | `delete:organization_invitations` | Revoke invitations |
   | `read:roles` | Role sync (future) |
   | `update:users_app_metadata` | permissions_version cache invalidation (ADR-012) |

5. Click **Authorize**.
6. On the app's Settings tab, note the **Client ID** and **Client Secret**.  
   These become `AUTH0_MANAGEMENT_CLIENT_ID` and `AUTH0_MANAGEMENT_CLIENT_SECRET`.
7. The Management API audience is always `https://YOUR_DOMAIN/api/v2/` — note this as `AUTH0_MANAGEMENT_AUDIENCE`.

---

## 8. Verify JWKS is reachable

Your backend's JWKS probe fetches:

```
https://<AUTH0_DOMAIN>/.well-known/jwks.json
```

Confirm this URL returns JSON in your browser before wiring up the backend. If it returns 404 your domain is incorrect.

---

## 9. Fill in your `.env.backend`

```dotenv
# Auth0 — JWT validation
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_AUDIENCE=https://api.groundwork.app/
AUTH0_ISSUER=https://your-tenant.us.auth0.com/

# Auth0 — Management API
AUTH0_MANAGEMENT_CLIENT_ID=<client-id from §7>
AUTH0_MANAGEMENT_CLIENT_SECRET=<client-secret from §7>
AUTH0_MANAGEMENT_AUDIENCE=https://your-tenant.us.auth0.com/api/v2/

# Flip this off once Auth0 is wired up end-to-end
AUTH0_STUB_ENABLED=false
```

> **Never commit real secrets.** `.env.backend` is git-ignored. Use your secret manager (AWS Secrets Manager, Doppler, etc.) in staging/prod.

---

## 10. Smoke test

Once the env vars are set and `AUTH0_STUB_ENABLED=false`:

```bash
# Readiness probe should show auth0_jwks: "ok"
curl http://localhost:8000/api/v1/health/ready
```

Expected response:
```json
{"status": "ready", "checks": {"database": "ok", "auth0_jwks": "ok"}}
```

---

## What Auth0 handles (no backend code needed)

Per ADR-010, the following flows are fully Auth0-handled:

- **Login** — Universal Login page, MFA challenge, org picker
- **Logout** — redirect to Auth0 logout endpoint; backend has no `/logout` route
- **Password reset** — Auth0 Universal Login handles this natively
- **Passkey enrollment** — WebAuthn flow inside Universal Login
- **Refresh token rotation** — Auth0 SDK handles silently in the browser

The backend only validates the resulting JWT on each request and issues `SET LOCAL app.org_id` for RLS.

---

## Pending (covered by later tasks)

| What | Task |
|---|---|
| Post-Login Action (MFA enforcement, `is_active` claim, `permissions_version` enrichment) | TASK-014C |
| Management API client code | TASK-014D |
| Bootstrap first org/person/admin | TASK-014E |
| Invitation flow | TASK-014F / 014G |
