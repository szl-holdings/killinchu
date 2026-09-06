# Killinchu Defend — production identity and authorization boundary

Status: **specification complete; deployed identity is NOT VERIFIED**  
Parent gate: `#399`  
Seam decision: `#401`

## 1. Authority boundary

Killinchu does not issue end-user credentials. Production validates identity
assertions from one explicitly configured external OpenID Connect provider.
Authentication never grants an effector by itself. Every request still passes
tenant isolation, role authorization, approval separation, scope allowlists,
rehearsal policy, and the public non-effecting boundary.

Caller-supplied names, e-mail addresses, tenant identifiers, roles, and approval
labels are display attributes only. They are never authorization roots.
Production identity remains `NOT_VERIFIED` until one exact protected source and
deployed revision passes the live tests in §10.

## 2. OIDC validation

The provider is configured with fixed values supplied as deployment secrets or
non-secret deployment configuration:

- `OIDC_ISSUER_URL` — exact issuer string;
- `OIDC_CLIENT_ID` — exact audience;
- an allowlisted tenant-claim name;
- fixed authorization, token, JWKS, introspection, and revocation endpoints
  discovered only from the exact issuer document or pinned configuration.

Every accepted token must satisfy all of these checks:

1. `iss` exactly equals `OIDC_ISSUER_URL` after no caller-controlled rewriting;
2. `aud` contains exactly the registered client audience required by the route;
3. the signature verifies against the provider JWKS;
4. only `RS256` or `ES256` is accepted unless a separate reviewed algorithm
   change is merged; `none` and all symmetric `HS*` algorithms are rejected;
5. `exp`, `nbf`, and `iat` are present, well-typed, and evaluated against a
   bounded monotonic clock policy; expired tokens have zero acceptance leeway;
6. `sub`, tenant claim, and `jti` are present and non-empty;
7. authorization-code flows require single-use server-side `state` and `nonce`;
8. an unknown `kid` triggers one bounded JWKS refresh no more often than every
   five minutes; failure remains a rejection;
9. retired or revoked keys, issuers, clients, sessions, and tokens fail closed.

Issuer metadata, JWKS documents, and introspection responses have bounded sizes,
timeouts, cache lifetimes, and redirect policies. TLS verification cannot be
disabled. Bearer tokens, authorization codes, client secrets, and private keys
are never logged or written into receipts.

## 3. Immutable principal identity

The authorization identity root is the tuple `(issuer, sub)`. Killinchu derives
`principal_id` as UUIDv5 over a fixed namespace and the canonical bytes of that
tuple. Display name and e-mail may change without changing the principal.

Every durable session, case, analysis, approval request, approval vote,
rehearsal, idempotency record, backup/restore receipt, and receipt-chain event
stores `principal_id`. Historical rows are not rewritten when provider display
attributes change.

The hash of `jti` may be retained for revocation correlation. The bearer token
itself is never stored at rest.

## 4. Tenant identity and isolation

`tenant_id` comes from one configured provider claim. It is normalized through a
fixed, reject-on-ambiguity mapping maintained by the operator; it is never read
from the request path, query string, JSON body, or caller-selected header.

Every domain table and idempotency record carries `tenant_id`. Repository/service
methods require a tenant context and emit tenant predicates by construction.
Missing tenant context is a programming error that fails closed. Database
constraints and row-level security are used where the selected production
provider supports them, but application queries remain tenant-scoped even when
row-level security is present.

Cross-tenant access is unavailable to ordinary roles. The auditor role may read
across tenants only through a separate fixed route and explicit audit scope; it
cannot mutate. Every cross-tenant read records actor, purpose, tenant set,
filters, result count, source revision, and receipt identity without recording
sensitive record bodies.

## 5. Deny-by-default RBAC

The production role matrix is fixed:

| Role | Allowed capability |
|---|---|
| `analyst` | read tenant cases and receipts; submit bounded analyses |
| `requester` | create tenant cases and request approvals |
| `approver` | approve or reject eligible requests from another principal |
| `auditor` | read-only evidence access; no state mutation |
| `operator` | migrations, deployment, backup/restore, and incident controls |

Unknown roles, missing roles, malformed role claims, and role combinations not
present in the reviewed matrix are denied. A route declares its capability; the
middleware maps that capability to the matrix. Handlers do not invent local
role checks.

Operator authority does not imply analyst, requester, or approver authority.
Emergency access requires a separate break-glass policy with expiry, reason,
independent approval, tripwire alert, and immutable receipt.

## 6. Requester and approver separation

The immutable requester principal is written when a case or approval request is
created. An approval from that same principal is rejected even when display
name, e-mail, role order, session, or token changes. High-blast-radius scopes
retain the existing two-distinct-approver rule.

The production database enforces separation through constraints or a transaction
trigger in addition to application checks. The rejection itself emits an audit
event. Denied, expired, or revoked requests are terminal and must be re-requested;
they are never revived by changing a vote row.

## 7. Session and revocation behavior

A session expires after 12 hours of inactivity and after 7 days absolute,
whichever occurs first. State-changing routes validate current token/session
status on every request. Read routes may cache a successful introspection result
for at most 60 seconds; revocation or security events invalidate that cache.

Session state contains only the immutable principal, tenant, bounded role set,
issued/last-seen/absolute-expiry times, provider identity, and a non-reversible
`jti` correlation value. Session fixation is prevented by rotating the local
session identifier after authentication and privilege changes.

Logout invalidates the local session immediately and invokes provider revocation
when the provider supports it. Provider unavailability on a state-changing route
fails closed rather than treating an old cached answer as current.

## 8. Rate limits

The minimum production limits are:

| Route class | Limit |
|---|---:|
| read | 100 requests/minute/principal |
| state changing | 20 requests/minute/principal |
| approval | 5 requests/minute/principal |

Limits are additionally bounded by tenant and source address to prevent one
principal or tenant from exhausting the service. Counters use a durable or
shared backend in production; an in-process counter is demo-only. Rejections
return a typed envelope and bounded retry time without disclosing account or
tenant existence.

## 9. Audit and receipt-chain events

Authentication success/failure, issuer and audience rejection, unknown key,
revocation, session creation/expiry, authorization allow/deny, tenant-scope
denial, rate-limit rejection, role change, break-glass use, approval separation,
and provider-health transitions emit structured events.

Events contain typed reason codes, immutable principal and tenant identifiers,
route capability, policy version, source revision, trace identity, and receipt
identity. They do not contain raw tokens, authorization codes, secrets, full
provider documents, or sensitive request bodies.

## 10. Live acceptance before production readiness

The identity portion of `#399` remains open until one exact protected source and
deployed revision proves all of the following:

- valid issuer/audience/signature acceptance;
- rejection of wrong issuer, wrong audience, expired/not-yet-valid tokens,
  `none`, `HS*`, malformed claims, unknown and retired keys;
- witnessed JWKS rotation and bounded unknown-`kid` refresh;
- single-use state/nonce and replay rejection;
- immutable principal continuity across display-attribute changes;
- cross-tenant read and mutation denial at service and database boundaries;
- every role allow/deny case, including unknown and combined roles;
- requester/approver and two-approver separation under concurrency;
- inactivity, absolute expiry, logout, introspection failure, and revocation;
- distributed rate limits and immutable audit receipt verification;
- no bearer token or secret in logs, traces, database rows, or receipts.

Until that evidence exists, the truthful state is:

```text
production_oidc: NOT_VERIFIED
production_tenant_isolation: NOT_VERIFIED
production_rbac: NOT_VERIFIED
public_effectors: DISABLED
```

## 11. Mapping to `#399`

| `#399` requirement | Binding in this document |
|---|---|
| issuer, audience, signature, expiry, nonce/state, rotation | §2 |
| immutable identity on every durable record | §3 |
| tenant isolation and role matrix | §§4–5 |
| requester/approver separation | §6 |
| session expiry and revocation | §7 |
| rate limits and audit without token storage | §§8–9 |
| exact deployed proof | §10 |
