"""Baseline schema — all tables derived from current ORM models.

Consolidated from 001-008 on 2026-04-19. Uses ``Base.metadata.create_all`` so
the baseline always matches the ORM — the moment the models evolve past a
point an incremental migration can resolve, squash back into this file.

Revision ID: 001
Revises:
Create Date: 2026-04-19
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
