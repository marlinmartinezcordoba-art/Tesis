"""cierre de la auditoría RiC (INS-06): unidades de conservación «tomo» y
«otro» y frecuencia de consulta del FUID (Acuerdo 042 de 2002)

Revision ID: 0029
Revises: 0028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0029'
down_revision: Union[str, None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recursos_documentales', sa.Column('tomo', sa.String(30), nullable=True))
    op.add_column('recursos_documentales', sa.Column('otra_unidad', sa.String(60), nullable=True))
    op.add_column('recursos_documentales', sa.Column('frecuencia_consulta', sa.String(10), nullable=True))
    op.execute("ALTER TABLE recursos_documentales ADD CONSTRAINT ck_frecuencia_consulta CHECK "
               "(frecuencia_consulta IS NULL OR frecuencia_consulta IN ('alta', 'media', 'baja', 'ninguna'))")


def downgrade() -> None:
    op.execute("ALTER TABLE recursos_documentales DROP CONSTRAINT IF EXISTS ck_frecuencia_consulta")
    for c in ('frecuencia_consulta', 'otra_unidad', 'tomo'):
        op.drop_column('recursos_documentales', c)
