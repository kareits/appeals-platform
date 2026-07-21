# TASK 01 — Ticket and Manual Workflow

## Цель
Ручная регистрация и регуляторный журнал до Flowable.

## Реализовать
Ticket data model/migrations, create/update/classification/comments/search, registration number, decisions, close validation, retention, audit, dictionaries.

IAM: dev users/roles и authorization matrix.

BFF/frontend: login dev, list, manual form, card, comments, decision.

## Временный workflow
Допустим placeholder status, но API должен быть готов к Flowable projection.

## Acceptance
- регистрация любого письменного обращения;
- условные поля nullable;
- обязательные валидируются;
- уникальный номер;
- search/filter;
- first line read-only;
- close blocked without decision;
- audit;
- regulatory tests.
