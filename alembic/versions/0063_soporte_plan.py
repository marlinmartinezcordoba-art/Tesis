"""Documento de soporte de un plan (PGD o PINAR): el archivo adjunto, con su huella.

Revision ID: 0063
Revises: 0062
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0063'
down_revision: Union[str, None] = '0062'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('entidades_vocabulario', sa.Column('soporte', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('entidades_vocabulario', 'soporte')
