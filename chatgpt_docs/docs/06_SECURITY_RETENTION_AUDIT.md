# 06. Безопасность, хранение и аудит

## Auth

Цель — корпоративный OIDC/SSO. Dev auth разрешен только вне production. Production проверяет signed JWT и разделяет user/service credentials.

## Authorization

RBAC + подразделение/команда + продукт/категория + принадлежность тикета + confidentiality.

## Персональные данные

- маскирование ИИН/БИН;
- отсутствие полных идентификаторов в логах;
- TLS;
- backup encryption;
- контролируемые exports;
- аудит просмотра и скачивания.

## Вложения

- allowlist;
- MIME validation;
- size limits;
- path traversal protection;
- random storage key;
- antivirus state;
- до CLEAN файл недоступен;
- безопасный preview.

## Email

- подтвержденный получатель;
- фиксированный sender;
- header injection protection;
- idempotent send;
- delivery attempts;
- AI/template не выбирает адрес.

## Audit

Фиксируются входы, просмотры, изменения, назначения, статусы, решения, загрузки/скачивания, exports, отправки, администрирование, retention/legal hold, AI run и review.

## Retention

- минимум 5 лет;
- `retention_until`;
- `legal_hold`;
- soft delete не является purge;
- purge — привилегированная job с отчетом и audit;
- согласованное удаление документов.

## Backup

PostgreSQL, file volume и Flowable DB должны восстанавливаться согласованно. До production определить RPO/RTO и регулярно тестировать restore.
