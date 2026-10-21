"""grafo RiC-O como fuente de verdad: rearmar todos los grafos con su grafo de control

Los grafos guardados antes no tienen el grafo de control (lo que RiC-O no
expresa). Se marcan como pendientes para que el trabajador los vuelva a
escribir completos.

Revision ID: 0040
Revises: 0039

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0040'
down_revision: Union[str, None] = '0039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE grafos_rdf SET version_datos = version_datos + 1, cambiado_en = now()")


def downgrade() -> None:
    pass
