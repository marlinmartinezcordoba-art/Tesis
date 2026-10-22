"""proyección de lectura: la consulta lee lo que dice el grafo RiC-O

Crea el esquema «lectura» con las tablas de la descripción (sin claves
foráneas ni disparadores de trabajo), que se llena desde el grafo guardado
(app/servicios/lectura.py). Si una migración posterior cambia una de esas
tablas, la proyección la rehace sola la próxima vez que se consulta.

Revision ID: 0046
Revises: 0045

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0046'
down_revision: Union[str, None] = '0045'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.servicios import lectura

    lectura.asegurar_esquema(op.get_bind())


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS lectura CASCADE")
