# TASK 03 — Documents

## Цель
Безопасное MVP-хранение без MongoDB.

## Реализовать
Metadata, FileStorage protocol, LocalFileStorage, upload/stream/list/version, SHA-256, random key, limits, MIME, scan states, scanner interface, download audit, persistent volume, storage_backend.

## UI
Attachments, upload, preview, download, scan status, response document type.

## Acceptance
- restart не теряет файлы;
- other services use document ID only;
- no traversal;
- pending/infected inaccessible;
- hash verified;
- versions preserved;
- no binary events;
- GridFS can be added without API change.
