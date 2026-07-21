# Integration Service

## Назначение
Антикоррупционный слой к внутренним системам МФО.

## MVP
Interface, FakeCoreSystemAdapter, manual client/contract fields.

## Future
Find client by IIN, contracts, debt, delinquency, prior restructurings, product sync.

## Требования
No external schema leakage, timeout/retry, access audit, graceful degradation, no direct DB integration without approved contract.

## Общие требования

- Python 3.12, FastAPI, Pydantic v2.
- Domain/application/infrastructure структура.
- Собственная БД/схема и пользователь.
- `/health/live`, `/health/ready`.
- Structured JSON logs и correlation ID.
- Alembic migrations.
- OpenAPI.
- Unit, integration и contract tests.
