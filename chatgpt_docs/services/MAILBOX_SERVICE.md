# Mailbox Service

## Назначение
Интеграция с `dolg@solva.kz`.

## До получения доступа
Реализовать provider interface, FakeMailboxProvider, EML fixtures и outbound capture.

## Provider methods
Subscribe/poll, list since checkpoint, get body/attachments, send, delivery status, save checkpoint.

## Incoming
Deduplication, body html/text, optional raw EML, attachments through Document Service, mail.received, reply linking, reconciliation.

## Outgoing
Только approved request, verified recipient, fixed sender, documents by ID, idempotency, delivery attempts, sent/failed events.

## Security
Header injection protection, no arbitrary recipient, no direct file paths.

## Общие требования

- Python 3.12, FastAPI, Pydantic v2.
- Domain/application/infrastructure структура.
- Собственная БД/схема и пользователь.
- `/health/live`, `/health/ready`.
- Structured JSON logs и correlation ID.
- Alembic migrations.
- OpenAPI.
- Unit, integration и contract tests.
