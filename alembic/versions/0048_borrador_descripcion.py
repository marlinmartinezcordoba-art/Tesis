"""el avance de una descripción se guarda mientras se trabaja

El trabajo de descripción guarda el borrador del formulario (título,
alcance, entidades revisadas, campos, partes) para continuar donde se dejó:
al volver a la pantalla, al recargar o si la marca «en edición» venció.

Revision ID: 0048
Revises: 0047

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '0048'
down_revision: Union[str, None] = '0047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trabajos_descripcion', sa.Column('borrador', postgresql.JSONB(), nullable=True))
    op.add_column('trabajos_descripcion', sa.Column('borrador_guardado_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column('trabajos_descripcion', sa.Column('recuperado_de_id', postgresql.UUID(as_uuid=True),
                                                    sa.ForeignKey('trabajos_descripcion.id'), nullable=True))


def downgrade() -> None:
    op.drop_column('trabajos_descripcion', 'recuperado_de_id')
    op.drop_column('trabajos_descripcion', 'borrador_guardado_en')
    op.drop_column('trabajos_descripcion', 'borrador')
