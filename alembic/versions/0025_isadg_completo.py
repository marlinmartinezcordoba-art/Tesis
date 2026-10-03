"""cierre de la auditoría RiC (DES-07): los elementos de ISAD-G que faltaban
en el Record Resource, la escritura (ISO 15924) y las características físicas
del original

Revision ID: 0025
Revises: 0024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0025'
down_revision: Union[str, None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEXTOS = ('forma_ingreso', 'valoracion', 'nuevos_ingresos', 'organizacion', 'instrumentos_descripcion',
          'localizacion_originales', 'localizacion_copias', 'unidades_relacionadas', 'nota_publicaciones',
          'nota_archivero', 'reglas_descripcion')


def upgrade() -> None:
    for columna in TEXTOS:
        op.add_column('recursos_documentales', sa.Column(columna, sa.Text(), nullable=True))
    op.add_column('recursos_documentales', sa.Column('escrituras', postgresql.ARRAY(sa.String(length=4)), nullable=True))
    op.add_column('instanciaciones', sa.Column('caracteristicas_fisicas', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('instanciaciones', 'caracteristicas_fisicas')
    op.drop_column('recursos_documentales', 'escrituras')
    for columna in reversed(TEXTOS):
        op.drop_column('recursos_documentales', columna)
