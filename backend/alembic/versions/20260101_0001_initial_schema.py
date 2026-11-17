"""initial schema

Captures users + invoices + app_limits as of this revision. For any live
database that predates Alembic (SQLite dev / Fly volume), we treat tables
and columns that already exist as idempotent — the migration becomes a no-op
when the schema is already in place.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-01-01
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy import inspect


revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(inspect(bind).get_table_names())


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    tables = _existing_tables()

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sqlmodel.AutoString(), primary_key=True, nullable=False),
            sa.Column("email", sqlmodel.AutoString(), nullable=False),
            sa.Column("hashed_password", sqlmodel.AutoString(), nullable=False),
            sa.Column("role", sqlmodel.AutoString(), nullable=False, server_default="user"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("bootstrapped_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    else:
        user_cols = _existing_columns("users")
        if "role" not in user_cols:
            with op.batch_alter_table("users") as batch:
                batch.add_column(
                    sa.Column(
                        "role",
                        sqlmodel.AutoString(),
                        nullable=False,
                        server_default="user",
                    )
                )
        if "bootstrapped_at" not in user_cols:
            with op.batch_alter_table("users") as batch:
                batch.add_column(sa.Column("bootstrapped_at", sa.DateTime(), nullable=True))

    if "invoices" not in tables:
        op.create_table(
            "invoices",
            sa.Column("id", sqlmodel.AutoString(), primary_key=True, nullable=False),
            sa.Column(
                "user_id",
                sqlmodel.AutoString(),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("provider", sqlmodel.AutoString(), nullable=False),
            sa.Column("file_name", sqlmodel.AutoString(), nullable=False),
            sa.Column("file_path", sqlmodel.AutoString(), nullable=False),
            sa.Column("mime_type", sqlmodel.AutoString(), nullable=False),
            sa.Column("data_json", sqlmodel.AutoString(), nullable=False),
            sa.Column("validation_json", sqlmodel.AutoString(), nullable=False),
            sa.Column("invoice_number", sqlmodel.AutoString(), nullable=True),
            sa.Column("supplier_name", sqlmodel.AutoString(), nullable=True),
            sa.Column("total_amount", sa.Float(), nullable=True),
            sa.Column("currency", sqlmodel.AutoString(), nullable=True),
            sa.Column("invoice_date", sqlmodel.AutoString(), nullable=True),
            sa.Column("due_date", sqlmodel.AutoString(), nullable=True),
            sa.Column("all_checks_pass", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_invoices_user_id", "invoices", ["user_id"])
        op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])
        op.create_index("ix_invoices_created_at", "invoices", ["created_at"])
        op.create_index("ix_invoices_user_created", "invoices", ["user_id", "created_at"])
    else:
        # Make sure the composite index exists even on older DBs.
        bind = op.get_bind()
        existing_indexes = {ix["name"] for ix in inspect(bind).get_indexes("invoices")}
        if "ix_invoices_user_created" not in existing_indexes:
            op.create_index(
                "ix_invoices_user_created", "invoices", ["user_id", "created_at"]
            )

    if "app_limits" not in tables:
        op.create_table(
            "app_limits",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "max_files_per_upload",
                sa.Integer(),
                nullable=False,
                server_default="5",
            ),
            sa.Column("max_per_hour", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("max_per_day", sa.Integer(), nullable=False, server_default="500"),
            sa.Column(
                "max_per_month", sa.Integer(), nullable=False, server_default="5000"
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("app_limits")
    op.drop_index("ix_invoices_user_created", table_name="invoices")
    op.drop_index("ix_invoices_created_at", table_name="invoices")
    op.drop_index("ix_invoices_invoice_number", table_name="invoices")
    op.drop_index("ix_invoices_user_id", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
