"""Responsable de autorizar la consulta en la declaración de derechos (Tablas de Control de Acceso).

Revision ID: 0062
Revises: 0061
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0062'
down_revision: Union[str, None] = '0061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('declaraciones_derechos', sa.Column('responsable_autorizacion', sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column('declaraciones_derechos', 'responsable_autorizacion')
