"""expertas participantes de la evaluación

Quién hizo cada descripción humana de referencia: nombre, formación,
experiencia y consentimiento informado. La pregunta problema compara la
descripción del motor con la de expertas; la tesis debe poder decir quiénes
eran y por qué su descripción es una referencia válida.

Revision ID: 0056
Revises: 0055

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0056'
down_revision: Union[str, None] = '0055'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FORMACION = ("tecnica", "tecnologica", "profesional", "especializacion", "maestria", "doctorado")
ROL = ("descriptora", "calificadora", "ambas")


def upgrade() -> None:
    op.create_table(
        'evaluacion_participantes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('evaluacion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluaciones.id'), nullable=False,
                  index=True),
        sa.Column('usuario_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('codigo', sa.String(8), nullable=False),
        sa.Column('nombre', sa.String(200), nullable=False),
        sa.Column('profesion', sa.String(200), nullable=False),
        sa.Column('formacion', sa.Enum(*FORMACION, name='formacion_participante'), nullable=False),
        sa.Column('anios_experiencia', sa.Integer(), nullable=False),
        sa.Column('anios_descripcion', sa.Integer(), nullable=True),
        sa.Column('cargo', sa.String(200), nullable=True),
        sa.Column('institucion', sa.String(200), nullable=True),
        sa.Column('rol', sa.Enum(*ROL, name='rol_participante'), nullable=False),
        sa.Column('consentimiento', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('consentimiento_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('registrado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('registrado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('retirado_en', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('evaluacion_id', 'usuario_id'),
        sa.UniqueConstraint('evaluacion_id', 'codigo'),
    )


def downgrade() -> None:
    op.drop_table('evaluacion_participantes')
    sa.Enum(name='rol_participante').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='formacion_participante').drop(op.get_bind(), checkfirst=True)
