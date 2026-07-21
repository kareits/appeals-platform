# API Gateway / BFF

## Назначение
Единый API для frontend.

## Обязанности
Auth, authorization context, workspace aggregation, error normalization, correlation ID, optional rate limiting.

## Workspace
Ticket card, Flowable task/state, mail timeline, documents, client/contract, notifications.

## Ограничения
Не хранить доменные данные и не дублировать бизнес-логику. Partial read failures обозначаются в ответе.

## Общие требования

- Python 3.12, FastAPI, Pydantic v2.
- Domain/application/infrastructure структура.
- Собственная БД/схема и пользователь.
- `/health/live`, `/health/ready`.
- Structured JSON logs и correlation ID.
- Alembic migrations.
- OpenAPI.
- Unit, integration и contract tests.
