"""criterio de comparabilidad y clasificación de errores de la evaluación

Objetivo 3 de la tesis convertido en lógica: cada evaluación guarda su
criterio de comparabilidad (fijado antes de iniciar) y las investigadoras
clasifican cada desacuerdo entre el motor y la referencia ciega con la
taxonomía de errores, primero de forma independiente y después por consenso.

Revision ID: 0054
Revises: 0053

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '0054'
down_revision: Union[str, None] = '0053'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('evaluaciones', sa.Column('criterio', postgresql.JSONB(), nullable=True))
    op.create_table(
        'evaluacion_errores',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('evaluacion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluaciones.id'), nullable=False,
                  index=True),
        sa.Column('clave', sa.String(40), nullable=False),
        sa.Column('ronda', sa.String(12), nullable=False),
        sa.Column('clasificadora_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('tipo_error', sa.String(20), nullable=False),
        sa.Column('nota', sa.Text(), nullable=True),
        sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('evaluacion_id', 'clave', 'ronda', 'clasificadora_id', name='uq_error_clasificacion'),
        sa.CheckConstraint("ronda IN ('individual', 'consenso')", name='ck_error_ronda'),
    )


def downgrade() -> None:
    op.drop_table('evaluacion_errores')
    op.drop_column('evaluaciones', 'criterio')
