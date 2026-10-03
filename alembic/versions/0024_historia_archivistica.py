"""cierre de la auditoría RiC (DES-06): historia archivística del Record
Resource (ISAD-G 3.2.3), distinta de la relación con el custodio

Revision ID: 0024
Revises: 0023

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0024'
down_revision: Union[str, None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recursos_documentales', sa.Column('historia_archivistica', sa.Text(), nullable=True))
    op.add_column('recursos_documentales', sa.Column('origen_historia_archivistica', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('recursos_documentales', 'origen_historia_archivistica')
    op.drop_column('recursos_documentales', 'historia_archivistica')
