"""tesauros para normalizar las materias

- tesauros, conceptos_tesauro y etiquetas_concepto (la preferente y las no
  preferentes, normalizadas, con índice de trigramas para buscar parecidos).
- La clase «materia» en el vocabulario del fondo (rico:Concept), unida a su
  concepto del tesauro.

Revision ID: 0038
Revises: 0037

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0038'
down_revision: Union[str, None] = '0037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE clase_vocabulario ADD VALUE IF NOT EXISTS 'materia'")
    op.create_table(
        'tesauros',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('nombre', sa.String(200), nullable=False),
        sa.Column('fuente', sa.String(500), nullable=True),
        sa.Column('licencia', sa.String(200), nullable=True),
        sa.Column('idioma', sa.String(8), nullable=False, server_default='es'),
        sa.Column('uri_esquema', sa.String(500), nullable=True),
        sa.Column('formato', sa.String(20), nullable=False),
        sa.Column('archivo', sa.String(300), nullable=True),
        sa.Column('huella', sa.String(64), nullable=True),
        sa.Column('conceptos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estado', sa.String(20), nullable=False, server_default='vigente'),
        sa.Column('importado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('importado_en', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("estado IN ('vigente', 'anulado')", name='ck_tesauro_estado'),
    )
    op.create_table(
        'conceptos_tesauro',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tesauro_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tesauros.id'), nullable=False, index=True),
        sa.Column('clave', sa.String(500), nullable=False),
        sa.Column('uri', sa.String(500), nullable=True),
        sa.Column('preferente', sa.String(300), nullable=False),
        sa.Column('notacion', sa.String(60), nullable=True),
        sa.Column('nota_alcance', sa.Text(), nullable=True),
        sa.Column('superior_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conceptos_tesauro.id'), nullable=True,
                  index=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='vigente'),
        sa.UniqueConstraint('tesauro_id', 'clave', name='uq_concepto_tesauro_clave'),
    )
    op.create_table(
        'etiquetas_concepto',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('concepto_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conceptos_tesauro.id'), nullable=False,
                  index=True),
        sa.Column('etiqueta', sa.String(300), nullable=False),
        sa.Column('normalizada', sa.String(300), nullable=False, index=True),
        sa.Column('tipo', sa.String(20), nullable=False),
        sa.CheckConstraint("tipo IN ('preferente', 'no_preferente', 'oculta')", name='ck_etiqueta_concepto_tipo'),
    )
    op.execute("CREATE INDEX ix_etiquetas_concepto_trgm ON etiquetas_concepto USING gin (normalizada gin_trgm_ops)")
    op.add_column('entidades_vocabulario', sa.Column('concepto_tesauro_id', postgresql.UUID(as_uuid=True),
                                                     sa.ForeignKey('conceptos_tesauro.id'), nullable=True))
    op.create_index('ix_entidades_vocabulario_concepto_tesauro_id', 'entidades_vocabulario', ['concepto_tesauro_id'])


def downgrade() -> None:
    op.drop_index('ix_entidades_vocabulario_concepto_tesauro_id', table_name='entidades_vocabulario')
    op.drop_column('entidades_vocabulario', 'concepto_tesauro_id')
    op.drop_table('etiquetas_concepto')
    op.drop_table('conceptos_tesauro')
    op.drop_table('tesauros')
    # El valor «materia» del enumerado no se retira (PostgreSQL no lo permite sin recrear el tipo).
