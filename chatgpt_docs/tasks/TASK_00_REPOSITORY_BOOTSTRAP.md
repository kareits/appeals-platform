# TASK 00 — Repository Bootstrap

## Цель
Создать монорепозиторий и инфраструктурный фундамент без бизнес-функций.

## Реализовать
- каталоги apps/services/orchestration/contracts/infrastructure;
- Python workspace и service template;
- Dockerfiles;
- Docker Compose: PostgreSQL, RabbitMQ, Flowable, reverse proxy;
- health endpoints;
- logging/correlation ID;
- event envelope schema;
- Ruff, type checker, pytest;
- CI;
- `.env.example`;
- Makefile/task runner: up/down/test/lint/migrate.

## Acceptance
- `docker compose up --build` запускается;
- health доступны;
- Flowable доступен только в dev/private network;
- sample migration проходит;
- CI выполняет lint/type/test;
- secrets отсутствуют.
