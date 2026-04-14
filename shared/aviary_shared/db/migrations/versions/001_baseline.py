"""Baseline schema — all tables derived from current ORM models + default SA seed.

This is the consolidated starting point. Prior incremental migrations were
squashed away. Future schema changes add new revisions with `down_revision = "001"`.

Revision ID: 001
Revises:
Create Date: 2026-04-15
"""
from typing import Sequence, Union

from alembic import op

from aviary_shared.db.models import Base

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
