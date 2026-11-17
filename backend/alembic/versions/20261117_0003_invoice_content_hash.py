"""invoice content_hash column + per-user dedupe index

Adds `invoices.content_hash` (SHA-256 hex of the raw upload bytes) for
per-user dedupe, plus a composite index on (user_id, content_hash) for
the lookup. Existing rows get NULL; they'll never match a new upload (a
hash can't be None) so dedupe silently applies forward.

Revision ID: 0003_invoice_content_hash
Revises: 0002_invoice_model
Create Date: 2026-01-02
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy import inspect


revision: str = "0003_invoice_content_hash"
down_revision: Union[str, Sequence[str], None] = "0002_invoice_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _existing_indexes(table: str) -> set[str]:
    bind = op.get_bind()
    return {ix["name"] for ix in inspect(bind).get_indexes(table)}


def upgrade() -> None:
    cols = _existing_columns("invoices")
    if "content_hash" not in cols:
        with op.batch_alter_table("invoices") as batch:
            batch.add_column(sa.Column("content_hash", sqlmodel.AutoString(), nullable=True))

    if "ix_invoices_user_hash" not in _existing_indexes("invoices"):
        op.create_index(
            "ix_invoices_user_hash", "invoices", ["user_id", "content_hash"]
        )


def downgrade() -> None:
    if "ix_invoices_user_hash" in _existing_indexes("invoices"):
        op.drop_index("ix_invoices_user_hash", table_name="invoices")
    cols = _existing_columns("invoices")
    if "content_hash" in cols:
        with op.batch_alter_table("invoices") as batch:
            batch.drop_column("content_hash")
