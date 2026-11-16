"""Descripción devuelta para redescribir: quién la devolvió, cuándo y por qué.

La descripción sigue publicada con su identificador; al guardarse la
corrección queda como versión nueva y la marca se levanta.

Revision ID: 0064
Revises: 0063
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = '0064'
down_revision: Union[str, None] = '0063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recursos_documentales', sa.Column('devuelta_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column('recursos_documentales', sa.Column('devuelta_por_id', UUID(as_uuid=True),
                                                     sa.ForeignKey('usuarios.id'), nullable=True))
    op.add_column('recursos_documentales', sa.Column('devuelta_motivo', sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column('recursos_documentales', 'devuelta_motivo')
    op.drop_column('recursos_documentales', 'devuelta_por_id')
    op.drop_column('recursos_documentales', 'devuelta_en')
