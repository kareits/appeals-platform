# Document Service

## Назначение
Единая граница хранения и доступа к файлам.

## MVP
PostgreSQL metadata, local/network filesystem adapter, persistent volume, `storage_backend=local`.

## Future
GridFS adapter, dual backend, migration job, неизменный document id.

## Use cases
UploadDocument, StreamDocument, ListTicketDocuments, AddVersion, LinkDocument, MarkScanResult, SoftDeleteDocument, AuditDownload.

## Storage interface
save, open/stream, delete, exists, hash verification.

## Security
Filename sanitization, random storage key, MIME validation, size limits, antivirus status, access check, no binary in RabbitMQ.

## Statuses
UPLOADING, UPLOADED, PENDING_SCAN, CLEAN, AVAILABLE, INFECTED, UPLOAD_FAILED, DELETED.

## Общие требования

- Python 3.12, FastAPI, Pydantic v2.
- Domain/application/infrastructure структура.
- Собственная БД/схема и пользователь.
- `/health/live`, `/health/ready`.
- Structured JSON logs и correlation ID.
- Alembic migrations.
- OpenAPI.
- Unit, integration и contract tests.
