"""nivel «colección» (RiC-O rst:Collection): reúne documentos de distintas series por pertenencia adicional

Revision ID: 0041
Revises: 0040

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0041'
down_revision: Union[str, None] = '0040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE nivel_descripcion ADD VALUE IF NOT EXISTS 'coleccion' AFTER 'fondo'")


def downgrade() -> None:
    pass  # PostgreSQL no quita valores de un tipo enumerado; nada lo usa si no se crean colecciones
