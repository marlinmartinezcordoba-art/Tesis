"""perfil RiC-Col del AGN (Esquema de Metadatos v1.4): estado de
conservación y signatura topográfica del original físico (tabla 4),
categoría de datos personales según la Ley 1581 y nota de accesibilidad
(principio 3, Ley 1680) en la descripción

Revision ID: 0031
Revises: 0030

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0031'
down_revision: Union[str, None] = '0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('instanciaciones', sa.Column('estado_conservacion', sa.String(20), nullable=True))
    for columna in ('deposito', 'estante', 'entrepano'):
        op.add_column('instanciaciones', sa.Column(columna, sa.String(40), nullable=True))
    op.add_column('recursos_documentales', sa.Column('datos_personales', sa.String(20), nullable=True))
    op.add_column('recursos_documentales', sa.Column('nota_accesibilidad', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('recursos_documentales', 'nota_accesibilidad')
    op.drop_column('recursos_documentales', 'datos_personales')
    for columna in ('entrepano', 'estante', 'deposito', 'estado_conservacion'):
        op.drop_column('instanciaciones', columna)
