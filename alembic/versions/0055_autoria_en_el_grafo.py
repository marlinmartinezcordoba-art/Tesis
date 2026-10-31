"""la autoría de la descripción en el grafo: volver a sincronizar los fondos

Criterio nativo 7: cada relación se asocia a la actividad que la produjo (la
propuesta del motor, la validación o la corrección de la archivista). Los
grafos ya publicados no la tienen: se marcan todos los fondos para que el
trabajador los vuelva a sincronizar. No cambia ninguna tabla.

Revision ID: 0055
Revises: 0054

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0055'
down_revision: Union[str, None] = '0054'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE grafos_rdf SET version_datos = version_datos + 1, cambiado_en = now()")


def downgrade() -> None:
    pass  # marcar para sincronizar no se deshace: el trabajador ya lo hizo
