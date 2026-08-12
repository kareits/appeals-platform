# ADR-0012: Document Service storage boundary, authorization, and download hardening

- **Status:** Accepted
- **Related:** ADR-014 (file storage: local in the MVP, GridFS/Document API later); ADR-004 (data
  boundaries); ADR-007 (shared-library boundaries); ADR-0006 (dev auth and the authorization
  matrix); ADR-0008 (ticket-service independent authorization and trusted actor); docs/06
  (attachments, retention, audit); `chatgpt_docs/services/DOCUMENT_SERVICE.md`

## Context

TASK_03A-1 introduces the platform's file boundary: the only service that stores document bytes and
their metadata. Everything else — the Ticket Service, Flowable, the Mailbox Service, the frontend —
references a document by identifier only and never touches the filesystem (root `CLAUDE.md`).

ADR-014 already fixed the backend strategy (local filesystem in the MVP, an unchanged `document_id`
when GridFS or a corporate Document API is added later). Four questions it does not answer had to be
decided to build the service, and each of them is a security decision rather than a matter of taste:

1. **Who may read and write documents at all?** The IAM authorization matrix in force (TASK_01D)
   defines no `document:*` permission for any role, so a service enforcing one would deny every real
   caller.
2. **Who may reach a *particular* appeal's documents?** The DOCUMENT_SERVICE spec requires an "access
   check", and the regulated team/assignment/confidentiality rules are the Ticket Service's data.
   Enforcing only the coarse permission leaves an object-level authorization bypass — the defect the
   independent review raised as CR-DOC-HIGH-001 against the first implementation of this task.
3. **How are stored objects addressed**, given that a filename is untrusted client input?
4. **How is content served back** without turning stored evidence into a cross-site-scripting vector
   in the platform's own origin?
5. **When is a document downloadable**, given that antivirus scanning (docs/06 "no access before
   CLEAN") only arrives in TASK_03A-2?

## Decision

- **Independent security boundary.** The Document Service verifies the IAM-issued access token
  itself (fixed HS256 allowlist; signature, issuer, audience, expiry, and claim types), exactly as
  the Ticket Service does under ADR-0008. It imports no IAM code and reads no other service's
  database (ADR-004, ADR-007). A missing or invalid token is 401 with `WWW-Authenticate: Bearer`.
  Every operation is protected — there is no anonymous read path to file bytes.
- **Authorization on appeal permissions, not `document:*`.** Reading metadata, listing, and
  downloading require `ticket:read`; uploading and linking require `ticket:update`. Documents exist
  only as evidence attached to an appeal, so "may edit this appeal" is the right existing privilege,
  and reusing the claims keeps the IAM matrix (already reviewed and seeded) unchanged in EP-2.
  Dedicated `document:*` permissions are deferred to the IAM matrix revision that also brings the
  business RBAC matrix; the claim strings are the only coupling, and swapping them is a one-line
  change in `domain/permissions.py`.
- **Object-level access is delegated to the Ticket Service, not duplicated and not skipped.**
  Whether a caller may see *this* appeal's documents — and whether they may change what is attached
  to it — depends on team, assignment, and confidentiality, which are the Ticket Service's data. The
  Document Service asks it, over its public API and with the **caller's own token**, before serving,
  storing, or linking anything. The rules live in one place (ADR-0008) and no database is crossed.
  The decision sits behind a domain port (`domain/scope.py`), so a capability token or a policy
  service can replace the adapter later without touching the use cases.
- **Reads and writes ask different questions.** Ticket separates read scope from a deliberately
  narrower mutation scope: the controlled read/audit roles (ANALYST, AUDITOR) grant organization-wide
  read but no mutation scope, and AUDITOR may read a confidential appeal without being able to change
  it. Treating a successful read as permission to write would let one role's breadth combine with
  another role's `ticket:update` permission — the composite escalation Ticket prevents
  (CR-DOC-HIGH-002, CR-BFF-RR-HIGH-001). The port therefore has two operations
  (`ensure_appeal_read_access`, `ensure_appeal_write_access`); reads use the first, and upload, link
  (both the current appeal and the destination) use the second.
- **A read-only probe carries the decision.** Ticket exposes
  `GET /api/v1/tickets/{ticketId}/access` → `{canRead, canMutate}`, computed by the same
  `can_read_ticket`/`can_mutate_ticket` it enforces internally. It has no side effects, writes no
  audit record, and answers `false`/`false` both for an appeal outside the caller's scope and for one
  that does not exist, so it is not an existence oracle. Adding it required an additive change to the
  Ticket Service beyond this phase's nominal scope (user-approved); the alternative — inferring
  mutation rights from a read, or reimplementing the rules here — is exactly what created the
  finding.
- **Fail-closed on every path, and the decision is bound to its resource.** A denial is 403 with no
  detail about the appeal (so a caller cannot probe existence). Anything that is not a *complete*
  decision for *the appeal that was asked about* is **503**, never an implicit allow: a timeout, a
  connection failure, any non-200 status (including a 401 that reveals a token mismatch between the
  services), a wrong media type, a body missing either boolean, or a body whose `ticketId` is absent,
  malformed, or names a different appeal. A capability means nothing apart from the resource it was
  issued for, so a partial, stale, misrouted, or wrongly cached response cannot authorize anything
  (CR-DOC-MEDIUM-004). An unlinked document has no appeal to
  decide on, so it stays visible to, and modifiable only by, its uploader until it is linked.
- **Random storage keys, sanitized filenames.** An object's location is `YYYY/MM/<128 random bits>`,
  generated by the service and never derived from client input, with no file extension. The client's
  filename is sanitized (path components, control characters, and header-breaking characters
  removed) and kept as display metadata only. The storage key is never exposed through the API.
  Traversal is blocked twice: the key is validated against a strict pattern before a path is built,
  and the resolved path is then checked to be contained in the resolved storage root.
- **Downloads are always untyped attachments.** Content is served as `application/octet-stream` with
  `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`, regardless of the content
  type declared at upload (which is recorded but never trusted). Safe preview is EP-4.
- **A lifecycle gate now, scanning behind it later.** Only the `AVAILABLE` status is downloadable.
  TASK_03A-1 reaches `UPLOADING` → `AVAILABLE` (or `UPLOAD_FAILED`); TASK_03A-2 inserts the scan
  states before `AVAILABLE`, so the docs/06 rule "no access before CLEAN" is enforced by a gate that
  already exists rather than by new logic on the serving path.
- **Metadata first, bytes second.** The metadata row is committed as `UPLOADING` before the first
  byte is written and updated afterwards. An interrupted upload therefore leaves a discoverable row
  naming its storage key — never an untracked file on the volume — which is what makes storage and
  metadata reconcilable (and, in EP-4, cleanable).
- **A size ceiling from the start, applied to file bytes.** A configurable maximum (25 MiB by
  default) is enforced while streaming the file to storage. It deliberately does **not** count
  multipart framing: comparing the whole request length against it rejected valid in-limit files in a
  client-dependent band (CR-DOC-MEDIUM-001). Request-body-level protection belongs to the ingress;
  the MIME allowlist and per-type limits remain TASK_03A-2 scope.
- **Write-once linkage enforced by the database, not by a read-then-write check.** Attaching a
  document to an appeal is a single conditional `UPDATE` whose predicate accepts only an unlinked row
  or the same appeal, so two concurrent links to different appeals cannot both succeed — one wins and
  the other is a 409 (CR-DOC-MEDIUM-002). Evidence is never silently moved.
- **No events in TASK_03A-1.** `document.uploaded.v1` and `document.available.v1` are emitted in
  TASK_03A-2 together with hashing and scanning, so no consumer ever observes a document before its
  content is verified. No event or message ever carries file bytes (root `CLAUDE.md`).

## Alternatives considered

- **Add `document:read`/`document:upload` to the IAM matrix now.** More precise semantically, but it
  changes an already-reviewed service outside the phase's allowed scope (`CONTEXT_LOADING_GUIDE`,
  EP-2), requires a seed/token/contract change in IAM, and buys nothing until the business RBAC
  matrix defines which roles hold them. Deferred, not rejected.
- **Permission-level checks only, with the object-level gap documented.** This was the first
  implementation and the independent review rejected it (CR-DOC-HIGH-001): documentation is not an
  authorization control, and a valid employee or first-line token could read any appeal's evidence.
  Superseded by the delegated decision above.
- **Reimplement the team/assignment/confidentiality rules inside the Document Service.** Avoids the
  synchronous dependency, but duplicates a regulated policy in a second place with a second source of
  truth — guaranteed drift the moment the business matrix lands. Rejected.
- **Reuse the plain `GET /api/v1/tickets/{ticketId}` for both reads and writes.** This was the first
  remediation and the review rejected it (CR-DOC-HIGH-002): that route answers the *read* question, so
  an audit role's breadth would authorize evidence mutations that Ticket itself refuses. Superseded by
  the capability probe.
- **Approximate the mutation rule from the token's roles** (for example, refuse writes when the token
  carries a broad-read-only role without an organization-wide mutation role). No change to Ticket, but
  it reproduces part of ADR-0008's role sets in a second place and cannot evaluate team or ownership
  facts at all. Rejected as a permanent rule.
- **Restrict reads to the uploader plus oversight roles**, using only data this service owns. Cheap
  and fail-closed, but wrong for the workflow: a colleague on the same team (or the mailbox service
  attaching an inbound file) could not read evidence they legitimately handle. Rejected as a
  permanent rule; it survives only as the narrow fallback for a document that is not linked yet.
- **Serve the stored content type (with `Content-Disposition: inline`) for previewable types.**
  Rejected: the type is client-declared and unverified, so an uploaded HTML or SVG file would run in
  the platform's origin. Preview needs sanitization and a separate origin — EP-4.
- **Write bytes first and insert metadata afterwards.** Simpler, but a crash between the two leaves
  an orphan file that nothing references and no job can attribute.
- **Derive the storage path from the appeal and filename** (`<ticketId>/<filename>`). Rejected:
  human-meaningful paths leak business data on the volume, collide, and put untrusted input into a
  path — the exact combination docs/06 forbids.

## Consequences

- The Document Service owns its database (`document` table) and a persistent storage volume; a
  restart does not lose files, and the compose stack has a one-shot migration job like every other
  service.
- Other services stay decoupled: `ticket_id` and `message_id` are opaque UUID columns with no
  foreign key, so document metadata can be migrated or backed up independently.
- **The Ticket Service becomes a runtime dependency of every document operation that names an
  appeal.** When it is unavailable, documents are unreadable (503) rather than open — the intended
  trade-off. The timeout is bounded (5 s by default), the decision travels with the correlation ID so
  it is traceable across both services, and no service credentials exist to be stolen because the
  caller's own token is forwarded.
- **Ticket owns one more public operation** (`getTicketAccess`), which other services may reuse for
  the same purpose. It exports a decision, never data: the response contains no appeal content.
- A future caching layer for scope decisions would trade freshness for latency and must not be added
  without an explicit decision: a stale allow is exactly the failure this ADR is closing.
- Dedicated `document:*` permissions remain a follow-up with the IAM matrix revision; they refine the
  first (coarse) layer, not the object-level decision.
- Adding GridFS later means implementing the `FileStorage` port and setting `storage_backend`
  per document; identifiers, the HTTP contract, and the lifecycle gate stay unchanged (ADR-014).
