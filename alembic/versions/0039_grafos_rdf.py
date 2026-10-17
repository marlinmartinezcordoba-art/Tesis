"""grafo RiC-O persistente: registro de sincronización por fondo y alcance

Revision ID: 0039
Revises: 0038

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0039'
down_revision: Union[str, None] = '0038'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'grafos_rdf',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('fondo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('recursos_documentales.id', ondelete='CASCADE'), nullable=False),
        sa.Column('alcance', sa.String(10), nullable=False),
        sa.Column('version_datos', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('version_sincronizada', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cambiado_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('sincronizado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tripletas', sa.Integer(), nullable=True),
        sa.Column('huella', sa.String(64), nullable=True),
        sa.Column('conforme', sa.Boolean(), nullable=True),
        sa.Column('problemas_owl', sa.Integer(), nullable=True),
        sa.Column('resultados_shacl', sa.Integer(), nullable=True),
        sa.Column('resumen', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.String(1000), nullable=True),
        sa.UniqueConstraint('fondo_id', 'alcance', name='uq_grafos_rdf_fondo_alcance'),
    )
    op.create_index('ix_grafos_rdf_fondo_id', 'grafos_rdf', ['fondo_id'])
    # Todos los fondos existentes quedan pendientes: el trabajador arma su grafo.
    op.execute("""
        INSERT INTO grafos_rdf (id, fondo_id, alcance)
        SELECT gen_random_uuid(), r.id, a.alcance
        FROM recursos_documentales r CROSS JOIN (VALUES ('publico'), ('completo')) AS a(alcance)
        WHERE r.nivel = 'fondo'
    """)


def downgrade() -> None:
    op.drop_index('ix_grafos_rdf_fondo_id', table_name='grafos_rdf')
    op.drop_table('grafos_rdf')
