# 03. Архитектура

## Стиль

Крупноблочная микросервисная архитектура в монорепозитории. Границы используются для владения данными, независимого тестирования и ограничения контекста ИИ-агента.

## Компоненты

- API Gateway/BFF — единая точка frontend и агрегация.
- IAM Service — пользователи, роли, команды, OIDC.
- Ticket Service — реестр, карточка, классификация, решение, аналитика.
- Process Adapter — доменный API поверх Flowable.
- Flowable — BPMN/DMN, user tasks, timers, assignments, approvals.
- Mailbox Service — Exchange, цепочки, получение/отправка.
- Document Service — файлы, версии, хеш, scan/download audit.
- Notification Service — внутренние уведомления.
- Integration Service — адаптер к учетной системе.

## Хранилища MVP

- один PostgreSQL-кластер;
- отдельная database/schema и DB-user на сервис;
- RabbitMQ;
- persistent file volume;
- отдельная БД Flowable.

Cross-database joins запрещены.

## Файлы

MVP: `LocalFileStorage`/`NetworkFileStorage`, метаданные PostgreSQL, `storage_backend=local`.

Позднее: `GridFSStorage` или корпоративный Document API, dual-read и фоновая миграция при неизменном `document_id`.

## Коммуникации

REST:
- BFF → сервисы;
- Process Adapter → Flowable;
- Mailbox → Document;
- сервисы → Integration.

RabbitMQ:
- mail.received;
- ticket.created/updated;
- process.started/status_changed/task_created;
- document.available;
- notification.requested;
- email.send_requested/sent;
- deadline.warning/breached.

## Надежность

- Transactional Outbox;
- idempotent consumers;
- retries/backoff;
- DLQ;
- correlation ID;
- health/readiness;
- optimistic locking;
- unique external message IDs;
- Exchange reconciliation.

## Не использовать в MVP

Kubernetes, service mesh, Kafka, event sourcing, полный CQRS, GraphQL, отдельные репозитории, несколько backend-языков, Celery без обоснования, Windmill, Redis без конкретного use case.
