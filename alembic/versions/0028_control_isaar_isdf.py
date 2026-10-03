"""cierre de la auditoría RiC (VOC-01, VOC-02, VOC-03): área de control de
ISAAR y de ISDF, tipo y código de la función, nivel «parcial» y parentesco

Revision ID: 0028
Revises: 0027

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0028'
down_revision: Union[str, None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE nivel_detalle ADD VALUE IF NOT EXISTS 'parcial'")
        op.execute("ALTER TYPE codigo_relacion_ric ADD VALUE IF NOT EXISTS 'has_family_association_with'")
    t = 'entidades_vocabulario'
    op.add_column(t, sa.Column('estado_elaboracion', sa.String(20), nullable=True))  # ISAAR 5.4.4 / ISDF 5.4.4
    op.add_column(t, sa.Column('institucion_responsable', sa.String(300), nullable=True))  # 5.4.2
    op.add_column(t, sa.Column('notas_mantenimiento', sa.Text(), nullable=True))  # 5.4.9
    op.add_column(t, sa.Column('lenguas', postgresql.ARRAY(sa.String(3)), nullable=True))  # 5.4.7 (ISO 639-3)
    op.add_column(t, sa.Column('escrituras', postgresql.ARRAY(sa.String(4)), nullable=True))  # 5.4.7 (ISO 15924)
    op.add_column(t, sa.Column('tipo_funcion', sa.String(20), nullable=True))  # ISDF 5.1.1
    op.add_column(t, sa.Column('codigo_clasificacion', sa.String(40), nullable=True))  # ISDF 5.1.4; skos:notation
    # Por qué se sugiere una fusión (hallazgo VOC-05): nombre parecido, otra
    # forma del nombre o el mismo identificador externo.
    op.add_column('sugerencias_fusion', sa.Column('motivo', sa.String(30), nullable=False, server_default='nombre'))
    op.execute("ALTER TABLE entidades_vocabulario ADD CONSTRAINT ck_estado_elaboracion CHECK "
               "(estado_elaboracion IS NULL OR estado_elaboracion IN ('borrador', 'revisado', 'definitivo'))")
    op.execute("ALTER TABLE entidades_vocabulario ADD CONSTRAINT ck_tipo_funcion CHECK "
               "(tipo_funcion IS NULL OR tipo_funcion IN ('funcion', 'subfuncion', 'proceso', 'actividad', "
               "'transaccion'))")


def downgrade() -> None:
    op.drop_column('sugerencias_fusion', 'motivo')
    op.execute("ALTER TABLE entidades_vocabulario DROP CONSTRAINT IF EXISTS ck_tipo_funcion")
    op.execute("ALTER TABLE entidades_vocabulario DROP CONSTRAINT IF EXISTS ck_estado_elaboracion")
    for c in ('codigo_clasificacion', 'tipo_funcion', 'escrituras', 'lenguas', 'notas_mantenimiento',
              'institucion_responsable', 'estado_elaboracion'):
        op.drop_column('entidades_vocabulario', c)
