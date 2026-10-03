"""cierre de la auditoría RiC (PRE-10): respaldo de la base de datos con su
simulacro de restauración

Revision ID: 0017
Revises: 0016

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0017'
down_revision: Union[str, None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    estado = postgresql.ENUM('en_curso', 'correcto', 'fallido', name='estado_respaldo')
    simulacro = postgresql.ENUM('correcto', 'fallido', name='estado_simulacro')
    estado.create(op.get_bind(), checkfirst=True)
    simulacro.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'respaldos_bd',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('iniciado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('terminado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('origen', sa.String(length=20), nullable=False),
        sa.Column('estado', postgresql.ENUM(name='estado_respaldo', create_type=False), nullable=False),
        sa.Column('archivo', sa.String(length=300), nullable=True),
        sa.Column('tamano_bytes', sa.BigInteger(), nullable=True),
        sa.Column('huella', sa.String(length=64), nullable=True),
        sa.Column('conteos', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.String(length=1000), nullable=True),
        sa.Column('simulacro_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('simulacro_estado', postgresql.ENUM(name='estado_simulacro', create_type=False), nullable=True),
        sa.Column('simulacro_detalle', postgresql.JSONB(), nullable=True),
        sa.Column('descargado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('descargado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('depurado_en', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_respaldos_bd_iniciado_en', 'respaldos_bd', ['iniciado_en'])


def downgrade() -> None:
    op.drop_index('ix_respaldos_bd_iniciado_en', table_name='respaldos_bd')
    op.drop_table('respaldos_bd')
    postgresql.ENUM(name='estado_simulacro').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='estado_respaldo').drop(op.get_bind(), checkfirst=True)
