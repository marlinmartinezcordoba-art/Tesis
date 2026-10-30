"""posibles datos personales detectados en el texto (Ley 1581)

El sistema busca con reglas cédulas, tarjetas de identidad, correos,
teléfonos, cuentas, datos de salud y otros datos sensibles o de menores en el
texto de cada archivo. Cada hallazgo queda pendiente hasta que una persona lo
confirma, lo corrige o lo descarta; nada se borra.

Revision ID: 0049
Revises: 0048

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '0049'
down_revision: Union[str, None] = '0048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'datos_personales_detectados',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('instanciacion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('instanciaciones.id'), nullable=False),
        sa.Column('fondo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('recursos_documentales.id'), nullable=False),
        sa.Column('tipo', sa.String(40), nullable=False),
        sa.Column('categoria', sa.String(10), nullable=False),
        sa.Column('confianza', sa.Float(), nullable=False),
        sa.Column('regla', sa.String(40), nullable=False),
        sa.Column('version_reglas', sa.String(10), nullable=False),
        sa.Column('muestra', sa.String(120), nullable=False),
        sa.Column('huella_valor', sa.String(64), nullable=False),
        sa.Column('ocurrencias', postgresql.JSONB(), nullable=False),
        sa.Column('estado', sa.String(12), nullable=False),
        sa.Column('tipo_final', sa.String(40), nullable=True),
        sa.Column('categoria_final', sa.String(10), nullable=True),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('decidido_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('decidido_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('detectado_en', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('instanciacion_id', 'tipo', 'huella_valor', name='uq_dato_personal_valor'),
    )
    op.create_index('ix_datos_personales_detectados_instanciacion_id', 'datos_personales_detectados', ['instanciacion_id'])
    op.create_index('ix_datos_personales_detectados_fondo_id', 'datos_personales_detectados', ['fondo_id'])
    op.create_index('ix_datos_personales_detectados_estado', 'datos_personales_detectados', ['estado'])
    op.add_column('instanciaciones', sa.Column('revision_datos_personales', sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column('instanciaciones', 'revision_datos_personales')
    op.drop_table('datos_personales_detectados')
