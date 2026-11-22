"""evaluación del rendimiento con la medida F1 (objetivo 3, metodología vigente)

Reemplaza el protocolo ciego por la evaluación sobre las decisiones de validación que la
archivista toma en Descripción. Agrega la semilla del sorteo, el conjunto de cada documento
(desarrollo o prueba) y la tabla de la validación de control. Las tablas del protocolo ciego
(anotaciones, exposiciones, calificaciones, participantes) se conservan con sus datos; el
código ya no las usa.

Revision ID: 0065
Revises: 0064

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0065'
down_revision: Union[str, None] = '0064'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('evaluaciones', sa.Column('semilla', sa.Integer(), nullable=True))
    op.add_column('evaluaciones', sa.Column('sorteada_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column('evaluacion_documentos', sa.Column('conjunto', sa.String(12), nullable=True))
    op.create_check_constraint('ck_evaluacion_documento_conjunto', 'evaluacion_documentos',
                               "conjunto IS NULL OR conjunto IN ('desarrollo', 'prueba')")
    op.create_table(
        'evaluacion_control',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('evaluacion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluaciones.id'), nullable=False,
                  index=True),
        # Sin clave foránea: la auditoría no admite dependencias (no se trunca ni se borra).
        sa.Column('evento_id', sa.BigInteger(), nullable=False),
        sa.Column('decision', sa.String(12), nullable=False),
        sa.Column('usuario_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('evaluacion_id', 'evento_id', 'usuario_id', name='uq_control_decision'),
        sa.CheckConstraint("decision IN ('aceptada', 'corregida', 'rechazada')", name='ck_control_decision'),
    )


def downgrade() -> None:
    op.drop_table('evaluacion_control')
    op.drop_constraint('ck_evaluacion_documento_conjunto', 'evaluacion_documentos', type_='check')
    op.drop_column('evaluacion_documentos', 'conjunto')
    op.drop_column('evaluaciones', 'sorteada_en')
    op.drop_column('evaluaciones', 'semilla')
