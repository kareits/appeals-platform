# ADR-0005: SLA policy, business calendar, and platform timezone

- **Status:** Accepted
- **Related:** DECISION_LOG ADR-009 (SLA/business-calendar ownership); ADR-003 (UTC in storage)

## Context

Appeal deadlines are regulatory data and part of the ticket card. The Ticket Service must compute
`internal_due_at` (internal SLA) and `legal_due_at` (regulatory term); Flowable later sets timers
from these values and Notification alerts on them (ADR-009). Two facts complicate the computation:
the exact KZ SLA calendar (working hours, holidays, the precise regulatory term) is not yet
confirmed (Q-C1), and timestamps are stored in UTC (ADR-003) while business dates must reflect the
Kazakhstan business timezone.

## Decision

- **Ownership:** the Ticket Service computes both deadlines at registration from a **versioned SLA
  policy** and a **business calendar**, and stamps `sla_policy_version` on the ticket for
  provenance. Flowable sets timers from the computed values; Notification notifies (ADR-009).
- **SLA policy** (`domain/sla.py`): a versioned `SlaPolicy` (reaction hours, resolution hours,
  regulatory-term days). The temporary default `v1-temp` uses docs/01 values (reaction 12h,
  resolution 24h) and a placeholder 15-calendar-day regulatory term (Q-C1). `internal_due_at` is
  derived from the resolution hours; `legal_due_at` from the regulatory-term days.
- **Business calendar** (`domain/business_calendar.py`): a `BusinessCalendar` protocol with a
  temporary `ContinuousCalendar` (24/7, no weekends or holidays, Q-C1). A KZ working-hours/holiday
  calendar replaces it later without changing the SLA computation.
- **Platform timezone** (`domain/timezone.py`): timestamps are **stored in UTC** (ADR-003), but
  business *dates* and working-hours math use the platform business timezone — Kazakhstan
  (Astana/Almaty), UTC+5, no daylight saving. The zone is configurable via the platform-wide
  `PLATFORM_TIMEZONE` environment variable (default `Asia/Almaty`); the retention date is computed
  from the closure instant converted to this timezone, so a late-evening closure is not counted
  against the previous day.

## Alternatives considered

- **Compute deadlines in a separate SLA service:** rejected — excessive for MVP; deadlines belong
  to the card the Ticket Service already owns (ADR-011 rationale).
- **Store local time instead of UTC:** rejected — violates ADR-003 and breaks cross-service
  ordering; convert to the business timezone only where a business date is needed.
- **Hard-code the timezone:** rejected — a configurable `PLATFORM_TIMEZONE` keeps deployments
  flexible and documents the platform-wide convention.
- **Working-hours calendar now:** deferred — the confirmed KZ calendar (Q-C1) is not available; the
  protocol lets it drop in later.

## Consequences

- A `SlaPolicy`, `BusinessCalendar` protocol, and timezone helper exist from EP-1; `internal_due_at`
  and `legal_due_at` are populated at registration and exposed on the card.
- The temporary policy and continuous calendar are clearly marked and versioned, so replacing them
  is a localized change plus a new policy version.
- `PLATFORM_TIMEZONE` is documented in `.env.example` as a shared, platform-wide setting.

## Follow-up (deferred to EP-3)

Business/regulatory policy **values** (SLA reaction/resolution, the regulatory-term days, the
retention period, business-calendar working hours and KZ holidays, and the WAITING/HOLD escalation
durations) are currently code-level defaults in this service. They will be centralized into a
dedicated, versioned **business-policy configuration** owned by the Ticket Service — separate from
deployment/infra settings (`env`/`Settings`) — with a later move to a database table editable by the
ADMIN role (docs/00: ADMIN owns SLA and dictionaries). The DMN `appeal_routing` decision only
**selects** which policy/ruleset applies (returning a policy code, `internal_sla_policy`); the policy
values remain owned and resolved by the Ticket Service, never stored in or read from Flowable
(ADR-009, ADR-011). This is scheduled for EP-3, where the DMN policy selection is introduced.

## Migration impact

Adds `sla_policy_version`, `response_sent_at`, and `no_response_reason` columns (migration 0004).
Existing tickets keep null deadlines until recomputed; no backfill is required in MVP.

## Rollback considerations

The policy and calendar are additive and versioned; a superseding ADR can introduce a new policy
version or a real working-hours calendar without breaking stored deadlines.
