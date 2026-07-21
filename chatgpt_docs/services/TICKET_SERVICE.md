# Ticket Service

## Назначение
Регуляторный реестр и карточка обращения.

## Владеет
Ticket, applicant/representative, classifications, dictionaries, decision, related tickets, comments, systemic issues, corrective actions, satisfaction, workflow projection.

## Не владеет
Почтовой доставкой, файлами, полной Flowable history и корпоративными credentials.

## Use cases
CreateManualTicket, CreateTicketFromMail, UpdateTicketDetails, ClassifyTicket, RecordDecision, AddComment, LinkTicket, UpdateWorkflowProjection, CreateSystemicIssue, AddCorrectiveAction, ExportTickets.

## Инварианты
- уникальный registration number;
- обязательный received_at;
- product/classifier/channel до рассмотрения;
- status меняется только через projection;
- close требует decision и closure reason;
- demographics nullable;
- retention устанавливается при закрытии;
- optimistic locking.

## Поиск
Номер, ИИН/БИН, ФИО, договор, status/stage, продукт, classifier, channel, assignee/team, даты, breach, decision, closure reason.

## Общие требования

- Python 3.12, FastAPI, Pydantic v2.
- Domain/application/infrastructure структура.
- Собственная БД/схема и пользователь.
- `/health/live`, `/health/ready`.
- Structured JSON logs и correlation ID.
- Alembic migrations.
- OpenAPI.
- Unit, integration и contract tests.
