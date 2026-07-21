# 08. Тестирование и приемка

## Уровни

Unit, integration, contract, E2E, security.

## Критические E2E

1. Ручная регистрация → задача → решение → PDF → закрытие → retention.
2. Email → тикет → вложения → reply linking → ответ → timeline.
3. WAITING_FOR_CUSTOMER → timer или customer reply.
4. ON_HOLD → обязательная причина → timer → resume.
5. Reassignment с сохранением истории и прав.
6. Запрет закрытия без решения.
7. Запрет физического удаления.
8. First-line read-only.
9. Filtered export и audit.
10. Duplicate external email ID не создает дубль.

## Definition of Done

Acceptance criteria, tests, migrations, lint/type, contracts, config docs, no secrets, Docker build, health endpoints, compose smoke test.
