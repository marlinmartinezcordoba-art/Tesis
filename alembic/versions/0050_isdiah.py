"""ficha ISDIAH de la institución que custodia los fondos

Contacto, acceso y servicios de una entidad corporativa que custodia
archivos (ISDIAH): lo que la ficha ISAAR no tiene. Los fondos que custodia
salen de sus vínculos de custodia (rico:hasOrHadHolder).

Revision ID: 0050
Revises: 0049

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '0050'
down_revision: Union[str, None] = '0049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('entidades_vocabulario', sa.Column('isdiah', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('entidades_vocabulario', 'isdiah')
