"""instrumentos: datos de control del inventario (FUID)

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNAS = (
    ('codigo_referencia', sa.String(60)),
    ('caja', sa.String(30)),
    ('carpeta', sa.String(30)),
    ('folios', sa.Integer()),
    ('soporte', sa.String(40)),
)


def upgrade() -> None:
    for nombre, tipo in COLUMNAS:
        op.add_column('recursos_documentales', sa.Column(nombre, tipo, nullable=True))


def downgrade() -> None:
    for nombre, _ in reversed(COLUMNAS):
        op.drop_column('recursos_documentales', nombre)
