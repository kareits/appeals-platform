# 04. Flowable BPMN/DMN

## Источник истины

Flowable владеет состоянием процесса, активной задачей, назначением, таймерами и согласованием. Ticket Service хранит read projection.

## Процесс `appeal_restructuring_v1`

1. Appeal registered.
2. User Task: классификация.
3. DMN: маршрутизация.
4. User Task: идентификация клиента/договора.
5. User Task: проверка комплектности.
6. Gateway: документы полные?
7. Если нет:
   - подготовить запрос;
   - проверить/утвердить;
   - отправить;
   - WAITING_FOR_CUSTOMER;
   - timer 5 days;
   - message event при ответе клиента;
   - timeout → reminder-or-close.
8. User Task: анализ реструктуризации.
9. User Task: фиксация решения.
10. Gateway: требуется согласование?
11. User Task: согласование руководителя.
12. User Task: подготовка PDF.
13. User Task: проверка финального ответа.
14. Service Task: запрос отправки.
15. Wait for email.sent/email.failed.
16. User Task: закрытие.
17. End.
18. Необязательный post-close analysis subprocess.

## ON_HOLD

- обязательная причина;
- timer 15 days;
- уведомления;
- задача после timer;
- resume возвращает на предыдущую стадию.

## DMN входы

`product_code`, `classifier_code`, `category`, `source_channel`, `complaint_flag`, `ombudsman_flag`, при необходимости `amount_range`, `region`.

Выходы:
`team_code`, `priority_code`, `internal_sla_policy`, `approval_policy`, `required_document_ruleset`.

## Process Adapter API

- start_process;
- get_process_state;
- list_user_tasks;
- claim/unclaim;
- complete_task;
- reassign;
- put_on_hold/resume;
- record_customer_reply;
- handle_email_sent;
- controlled migrate.

## Variables

Разрешены идентификаторы, коды и небольшие флаги. Запрещены PDF, изображения, полные письма, полная карточка клиента и большие JSON.

## Версионирование

Новые deployment создают новые версии. Активные процессы не мигрируются автоматически. BPMN/DMN хранятся в Git.
