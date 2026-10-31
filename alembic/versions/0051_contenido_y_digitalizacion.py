"""varios tipos de contenido por documento, y la digitalización con su verificación

Requisito 2: un documento con texto y fotografías se describe con «texto» e
«imagen fija» a la vez (rico:hasContentOfType admite varios valores); el valor
único anterior pasa a ser el primero de la lista.

Requisito 5: la digitalización (original físico → copia digital) guarda quién
y cuándo digitalizó, con qué equipo y resolución, y cada verificación de la
copia con sus comprobaciones. «Digitalizado» no es «verificado».

Revision ID: 0051
Revises: 0050

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '0051'
down_revision: Union[str, None] = '0050'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recursos_documentales', sa.Column('tipos_contenido', postgresql.ARRAY(sa.String(40)), nullable=True))
    op.execute("UPDATE recursos_documentales SET tipos_contenido = ARRAY[tipo_contenido] WHERE tipo_contenido IS NOT NULL")
    op.drop_column('recursos_documentales', 'tipo_contenido')
    op.create_table(
        'digitalizaciones',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('relacion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('relaciones.id'), nullable=False, unique=True),
        sa.Column('responsable', sa.String(200), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=True),
        sa.Column('equipo', sa.String(200), nullable=True),
        sa.Column('resolucion_ppp', sa.Integer(), nullable=True),
        sa.Column('nota', sa.Text(), nullable=True),
        sa.Column('registrado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('registrado_en', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'verificaciones_digitalizacion',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('relacion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('relaciones.id'), nullable=False),
        sa.Column('comprobaciones', postgresql.JSONB(), nullable=False),
        sa.Column('resultado', sa.String(20), nullable=False),
        sa.Column('nota', sa.Text(), nullable=True),
        sa.Column('verificado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('verificado_en', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_verificaciones_digitalizacion_relacion_id', 'verificaciones_digitalizacion', ['relacion_id'])
    # Los grafos guardados tenían la columna anterior en su control: se vuelven a escribir.
    op.execute("UPDATE grafos_rdf SET version_datos = version_datos + 1, cambiado_en = now()")


def downgrade() -> None:
    op.drop_table('verificaciones_digitalizacion')
    op.drop_table('digitalizaciones')
    op.add_column('recursos_documentales', sa.Column('tipo_contenido', sa.String(30), nullable=True))
    op.execute("UPDATE recursos_documentales SET tipo_contenido = tipos_contenido[1] WHERE tipos_contenido IS NOT NULL")
    op.drop_column('recursos_documentales', 'tipos_contenido')
