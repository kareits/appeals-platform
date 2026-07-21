# Notification Service

## Назначение
Уведомления сотрудникам.

## MVP channels
In-app, позднее corporate email.

## Consumes
process.task_created, assignment_changed, deadline.warning, deadline.breached, customer.reply_received, response.returned.

## Produces
notification.delivered, notification.failed.

## Требования
Idempotency, retry, read/unread, ticket link. Клиентские письма отправляет только Mailbox Service.

## Общие требования

- Python 3.12, FastAPI, Pydantic v2.
- Domain/application/infrastructure структура.
- Собственная БД/схема и пользователь.
- `/health/live`, `/health/ready`.
- Structured JSON logs и correlation ID.
- Alembic migrations.
- OpenAPI.
- Unit, integration и contract tests.
