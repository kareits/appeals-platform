# ADR-0010: Corporate OIDC federation (Keycloak + Active Directory)

- **Status:** Proposed — target architecture; implementation deferred to TASK_06. This document is
  the concrete form of the placeholder **ADR-AUTH-OIDC** referenced by ADR-0006, ADR-0007,
  ADR-0008, and ADR-0009.
- **Related:** ADR-0006 (dev/local auth and the authorization matrix — this decision is to supersede
  its production-authentication part once accepted and implemented at TASK_06); ADR-0007 (BFF gateway
  auth context); ADR-0008 (Ticket-service independent JWT verification); ADR-0009 (web-frontend
  foundation); ADR-012 (mocks for undefined external integrations); docs/06 (security, authorization,
  audit); OPEN_QUESTIONS Q-B3.
- **Confirmed inputs:** IT administrators, 2026-08-10 (see the fact table below and
  [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) Q-B1/Q-B2/Q-B3).

## Context

ADR-0006 established a **dev/local** authentication scheme: the IAM Service issues an HS256 JWT
whose claims carry the subject, roles, resolved permissions, and teams. The consumption paths differ
by service: the **BFF** does not verify the token itself — it resolves the caller context by calling
IAM `GET /auth/me` (ADR-0007) — while the **Ticket Service** verifies the token it receives
independently and enforces authorization on the claim strings (ADR-0008). That scheme is explicitly
non-production (ADR-012): the corporate identity provider was undefined, so a fake was used behind a
stable claim shape.

The corporate identity provider is now defined. IT administrators confirmed the following:

| Aspect | Confirmed value |
|---|---|
| IdP / version | Keycloak 26.0.8 |
| Realm | `KZ` |
| Protocol | OpenID Connect (OIDC) |
| Issuer | `https://keycloak.solva.kz/realms/KZ` |
| Authorization endpoint | `.../protocol/openid-connect/auth` |
| Token endpoint | `.../protocol/openid-connect/token` |
| JWKS endpoint | `.../protocol/openid-connect/certs` |
| UserInfo endpoint | `.../protocol/openid-connect/userinfo` |
| End-session (logout) | `.../protocol/openid-connect/logout` |
| Flow | Authorization Code + PKCE (server supports `S256` and `plain`; `S256` recommended) |
| Token signature | RS256 |
| Access-token lifetime | 5 minutes |
| SSO session idle / max | 30 minutes / 10 hours |
| Offline session idle | 30 days |
| Refresh-token rotation | Disabled (`Revoke Refresh Token = Disabled`) |
| Login timeout / action timeout | 30 minutes / 5 minutes |
| Client registration | Performed by Keycloak admins; Client ID (+ Client Secret for confidential clients) issued on request |
| AD federation | Active Directory via LDAP User Federation |
| Roles/groups in token | Only roles/groups configured in Keycloak; AD groups are not in the token unless a mapper is configured |
| Service-to-service | Client Credentials grant not currently used |
| MFA | Not used |
| Provisioning / deprovisioning | Users sync from AD via LDAP; disable/revoke happens in AD and propagates to Keycloak |
| Test environment | No separate Keycloak test environment; HTTPS transport; inter-segment access via FortiGate |

Two invariants from the existing design must be preserved: authorization stays owned by the IAM
role → permission matrix (ADR-0006, ADR-007 — no shared permission library), and downstream
services must keep verifying a signed token independently (ADR-0008). The transition therefore
changes **who signs the token and how it is verified**, not the claim shape or the authorization
model.

## Decision

The following are fixed now; the items under "Open for TASK_06" are the remaining design choices,
listed so they are not lost.

1. **Root of trust moves to a verified Keycloak OIDC login; IAM is the verification authority.** In
   production the corporate identity is established by an OIDC login whose token is signed by
   Keycloak (RS256). **IAM** verifies that token against the realm JWKS (`.../certs`), checking
   `iss = https://keycloak.solva.kz/realms/KZ`, the audience equal to the registered client, and
   expiry. This matches ADR-0007, which already states that across the OIDC transition "only IAM's
   verification changes, not the gateway." The symmetric HS256 dev issuance (ADR-0006) is used only
   for `local`/`dev`/`test`, where the environment allowlist already fails closed.

2. **The internal claim shape is preserved.** The `roles`, `permissions`, and `teams` claims remain
   the contract. IAM stays the authority that resolves and vends these claims, so what changes is the
   root of trust behind IAM's resolution (a verified Keycloak identity), not the claim shape. **Under
   the public-SPA topology** the consumption paths are unchanged and ADR-0006/0007/0008/0009 stay
   valid: the **BFF** keeps resolving the caller context via IAM `GET /auth/me` and does **not**
   verify tokens itself (ADR-0007), the **Ticket Service** keeps verifying independently the token it
   receives (ADR-0008), and the frontend (ADR-0009) is unaffected. **The confidential-BFF topology
   is different:** it makes the BFF an OIDC client (code exchange, client secret, refresh token, a
   server-issued SPA session) and therefore requires revising **both ADR-0007** (the BFF stops being
   a stateless bearer-forwarding gateway and gains a login/callback/logout and session/cookie
   contract, plus how it conveys a platform token to the Ticket Service) **and ADR-0009** (auth state
   leaves `sessionStorage`). **How** the IAM-resolved claims reach the token the Ticket Service
   independently verifies is an explicit TASK_06 choice (see "Open for
   TASK_06").

3. **Stable user key = AD `objectGUID`, stored as `iam_user.external_subject`.** The immutable
   identity key is the Active Directory `objectGUID`, exposed to the token through a Keycloak
   protocol mapper and stored on a new **nullable** `iam_user.external_subject` column. Rationale:
   `objectGUID` does not change when a user is renamed or moved (unlike `UPN`) and survives a
   re-created LDAP federation link (unlike the Keycloak `sub`, which is Keycloak-internal). IAM keys
   its local user (roles/teams) on `external_subject`; `sub`/`UPN` may be recorded for diagnostics
   but are not the join key. Backfilling `external_subject` for existing local users is a TASK_06
   migration/provisioning step.

4. **Authorization stays owned by IAM; identity comes from Keycloak.** Keycloak provides the
   authenticated identity (and, via a configured mapper, group/role claims). IAM remains the
   authority for the role → permission matrix (ADR-0006). Because AD groups are not in the token by
   default, one of two integration paths is chosen at TASK_06: (a) request a Keycloak group/role
   **mapper** that emits group claims, which IAM maps to its local roles; or (b) IAM maps the
   external identity to local roles through its own user↔role store. Either way, downstream services
   keep consuming IAM-resolved `roles`/`permissions` — they never read AD groups directly.

5. **Service-to-service stays on the internal scheme.** The Client Credentials grant is **not
   currently used/configured** for the platform. Inter-service calls therefore keep the existing
   internal authentication (shared secret / internal token) until a Keycloak service-account /
   confidential client is provisioned for machine-to-machine use. Whether the grant can be enabled is
   a separate confirmation with the Keycloak admins; this ADR only records that it is not in use
   today.

6. **Session and lifetime handling respects Keycloak timings.** Access tokens live 5 minutes; SSO
   idle is 30 minutes and max 10 hours; refresh-token rotation is disabled. The session/refresh
   strategy (decision under "Open for TASK_06") must renew access tokens within these bounds and use
   the Keycloak end-session endpoint for logout. The frontend's tab-scoped `sessionStorage` model
   (ADR-0009) fits the public-SPA topology; the confidential-BFF topology changes where auth state
   lives (see the flow-topology item under "Open for TASK_06").

7. **No MFA and no separate test realm today.** MFA is not enabled (confirmed); this ADR records
   that fact and does not otherwise constrain the primary authentication mechanism, which is
   configured in Keycloak/AD. Because there is no dedicated Keycloak test environment, automated
   integration testing continues to rely on the dev-auth scheme for `local`/CI; a dedicated test
   client (and, if needed, a test realm or throwaway accounts) is requested from the Keycloak admins
   before any shared-environment OIDC E2E.

### Open for TASK_06 (recorded, not yet decided)

- **How IAM-resolved claims reach the independently-verified token.** Either (a) Keycloak protocol
  mappers emit the final claims into the Keycloak token that the Ticket Service verifies directly
  (IAM synchronizes the role data into Keycloak), or (b) after verifying the Keycloak login, IAM
  mints a short-lived platform-internal signed token carrying the IAM-resolved
  `roles`/`permissions`/`teams`, which the Ticket Service verifies (asymmetric signing per docs/06).
  Recommendation: **(b)**, because permissions are IAM-computed and IAM-owned (ADR-0006), so keeping
  them out of Keycloak avoids duplicating the authorization matrix into the IdP; option (a) is viable
  if the team prefers a single token issuer.
- **Flow topology.** Either (a) the SPA is a **public** OIDC client performing Authorization Code +
  PKCE in the browser (no client secret; bearer/refresh tokens held tab-scoped, as in ADR-0009), or
  (b) the **BFF is a confidential client** that performs the code exchange server-side (holds the
  Client Secret and refresh token and issues its own session to the SPA). Recommendation:
  **(b) confidential BFF**, because it keeps the **bearer and refresh tokens** out of the browser
  (reducing token-exfiltration exposure) — not because it removes "signing material" (a public
  SPA + PKCE also holds no client secret). Trade-off: option (a) is compatible with the current
  ADR-0007/0009 (a stateless bearer-forwarding BFF; a tab-scoped token in `sessionStorage`); option
  (b) **requires revising both ADR-0007 and ADR-0009**, since it makes the BFF an OIDC client with a
  server-side login/callback/logout and session contract, changes how a platform token reaches the
  Ticket Service, and moves auth state out of `sessionStorage`. The final call is made at TASK_06.
- **`external_subject` backfill/provisioning** for pre-existing local users and the exact Keycloak
  mapper configuration (objectGUID claim name, group/role mapper).
- **Test access:** a test client/realm and, if required, a test mailbox-independent set of throwaway
  accounts; network access to Keycloak over HTTPS across FortiGate segments.

## Alternatives considered

- **Treat Keycloak as an unverified upstream login (IAM never validates the corporate token):**
  rejected — if IAM does not cryptographically verify the Keycloak RS256 token, IAM becomes the
  de-facto identity authority and lifetimes/revocation desynchronize from Keycloak/AD, contrary to
  the docs/06 target of trusting a verified corporate identity. This is **distinct from** delivery
  option (b) under "Open for TASK_06": there IAM **first verifies** the Keycloak token (JWKS) and
  only then mints a short-lived internal claims-carrier token, so the corporate login stays the
  verified root of trust. Option (b) is therefore not this rejected variant — it re-issues an
  internal token, never a corporate access token.
- **Key users on `UPN` or Keycloak `sub`:** rejected — `UPN` changes on rename; `sub` is
  Keycloak-internal and can change if the federation link is re-created. `objectGUID` is the stable
  AD identity.
- **Read AD groups directly for authorization:** rejected — AD groups are not in the token by
  default and this would move authorization out of IAM (violating ADR-0006/007). IAM stays
  authoritative; a Keycloak mapper (if used) only supplies claims IAM maps.
- **Public SPA OIDC client (browser-held tokens) as the default:** viable and simpler, kept as
  option (a); deferred in favour of the confidential-BFF recommendation for a stronger token-custody
  posture. Final call at TASK_06.

## Consequences

- No code changes in this ADR. The dev-auth scheme (ADR-0006) remains the runtime for local/dev/CI
  and is unaffected. TASK_06 implements the verification switch, the `external_subject` column and
  backfill, the Keycloak client registration (via admins), and the chosen flow topology.
- No service requires a **claim-shape change**, and the new RS256/JWKS verification is added at the
  **IAM** boundary (selected by environment alongside the existing HS256 dev path); the delivery of
  the resolved claims to the Ticket-verified token follows the TASK_06 choice above. Under the
  **public-SPA** topology the consumption paths and the BFF/frontend contracts are unaffected — the
  BFF keeps using IAM `/auth/me` (ADR-0007) and the Ticket Service keeps verifying its received token
  independently (ADR-0008). The **confidential-BFF** topology instead requires revising both ADR-0007
  (BFF becomes an OIDC client with a session contract) and ADR-0009 (auth state leaves
  `sessionStorage`).
- Because refresh-token rotation is disabled and access tokens are short (5 min), the session layer
  must refresh actively within the 30-minute idle / 10-hour max SSO window; logout must call the
  Keycloak end-session endpoint.
- Service-to-service calls remain on the internal scheme until a Client Credentials / service-account
  client is provisioned (not currently used); this is tracked as a follow-up, not a regression.
- The dev seed accounts and repository-known secret from ADR-0006 remain non-production only and are
  removed/disabled for any shared or production deployment (CR-IAM-HIGH-002 remains open until then).
