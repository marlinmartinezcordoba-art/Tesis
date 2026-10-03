"""ingesta: confianza del OCR; catálogo: siete códigos verificados contra RiC-O 1.1

Revision ID: 0010
Revises: 0009

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODIGOS_NUEVOS = ('has_or_had_holder', 'precedes_or_preceded', 'has_direct_subevent', 'contains_or_contained',
                  'affects_or_affected', 'is_related_to', 'issued_by')


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for c in CODIGOS_NUEVOS:
            op.execute(f"ALTER TYPE codigo_relacion_ric ADD VALUE IF NOT EXISTS '{c}'")
    op.add_column('instanciaciones', sa.Column('confianza_ocr', sa.Float(), nullable=True))
    op.add_column('instanciaciones', sa.Column('palabras_ocr', sa.Integer(), nullable=True))
    op.add_column('instanciaciones', sa.Column('ocr_baja_confianza', sa.Boolean(), server_default='false',
                                               nullable=False))
    op.create_index(op.f('ix_instanciaciones_ocr_baja_confianza'), 'instanciaciones', ['ocr_baja_confianza'],
                    unique=False)
    # Los documentos leídos por OCR antes de esta versión no tienen
    # confianza: quedan vacíos (no se inventa un valor); un reintento la calcula.


def downgrade() -> None:
    # Los valores agregados al tipo enumerado no se pueden quitar en
    # PostgreSQL; quedan sin uso.
    op.drop_index(op.f('ix_instanciaciones_ocr_baja_confianza'), table_name='instanciaciones')
    op.drop_column('instanciaciones', 'ocr_baja_confianza')
    op.drop_column('instanciaciones', 'palabras_ocr')
    op.drop_column('instanciaciones', 'confianza_ocr')
