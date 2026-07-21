# Process Adapter

## Назначение
Изолировать платформу от Flowable REST API и предоставить доменные команды.

## Владеет
Mapping ticket/process, mapping task, idempotency, Flowable client, process projection events, authorization task commands.

## Use cases
StartAppealProcess, GetTicketProcessState, ListWorkItems, ClaimTask, CompleteTask, ReassignTask, HoldProcess, ResumeProcess, CorrelateCustomerReply, HandleEmailSent, PublishProjection.

## Ограничения
- frontend не вызывает Flowable;
- duplicate start защищен business key;
- временные ошибки retry;
- actions audited;
- no full documents in variables.

## Общие требования

- Python 3.12, FastAPI, Pydantic v2.
- Domain/application/infrastructure структура.
- Собственная БД/схема и пользователь.
- `/health/live`, `/health/ready`.
- Structured JSON logs и correlation ID.
- Alembic migrations.
- OpenAPI.
- Unit, integration и contract tests.
