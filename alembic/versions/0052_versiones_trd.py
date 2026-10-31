"""archivo original de cada carga de la TRD, procedencia de cada fila y versión con que se clasificó

Requisito 3: el archivo de la TRD se conserva tal como llegó, con su huella,
y cada fila de la matriz dice de qué archivo y de qué fila salió.
Requisito 7: cada descripción guarda la versión de la TRD que regía cuando se
clasificó.

Revision ID: 0052
Revises: 0051

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '0052'
down_revision: Union[str, None] = '0051'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cargas_instrumento',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('fondo_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('recursos_documentales.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('trd_versiones.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('archivo', sa.String(300), nullable=False),
        sa.Column('huella', sa.String(64), nullable=False),
        sa.Column('tamano', sa.Integer(), nullable=False),
        sa.Column('ruta', sa.String(500), nullable=False),
        sa.Column('origen', sa.String(300), nullable=True),
        sa.Column('filas_cargadas', sa.Integer(), nullable=False),
        sa.Column('cargado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('cargado_en', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_cargas_instrumento_fondo_id', 'cargas_instrumento', ['fondo_id'])
    op.create_index('ix_cargas_instrumento_version_id', 'cargas_instrumento', ['version_id'])
    op.add_column('trd_filas', sa.Column('procedencia', postgresql.JSONB(), nullable=True))
    op.add_column('recursos_documentales', sa.Column('version_trd_id', postgresql.UUID(as_uuid=True),
                                                     sa.ForeignKey('trd_versiones.id'), nullable=True))
    op.execute("UPDATE grafos_rdf SET version_datos = version_datos + 1, cambiado_en = now()")


def downgrade() -> None:
    op.drop_column('recursos_documentales', 'version_trd_id')
    op.drop_column('trd_filas', 'procedencia')
    op.drop_table('cargas_instrumento')
