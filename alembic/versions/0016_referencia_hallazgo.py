"""cierre de la auditoría RiC: cada hallazgo del panel puede llevar el
identificador con que lo levantó la auditoría (p. ej. «INS-02»)

Revision ID: 0016
Revises: 0015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016'
down_revision: Union[str, None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('hallazgos_conformidad', sa.Column('referencia', sa.String(length=12), nullable=True))
    op.create_unique_constraint('uq_hallazgo_referencia', 'hallazgos_conformidad', ['referencia'])


def downgrade() -> None:
    op.drop_constraint('uq_hallazgo_referencia', 'hallazgos_conformidad', type_='unique')
    op.drop_column('hallazgos_conformidad', 'referencia')
