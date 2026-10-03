"""cierre de la auditoría RiC (ING-01, ING-02): lote de transferencia con su
procedencia y su paquete de envío (SIP) BagIt

Revision ID: 0026
Revises: 0025

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0026'
down_revision: Union[str, None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FORMA = ('transferencia_primaria', 'transferencia_secundaria', 'donacion', 'compra', 'comodato', 'deposito', 'otro')


def upgrade() -> None:
    op.create_table(
        'lotes_ingesta',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('fondo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('recursos_documentales.id'), nullable=False),
        sa.Column('numero', sa.String(40), nullable=False),
        sa.Column('forma_ingreso', sa.Enum(*FORMA, name='forma_ingreso'), nullable=False),
        sa.Column('remitente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entidades_vocabulario.id'), nullable=True),
        sa.Column('dependencia_origen_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entidades_vocabulario.id'),
                  nullable=True),
        sa.Column('acta_numero', sa.String(60), nullable=True),
        sa.Column('acta_fecha_edtf', sa.String(200), nullable=True),
        sa.Column('acta_instanciacion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('instanciaciones.id'),
                  nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('estado', sa.Enum('abierto', 'confirmado', 'anulado', name='estado_lote'), nullable=False),
        sa.Column('creado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('confirmado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('motivo_anulacion', sa.Text(), nullable=True),
        sa.Column('sip_ruta', sa.String(500), nullable=True),
        sa.Column('sip_huella', sa.String(64), nullable=True),
        sa.Column('sip_archivos', sa.Integer(), nullable=True),
        sa.Column('sip_bytes', sa.BigInteger(), nullable=True),
        sa.UniqueConstraint('fondo_id', 'numero', name='uq_lote_numero_por_fondo'),
    )
    op.create_index('ix_lotes_ingesta_fondo_id', 'lotes_ingesta', ['fondo_id'])
    op.add_column('instanciaciones', sa.Column('lote_id', postgresql.UUID(as_uuid=True),
                                               sa.ForeignKey('lotes_ingesta.id'), nullable=True))
    op.create_index('ix_instanciaciones_lote_id', 'instanciaciones', ['lote_id'])


def downgrade() -> None:
    op.drop_index('ix_instanciaciones_lote_id', 'instanciaciones')
    op.drop_column('instanciaciones', 'lote_id')
    op.drop_index('ix_lotes_ingesta_fondo_id', 'lotes_ingesta')
    op.drop_table('lotes_ingesta')
    sa.Enum(name='estado_lote').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='forma_ingreso').drop(op.get_bind(), checkfirst=True)
