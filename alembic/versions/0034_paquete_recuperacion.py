"""paquete de recuperación ante desastres (brechas NFR-04, NFR-07 y
RF-OPS-001): base, archivos del almacén y manifiesto con huellas, con su
simulacro de restauración completa y el tiempo medido (RTO real)

Revision ID: 0034
Revises: 0033

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0034'
down_revision: Union[str, None] = '0033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'paquetes_recuperacion',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('terminado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('origen', sa.String(20), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False),
        sa.Column('respaldo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('respaldos_bd.id'), nullable=True),
        sa.Column('archivo', sa.String(300), nullable=True),
        sa.Column('tamano_bytes', sa.BigInteger(), nullable=True),
        sa.Column('huella', sa.String(64), nullable=True),
        sa.Column('archivos', sa.Integer(), nullable=True),
        sa.Column('bytes_archivos', sa.BigInteger(), nullable=True),
        sa.Column('error', sa.String(1000), nullable=True),
        sa.Column('simulacro_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('simulacro_estado', sa.String(20), nullable=True),
        sa.Column('simulacro_segundos', sa.Integer(), nullable=True),
        sa.Column('simulacro_detalle', postgresql.JSONB(), nullable=True),
        sa.Column('descargado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('descargado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('depurado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('creado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('paquetes_recuperacion')
