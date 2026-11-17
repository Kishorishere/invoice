"""add model column to invoices

Revision ID: 0002_invoice_model
Revises: 0001_initial_schema
Create Date: 2026-11-16
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy import inspect


revision: str = "0002_invoice_model"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    cols = _existing_columns("invoices")
    if "model" not in cols:
        with op.batch_alter_table("invoices") as batch:
            batch.add_column(sa.Column("model", sqlmodel.AutoString(), nullable=True))


def downgrade() -> None:
    cols = _existing_columns("invoices")
    if "model" in cols:
        with op.batch_alter_table("invoices") as batch:
            batch.drop_column("model")
