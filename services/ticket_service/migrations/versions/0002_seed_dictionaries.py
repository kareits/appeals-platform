"""Seed draft reference dictionaries.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Dictionary types seeded here. The downgrade removes exactly these types, leaving any operator- or
# later-migration-added entries untouched.
_SEEDED_TYPES: tuple[str, ...] = (
    "channel",
    "product",
    "classifier",
    "priority",
    "status",
    "stage",
    "decision",
    "closure_reason",
    "gender",
)

# TODO(Q-A1): Replace these draft codes and labels with the business-approved taxonomy of
# classifiers, products, and closure reasons once it is provided; codes are mapped, not discarded.
#
# Codes are English and vendor-neutral (ADR-016); display labels are Russian business content
# (ADR-015). Statuses mirror docs/01 exactly.
_SEED_ROWS: tuple[dict[str, object], ...] = (
    # Intake channels.
    {
        "dictionary_type": "channel",
        "code": "EMAIL",
        "display_name_ru": "Электронная почта",
        "sort_order": 10,
    },
    {
        "dictionary_type": "channel",
        "code": "PAPER",
        "display_name_ru": "Бумажное обращение",
        "sort_order": 20,
    },
    {"dictionary_type": "channel", "code": "PORTAL", "display_name_ru": "Портал", "sort_order": 30},
    {"dictionary_type": "channel", "code": "PHONE", "display_name_ru": "Телефон", "sort_order": 40},
    {"dictionary_type": "channel", "code": "OTHER", "display_name_ru": "Иное", "sort_order": 90},
    # Credit products.
    {
        "dictionary_type": "product",
        "code": "MICROLOAN",
        "display_name_ru": "Микрокредит",
        "sort_order": 10,
    },
    {
        "dictionary_type": "product",
        "code": "INSTALLMENT",
        "display_name_ru": "Рассрочка",
        "sort_order": 20,
    },
    {
        "dictionary_type": "product",
        "code": "GUARANTEE",
        "display_name_ru": "Гарантия",
        "sort_order": 30,
    },
    {
        "dictionary_type": "product",
        "code": "OTHER",
        "display_name_ru": "Иной продукт",
        "sort_order": 90,
    },
    # Question classifiers.
    {
        "dictionary_type": "classifier",
        "code": "RESTRUCTURING",
        "display_name_ru": "Реструктуризация",
        "sort_order": 10,
    },
    {
        "dictionary_type": "classifier",
        "code": "COMPLAINT",
        "display_name_ru": "Жалоба",
        "sort_order": 20,
    },
    {
        "dictionary_type": "classifier",
        "code": "INFO_REQUEST",
        "display_name_ru": "Запрос информации",
        "sort_order": 30,
    },
    {
        "dictionary_type": "classifier",
        "code": "DISPUTE",
        "display_name_ru": "Спор по задолженности",
        "sort_order": 40,
    },
    {
        "dictionary_type": "classifier",
        "code": "OTHER",
        "display_name_ru": "Иной вопрос",
        "sort_order": 90,
    },
    # Priorities.
    {"dictionary_type": "priority", "code": "LOW", "display_name_ru": "Низкий", "sort_order": 10},
    {
        "dictionary_type": "priority",
        "code": "NORMAL",
        "display_name_ru": "Обычный",
        "sort_order": 20,
    },
    {"dictionary_type": "priority", "code": "HIGH", "display_name_ru": "Высокий", "sort_order": 30},
    {
        "dictionary_type": "priority",
        "code": "URGENT",
        "display_name_ru": "Срочный",
        "sort_order": 40,
    },
    # Statuses (docs/01).
    {"dictionary_type": "status", "code": "NEW", "display_name_ru": "Новое", "sort_order": 10},
    {
        "dictionary_type": "status",
        "code": "IN_PROGRESS",
        "display_name_ru": "В работе",
        "sort_order": 20,
    },
    {
        "dictionary_type": "status",
        "code": "WAITING_FOR_CUSTOMER",
        "display_name_ru": "Ожидание клиента",
        "sort_order": 30,
    },
    {
        "dictionary_type": "status",
        "code": "ON_HOLD",
        "display_name_ru": "Приостановлено",
        "sort_order": 40,
    },
    {
        "dictionary_type": "status",
        "code": "TRANSFERRED",
        "display_name_ru": "Передано",
        "sort_order": 50,
    },
    {
        "dictionary_type": "status",
        "code": "COMPLETED",
        "display_name_ru": "Завершено",
        "sort_order": 60,
    },
    {
        "dictionary_type": "status",
        "code": "CANCELLED",
        "display_name_ru": "Отменено",
        "sort_order": 70,
    },
    # Stages (draft).
    {
        "dictionary_type": "stage",
        "code": "REGISTRATION",
        "display_name_ru": "Регистрация",
        "sort_order": 10,
    },
    {
        "dictionary_type": "stage",
        "code": "REVIEW",
        "display_name_ru": "Рассмотрение",
        "sort_order": 20,
    },
    {
        "dictionary_type": "stage",
        "code": "DOCUMENTS_REQUESTED",
        "display_name_ru": "Запрошены документы",
        "sort_order": 30,
    },
    {
        "dictionary_type": "stage",
        "code": "DECISION",
        "display_name_ru": "Принятие решения",
        "sort_order": 40,
    },
    {
        "dictionary_type": "stage",
        "code": "RESPONSE",
        "display_name_ru": "Подготовка ответа",
        "sort_order": 50,
    },
    {"dictionary_type": "stage", "code": "CLOSED", "display_name_ru": "Закрыто", "sort_order": 60},
    # Decisions (draft).
    {
        "dictionary_type": "decision",
        "code": "APPROVED",
        "display_name_ru": "Удовлетворено",
        "sort_order": 10,
    },
    {
        "dictionary_type": "decision",
        "code": "PARTIALLY_APPROVED",
        "display_name_ru": "Частично удовлетворено",
        "sort_order": 20,
    },
    {
        "dictionary_type": "decision",
        "code": "REJECTED",
        "display_name_ru": "Отказано",
        "sort_order": 30,
    },
    # Closure reasons (draft).
    {
        "dictionary_type": "closure_reason",
        "code": "RESOLVED",
        "display_name_ru": "Обращение разрешено",
        "sort_order": 10,
    },
    {
        "dictionary_type": "closure_reason",
        "code": "REJECTED",
        "display_name_ru": "Отказ по обращению",
        "sort_order": 20,
    },
    {
        "dictionary_type": "closure_reason",
        "code": "DUPLICATE",
        "display_name_ru": "Дубликат",
        "sort_order": 30,
    },
    {
        "dictionary_type": "closure_reason",
        "code": "WITHDRAWN",
        "display_name_ru": "Отозвано заявителем",
        "sort_order": 40,
    },
    {
        "dictionary_type": "closure_reason",
        "code": "OUT_OF_SCOPE",
        "display_name_ru": "Вне компетенции",
        "sort_order": 90,
    },
    # Gender.
    {"dictionary_type": "gender", "code": "MALE", "display_name_ru": "Мужской", "sort_order": 10},
    {"dictionary_type": "gender", "code": "FEMALE", "display_name_ru": "Женский", "sort_order": 20},
    {
        "dictionary_type": "gender",
        "code": "UNSPECIFIED",
        "display_name_ru": "Не указан",
        "sort_order": 90,
    },
)


def _dictionary_table() -> sa.Table:
    """Build a lightweight table reference for bulk seed operations.

    Returns:
        An ad-hoc ``dictionary_entry`` table description sufficient for insert/delete.
    """
    return sa.table(
        "dictionary_entry",
        sa.column("dictionary_type", sa.String),
        sa.column("code", sa.String),
        sa.column("display_name_ru", sa.String),
        sa.column("display_name_kk", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )


def upgrade() -> None:
    """Apply the migration: insert the draft reference dictionaries (backfill)."""
    rows = [
        {
            "dictionary_type": row["dictionary_type"],
            "code": row["code"],
            "display_name_ru": row["display_name_ru"],
            "display_name_kk": row.get("display_name_kk"),
            "sort_order": row["sort_order"],
            "is_active": True,
        }
        for row in _SEED_ROWS
    ]
    op.bulk_insert(_dictionary_table(), rows)


def downgrade() -> None:
    """Revert the migration: delete only the seeded draft dictionary entries.

    Deletion is scoped to the seeded dictionary types, so no regulatory appeal data is affected
    (root ``CLAUDE.md``).
    """
    table = _dictionary_table()
    op.execute(table.delete().where(table.c.dictionary_type.in_(_SEEDED_TYPES)))
