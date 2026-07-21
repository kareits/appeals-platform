# TASK 04 — Exchange Email

## Цель
Email integration через provider abstraction.

## До разработки production adapter
Уточнить Exchange type, shared mailbox, API, auth, test mailbox и sender permissions.

## Реализовать
Fake provider/EML fixtures, provider interface, sync/webhook, checkpoint, dedup, body, attachments, mail.received, ticket creation, reply linking, outbound send, idempotency, attempts, reconciliation, ticket number in subject.

## Acceptance
- fixture creates one ticket;
- attachments linked;
- duplicate ignored;
- reply linked;
- approved response sent once;
- failure retries and visible;
- complete timeline.
