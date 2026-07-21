# 02. Словарь данных

## Ticket

| Поле | Тип | Обязательно | Источник |
|---|---|---:|---|
| id | UUID/ULID | да | система |
| registration_number | string | да | Ticket Service |
| received_at | datetime | да | email/ручной ввод |
| registered_at | datetime | да | система |
| source_channel_code | string | да | система/сотрудник |
| subject | string | да | письмо/сотрудник |
| description | text | да | письмо/сотрудник |
| product_code | string | да | сотрудник/API |
| classifier_code | string | да | сотрудник/будущий AI |
| priority_code | string | да | правило/сотрудник |
| current_status_code | string | да | проекция Flowable |
| current_stage_code | string | да | проекция Flowable |
| current_team_id | UUID nullable | нет | Flowable |
| current_assignee_id | UUID nullable | нет | Flowable |
| legal_due_at | datetime nullable | нет | правило |
| internal_due_at | datetime nullable | нет | SLA |
| decision_code | string nullable | до закрытия | сотрудник |
| decision_summary | string nullable | до закрытия | сотрудник |
| decision_text | text nullable | до закрытия | сотрудник |
| decision_at | datetime nullable | до решения | система |
| decision_by | UUID nullable | до решения | система |
| closure_reason_code | string nullable | до закрытия | сотрудник |
| closed_at | datetime nullable | нет | Flowable |
| retention_until | date | после закрытия | система |
| legal_hold | bool | да | комплаенс |
| version | integer | да | optimistic lock |

## Applicant

- applicant_type: CONSUMER / REPRESENTATIVE;
- full_name nullable;
- identifier_type: IIN / BIN nullable;
- identifier_value nullable, защищенное/маскируемое;
- email nullable;
- phone nullable;
- gender_code nullable;
- age/birth_date nullable;
- region_code nullable;
- data_source: APPEAL / CORE_SYSTEM / MANUAL;
- representative_basis nullable.

## Ticket relation

- DUPLICATE_OF;
- REPEAT_OF;
- CONTINUATION_OF;
- COMPLAINT_ABOUT;
- RELATED_CONTRACT;
- PARENT;
- CHILD.

## Mail message

- id, ticket_id;
- direction;
- external_message_id;
- internet_message_id;
- conversation_id;
- in_reply_to, references;
- from, to, cc;
- subject;
- body_html, body_text;
- received_at/sent_at;
- delivery_status;
- raw_eml_document_id nullable.

## Document metadata

- id;
- ticket_id;
- message_id nullable;
- original_filename;
- storage_backend;
- storage_key;
- content_type;
- size_bytes;
- sha256;
- document_type_code;
- version;
- scan_status;
- status;
- created_by;
- created_at;
- deleted_at nullable;
- migrated_at nullable.

## Аналитика

### SystemicIssue
`id`, `title`, `description`, `root_cause_code`, `root_cause_text`, `severity_code`, `owner_department_id`, `detected_at`, `status`, `closed_at`.

### CorrectiveAction
`id`, `systemic_issue_id`, `action_type`, `description`, `owner_id`, `due_at`, `status`, `result`, `completed_at`.

### Satisfaction
`ticket_id`, `survey_version`, `channel`, `sent_at`, `received_at`, `score`, `comment`.

## AI-ready

Позднее:
- AI_RUN;
- DOCUMENT_EXTRACTION;
- EXTRACTED_FIELD;
- COMPLETENESS_CHECK;
- RESPONSE_DRAFT.

AI-значения не перезаписывают подтвержденные поля без отдельного подтверждения.
