"""RiC completo, cobertura total de RiC-CM 1.0: códigos de relación y campos nuevos

Revision ID: 0044
Revises: 0043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0044'
down_revision: Union[str, None] = '0043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODIGOS = ('has_or_had_owner', 'has_or_had_manager', 'has_or_had_ipr_holder', 'has_or_had_main_subject', 'has_descendant',
           'has_or_had_authority_over', 'has_or_had_work_relation_with', 'knows_of', 'knows', 'has_or_had_correspondent',
           'has_or_had_student', 'has_or_had_participant', 'is_or_was_adjacent_to', 'overlaps_or_overlapped',
           'has_or_had_component')


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for c in CODIGOS:
            op.execute(f"ALTER TYPE codigo_relacion_ric ADD VALUE IF NOT EXISTS '{c}'")
    for columna in (sa.Column('tipo_entidad', sa.String(40)), sa.Column('tipo_familia', sa.String(20)),
                    sa.Column('ocupacion', sa.String(200)), sa.Column('grupo_demografico', sa.String(200))):
        op.add_column('entidades_vocabulario', columna)
    op.add_column('recursos_documentales', sa.Column('tipo_contenido', sa.String(30), nullable=True))
    op.add_column('recursos_documentales', sa.Column('fechas_predominantes_edtf', sa.String(200), nullable=True))
    op.add_column('instanciaciones', sa.Column('tecnica_produccion', sa.String(30), nullable=True))
    op.add_column('trd_versiones', sa.Column('ente_vigilancia_id', postgresql.UUID(as_uuid=True),
                                             sa.ForeignKey('entidades_vocabulario.id'), nullable=True))


def downgrade() -> None:
    op.drop_column('trd_versiones', 'ente_vigilancia_id')
    op.drop_column('instanciaciones', 'tecnica_produccion')
    op.drop_column('recursos_documentales', 'fechas_predominantes_edtf')
    op.drop_column('recursos_documentales', 'tipo_contenido')
    for c in ('grupo_demografico', 'ocupacion', 'tipo_familia', 'tipo_entidad'):
        op.drop_column('entidades_vocabulario', c)
