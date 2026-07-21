# DEPENDENCY_MAP — Dependency Map

Dependencies between services, infrastructure, tasks, and external integrations.
Legend: **[M]** mandatory · **[O]** optional · **[X]** external blocker · **[F]** replaceable by
mock/fake.

## 1. Inter-service dependencies

| Service | Depends on | Type | Mechanism |
|---|---|---|---|
| BFF | IAM, Ticket, Process Adapter, Mailbox, Document, Notification | [M] | REST (workspace aggregation) |
| Ticket Service | Process Adapter (projection), Integration | [M] / [O][F] | `process.*` events; REST to Integration (fake) |
| Process Adapter | Flowable | [M] | REST |
| Mailbox Service | Document Service, Ticket Service, Process Adapter | [M] | REST (attachments), events (ticket creation, reply/send) |
| Document Service | — | — | standalone (local storage) |
| Notification Service | Ticket/Process/Mail/Response events | [M] | subscription to canonical events |
| Integration Service | external accounting system | [X][F] | `FakeCoreSystemAdapter` until access |
| IAM Service | corporate IdP (OIDC) | [X][F] | dev-auth until access |

**Invariants:** no access to another service's DB, no cross-database joins, no direct reads of
the Flowable DB (ADR-004, ADR-011). All inter-service data via REST/events.

## 2. Infrastructure dependencies

| Component | Needed for | Type |
|---|---|---|
| PostgreSQL (cluster, separate DB/schema per service) | all services | [M] |
| RabbitMQ | events, Transactional Outbox, DLQ | [M] |
| Flowable + separate Flowable DB | Process Adapter, EP-3, EP-0F | [M] |
| Reverse proxy | single entry point | [M] |
| Persistent file volume | Document Service | [M] |
| Docker Compose | local MVP run | [M] |
| Secrets manager / TLS | production | [M] (from EP-7) |
| Antivirus engine | Document hardening | [O][F] until EP-4 (interface + mock) |

## 3. Task dependencies (execution phases)

```
EP-0 (TASK_00A–C)
 ├─> EP-0F (TASK_00D, Flowable spike)
 └─> EP-1 (TASK_01)
        └─> EP-2 (TASK_03A) ──┬─> EP-3 (TASK_02) ──> EP-4 (TASK_03B)
                               │        │
                               └────────┴─> EP-5 (TASK_04)
                                                 └─> EP-6 (TASK_05) ──> EP-7 (TASK_06)
```

| Task | Must follow | Reason |
|---|---|---|
| EP-0F | EP-0 | needs a running Flowable |
| EP-1 | EP-0 | infrastructure, libs, IAM dev-auth |
| EP-2 | EP-0 (+ EP-1 for ticket_id) | file boundary |
| EP-3 | EP-1, EP-2, EP-0F | card projection, documents for completeness, validated Flowable loop |
| EP-4 | EP-2, EP-3 | hardening on top of foundation and process |
| EP-5 | EP-2, EP-3 | attachments via Document Service, reply/send via the process |
| EP-6 | EP-1..EP-5 | read-model from all event flows |
| EP-7 | EP-0..EP-6 | production on top of everything |

## 4. External integrations

| Integration | Status | Blocker | MVP replacement |
|---|---|---|---|
| Exchange / `dolg@solva.kz` | [X][F] | Exchange type, shared mailbox, API, auth, test mailbox, sender permissions | `FakeMailboxProvider` + EML fixtures + outbound capture |
| Corporate SSO/OIDC (AD/Entra) | [X][F] | IdP access, client credentials, group mapping | dev-auth (non-production only) |
| Accounting system (core) | [X][F] | API contract, access | `FakeCoreSystemAdapter` + manual client/contract entry |
| Antivirus | [O][F] | engine choice | scanner interface + mock status (real one — EP-4/EP-7) |

## 5. Components replaceable by mock/fake

- `FakeMailboxProvider` (EP-5) → real Exchange adapter (post-access).
- dev-auth (EP-1) → OIDC adapter (EP-7).
- `FakeCoreSystemAdapter` (as needed in EP-1/EP-3) → real Integration adapter (post-access).
- mock scan status (EP-2) → full antivirus (EP-4).
- `LocalFileStorage` (EP-2) → `GridFSStorage`/Document API (post-MVP, ADR-014).

## 6. Critical path

`EP-0 → EP-1 → EP-2 → EP-3 → EP-5 → EP-6 → EP-7`.
EP-0F runs in parallel to de-risk Flowable early; EP-4 may sit between EP-3 and EP-5 but not later
than EP-5 (attachment security is preferable before production mail — EP-2 is the minimum).
