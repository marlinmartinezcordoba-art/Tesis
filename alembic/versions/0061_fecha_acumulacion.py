"""Fecha de acumulación del recurso documental (rico:hasAccumulationDate).

Revision ID: 0061
Revises: 0060
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0061'
down_revision: Union[str, None] = '0060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recursos_documentales', sa.Column('fecha_acumulacion_edtf', sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column('recursos_documentales', 'fecha_acumulacion_edtf')
