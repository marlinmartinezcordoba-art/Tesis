"""descripción v3: parte documental, idioma, condiciones de acceso y de uso, calendario de la fecha,
tipo de parte en el vocabulario y recortes como instanciaciones propias

Revision ID: 0012
Revises: 0011

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        # Parte documental (RiC-E05 Record Part), por debajo de la unidad documental.
        op.execute("ALTER TYPE nivel_descripcion ADD VALUE IF NOT EXISTS 'parte_documental'")
        # Tipo de parte (anexo, folio, firma, sello…), vocabulario controlado del fondo.
        op.execute("ALTER TYPE clase_vocabulario ADD VALUE IF NOT EXISTS 'tipo_parte'")
        # El recorte de una parte documental también lleva su segunda copia.
        op.execute("ALTER TYPE motivo_segunda_copia ADD VALUE IF NOT EXISTS 'recorte'")
    origen = postgresql.ENUM('motor', 'motor_editado', 'persona', name='origen_dato', create_type=False)
    op.add_column('recursos_documentales', sa.Column('idiomas', postgresql.ARRAY(sa.String(length=3)), nullable=True))
    op.add_column('recursos_documentales', sa.Column('origen_idiomas', origen, nullable=True))
    op.add_column('recursos_documentales', sa.Column('confianza_idiomas', sa.Float(), nullable=True))
    op.add_column('recursos_documentales', sa.Column('condiciones_acceso', sa.Text(), nullable=True))
    op.add_column('recursos_documentales', sa.Column('condiciones_uso', sa.Text(), nullable=True))
    op.add_column('recursos_documentales', sa.Column('tipo_parte_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_recurso_tipo_parte', 'recursos_documentales', 'entidades_vocabulario',
                          ['tipo_parte_id'], ['id'])
    # Calendario explícito: toda fecha del sistema es gregoriana, y se declara.
    op.add_column('fechas', sa.Column('calendario', sa.String(length=20), server_default='gregoriano', nullable=False))
    # Un recorte (la firma o el sello de un documento) es una instanciación
    # propia, sacada de otra: se guarda de cuál, de qué página y qué zona.
    op.add_column('instanciaciones', sa.Column('recorte_de_id', sa.UUID(), nullable=True))
    op.add_column('instanciaciones', sa.Column('recorte_zona', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key('fk_instanciacion_recorte_de', 'instanciaciones', 'instanciaciones', ['recorte_de_id'], ['id'])
    op.create_index('ix_instanciaciones_recorte_de', 'instanciaciones', ['recorte_de_id'])


def downgrade() -> None:
    op.drop_index('ix_instanciaciones_recorte_de', table_name='instanciaciones')
    op.drop_constraint('fk_instanciacion_recorte_de', 'instanciaciones', type_='foreignkey')
    op.drop_column('instanciaciones', 'recorte_zona')
    op.drop_column('instanciaciones', 'recorte_de_id')
    op.drop_column('fechas', 'calendario')
    op.drop_constraint('fk_recurso_tipo_parte', 'recursos_documentales', type_='foreignkey')
    for c in ('tipo_parte_id', 'condiciones_uso', 'condiciones_acceso', 'confianza_idiomas', 'origen_idiomas',
              'idiomas'):
        op.drop_column('recursos_documentales', c)
    # Los valores agregados a los tipos enumerados no se pueden quitar en PostgreSQL.
