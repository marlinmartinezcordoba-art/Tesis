"""cierre de la auditoría RiC (CM-01, CM-16, DES-02): fechas extremas en
EDTF validado, al lado de la forma en que se escribieron

Revision ID: 0019
Revises: 0018

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0019'
down_revision: Union[str, None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AÑOS = re.compile(r"^\s*(\d{4})\s*(?:(?:[–—-]|a|al|hasta|/)\s*(\d{4}))?\s*$", re.IGNORECASE)


def upgrade() -> None:
    op.add_column('recursos_documentales', sa.Column('fechas_extremas_edtf', sa.String(length=200), nullable=True))
    con = op.get_bind()
    filas = con.execute(sa.text("SELECT id, fechas_extremas FROM recursos_documentales "
                                "WHERE fechas_extremas IS NOT NULL")).all()
    for ident, texto in filas:
        m = _AÑOS.match(texto or "")
        if m:  # lo que no se entiende queda sin normalizar, para que una persona lo revise
            edtf = f"{m.group(1)}/{m.group(2)}" if m.group(2) else m.group(1)
            con.execute(sa.text("UPDATE recursos_documentales SET fechas_extremas_edtf = :e WHERE id = :i"),
                        {"e": edtf, "i": ident})


def downgrade() -> None:
    op.drop_column('recursos_documentales', 'fechas_extremas_edtf')
