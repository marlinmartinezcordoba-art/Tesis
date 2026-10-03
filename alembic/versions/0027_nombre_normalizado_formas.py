"""cierre de la auditoría RiC (DES-10): las otras formas del nombre de una
autoridad también se buscan (nombre normalizado e índice de trigramas)

Revision ID: 0027
Revises: 0026

"""
import re
import unicodedata
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0027'
down_revision: Union[str, None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalizar(texto: str) -> str:  # la misma regla que app/servicios/vocabulario.normalizar
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def upgrade() -> None:
    op.add_column('nombres_entidad', sa.Column('nombre_normalizado', sa.String(300), nullable=True))
    con = op.get_bind()
    for ident, nombre in con.execute(sa.text("SELECT id, nombre FROM nombres_entidad")).all():
        con.execute(sa.text("UPDATE nombres_entidad SET nombre_normalizado = :n WHERE id = :i"),
                    {"n": _normalizar(nombre), "i": ident})
    op.execute("CREATE INDEX IF NOT EXISTS ix_nombres_entidad_trgm ON nombres_entidad "
               "USING gin (nombre_normalizado gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_nombres_entidad_trgm")
    op.drop_column('nombres_entidad', 'nombre_normalizado')
