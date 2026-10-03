"""evaluación ciega del motor frente a archivistas (objetivo 3 de la tesis)

Revision ID: 0015
Revises: 0014

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
ENUMS = {
    'estado_evaluacion': ('preparacion', 'en_curso', 'cerrada'),
    'condicion_anotacion': ('ciega', 'asistida'),
    'estado_anotacion': ('en_curso', 'enviada', 'anulada'),
    'criterio_rubrica': ('exactitud', 'completitud', 'pertinencia'),
}


def _enum(nombre):
    return postgresql.ENUM(name=nombre, create_type=False)


def upgrade() -> None:
    for nombre, valores in ENUMS.items():
        postgresql.ENUM(*valores, name=nombre).create(op.get_bind(), checkfirst=True)
    op.create_table(
        'evaluaciones',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('fondo_id', UUID, sa.ForeignKey('recursos_documentales.id'), nullable=False, index=True),
        sa.Column('nombre', sa.String(200), nullable=False),
        sa.Column('protocolo', sa.Text(), nullable=True),
        sa.Column('umbral_similitud', sa.Float(), nullable=False, server_default='0.85'),
        sa.Column('estado', _enum('estado_evaluacion'), nullable=False, server_default='preparacion'),
        sa.Column('creada_por_id', UUID, sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('iniciada_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cerrada_en', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('umbral_similitud > 0 AND umbral_similitud <= 1', name='ck_evaluacion_umbral'),
    )
    op.create_table(
        'evaluacion_documentos',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('evaluacion_id', UUID, sa.ForeignKey('evaluaciones.id'), nullable=False, index=True),
        sa.Column('instanciacion_id', UUID, sa.ForeignKey('instanciaciones.id'), nullable=False),
        sa.Column('propuesta', postgresql.JSONB(), nullable=True),
        sa.Column('motor', sa.String(120), nullable=True),
        sa.Column('version_prompt', sa.String(16), nullable=True),
        sa.Column('generada_en', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('evaluacion_id', 'instanciacion_id'),
    )
    op.create_table(
        'evaluacion_anotaciones',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('evaluacion_id', UUID, sa.ForeignKey('evaluaciones.id'), nullable=False, index=True),
        sa.Column('instanciacion_id', UUID, sa.ForeignKey('instanciaciones.id'), nullable=False),
        sa.Column('evaluador_id', UUID, sa.ForeignKey('usuarios.id'), nullable=False, index=True),
        sa.Column('condicion', _enum('condicion_anotacion'), nullable=False),
        sa.Column('estado', _enum('estado_anotacion'), nullable=False, server_default='en_curso'),
        sa.Column('datos', postgresql.JSONB(), nullable=True),
        sa.Column('iniciada_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('enviada_en', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('evaluacion_id', 'instanciacion_id', 'evaluador_id', 'condicion'),
    )
    op.create_table(
        'evaluacion_exposiciones',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('evaluacion_id', UUID, sa.ForeignKey('evaluaciones.id'), nullable=False, index=True),
        sa.Column('instanciacion_id', UUID, sa.ForeignKey('instanciaciones.id'), nullable=False),
        sa.Column('usuario_id', UUID, sa.ForeignKey('usuarios.id'), nullable=False, index=True),
        sa.Column('motivo', sa.String(20), nullable=False),
        sa.Column('momento', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        'evaluacion_calificaciones',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('evaluacion_id', UUID, sa.ForeignKey('evaluaciones.id'), nullable=False, index=True),
        sa.Column('instanciacion_id', UUID, sa.ForeignKey('instanciaciones.id'), nullable=False),
        sa.Column('evaluador_id', UUID, sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('criterio', _enum('criterio_rubrica'), nullable=False),
        sa.Column('puntaje', sa.Integer(), nullable=False),
        sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('evaluacion_id', 'instanciacion_id', 'evaluador_id', 'criterio'),
        sa.CheckConstraint('puntaje BETWEEN 1 AND 5', name='ck_calificacion_puntaje'),
    )


def downgrade() -> None:
    for tabla in ('evaluacion_calificaciones', 'evaluacion_exposiciones', 'evaluacion_anotaciones',
                  'evaluacion_documentos', 'evaluaciones'):
        op.drop_table(tabla)
    for nombre in ENUMS:
        postgresql.ENUM(name=nombre).drop(op.get_bind(), checkfirst=True)
