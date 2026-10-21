"""parametrización de la TRD y el CCD: versiones, dependencias, banco terminológico y matriz

Revision ID: 0042
Revises: 0041

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0042'
down_revision: Union[str, None] = '0041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def _fondo():
    return sa.Column('fondo_id', UUID, sa.ForeignKey('recursos_documentales.id', ondelete='CASCADE'), nullable=False,
                     index=True)


def upgrade() -> None:
    op.create_table(
        'trd_versiones',
        sa.Column('id', UUID, primary_key=True),
        _fondo(),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(300), nullable=False),
        sa.Column('acto_aprobacion', sa.String(300), nullable=True),
        sa.Column('fecha_aprobacion', sa.Date(), nullable=True),
        sa.Column('convalidacion', sa.String(300), nullable=True),
        sa.Column('fecha_convalidacion', sa.Date(), nullable=True),
        sa.Column('vigente_desde', sa.Date(), nullable=True),
        sa.Column('vigente_hasta', sa.Date(), nullable=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='borrador'),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('informe', postgresql.JSONB(), nullable=True),
        sa.Column('creado_por_id', UUID, sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('aplicado_por_id', UUID, sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('aplicado_en', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('fondo_id', 'numero', name='uq_trd_version_numero'),
    )
    op.create_table(
        'trd_dependencias',
        sa.Column('id', UUID, primary_key=True),
        _fondo(),
        sa.Column('superior_id', UUID, sa.ForeignKey('trd_dependencias.id'), nullable=True, index=True),
        sa.Column('codigo', sa.String(40), nullable=False),
        sa.Column('nombre', sa.String(300), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False, server_default='activa'),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('fondo_id', 'superior_id', 'codigo', name='uq_trd_dependencia_codigo'),
    )
    op.create_table(
        'trd_banco',
        sa.Column('id', UUID, primary_key=True),
        _fondo(),
        sa.Column('clase', sa.String(20), nullable=False),
        sa.Column('superior_id', UUID, sa.ForeignKey('trd_banco.id'), nullable=True, index=True),
        sa.Column('codigo', sa.String(40), nullable=True),
        sa.Column('nombre', sa.String(300), nullable=False),
        sa.Column('definicion', sa.Text(), nullable=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='activo'),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        'trd_filas',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('version_id', UUID, sa.ForeignKey('trd_versiones.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('dependencia_id', UUID, sa.ForeignKey('trd_dependencias.id'), nullable=False, index=True),
        sa.Column('serie_id', UUID, sa.ForeignKey('trd_banco.id'), nullable=False),
        sa.Column('subserie_id', UUID, sa.ForeignKey('trd_banco.id'), nullable=True),
        sa.Column('tipos', postgresql.ARRAY(UUID), nullable=False, server_default='{}'),
        sa.Column('gestion', sa.Integer(), nullable=True),
        sa.Column('central', sa.Integer(), nullable=True),
        sa.Column('disposicion', sa.String(2), nullable=True),
        sa.Column('otras_disposiciones', postgresql.ARRAY(sa.String(2)), nullable=False, server_default='{}'),
        sa.Column('soporte', sa.String(20), nullable=True),
        sa.Column('procedimiento', sa.Text(), nullable=True),
        sa.Column('funcion', sa.String(300), nullable=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='vigente'),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for tabla in ('trd_filas', 'trd_banco', 'trd_dependencias', 'trd_versiones'):
        op.drop_table(tabla)
