"""cierre de la auditoría RiC (DES-08, CM-02): nivel «subsección» del
cuadro de clasificación documental colombiano

Revision ID: 0020
Revises: 0019

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0020'
down_revision: Union[str, None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE nivel_descripcion ADD VALUE IF NOT EXISTS 'subseccion' AFTER 'seccion'")


def downgrade() -> None:
    # PostgreSQL no retira un valor de un enumerado; queda sin uso.
    pass
