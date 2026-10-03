"""cierre de la auditoría RiC (PRE-02, PRE-06, PRE-09, PRE-13): marcas de
tiempo por paso de la ingesta, mecanismo que creó un recorte, y
comprobaciones técnicas (antivirus con ClamAV; validación de PDF/A con
veraPDF y de TIFF con JHOVE)

Revision ID: 0030
Revises: 0029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0030'
down_revision: Union[str, None] = '0029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for columna in ('huella_en', 'formato_en', 'texto_en'):
        op.add_column('instanciaciones', sa.Column(columna, sa.DateTime(timezone=True), nullable=True))
    op.add_column('instanciaciones', sa.Column('mecanismo_creacion_id', postgresql.UUID(as_uuid=True),
                                               sa.ForeignKey('entidades_vocabulario.id'), nullable=True))
    op.add_column('instanciaciones', sa.Column('mecanismo_texto_id', postgresql.UUID(as_uuid=True),
                                               sa.ForeignKey('entidades_vocabulario.id'), nullable=True))
    op.create_table(
        'comprobaciones_tecnicas',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('instanciacion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('instanciaciones.id'),
                  nullable=False),
        sa.Column('tipo', sa.Enum('antivirus', 'validacion', name='tipo_comprobacion'), nullable=False),
        sa.Column('herramienta', sa.String(60), nullable=False),
        sa.Column('mecanismo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entidades_vocabulario.id'),
                  nullable=True),
        sa.Column('resultado', sa.Enum('limpio', 'infectado', 'conforme', 'no_conforme', 'error', 'no_disponible',
                                       name='resultado_comprobacion'), nullable=False),
        sa.Column('perfil', sa.String(60), nullable=True),
        sa.Column('resumen', sa.Text(), nullable=True),
        sa.Column('detalle', postgresql.JSONB(), nullable=True),
        sa.Column('origen', sa.String(20), nullable=False),
        sa.Column('realizada_en', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_comprobaciones_instanciacion', 'comprobaciones_tecnicas', ['instanciacion_id'])


def downgrade() -> None:
    op.drop_index('ix_comprobaciones_instanciacion', 'comprobaciones_tecnicas')
    op.drop_table('comprobaciones_tecnicas')
    sa.Enum(name='resultado_comprobacion').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='tipo_comprobacion').drop(op.get_bind(), checkfirst=True)
    op.drop_column('instanciaciones', 'mecanismo_texto_id')
    op.drop_column('instanciaciones', 'mecanismo_creacion_id')
    for columna in ('texto_en', 'formato_en', 'huella_en'):
        op.drop_column('instanciaciones', columna)
