"""el CCD con que se coteja una versión de la TRD

Fase C: el cuadro de clasificación (CCD) se coteja con la TRD. El archivo del
CCD se guarda como las demás cargas, con su huella, marcado como CCD y con el
resultado del cotejo.

Revision ID: 0053
Revises: 0052

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '0053'
down_revision: Union[str, None] = '0052'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cargas_instrumento', sa.Column('clase', sa.String(3), nullable=False, server_default='trd'))
    op.add_column('cargas_instrumento', sa.Column('informe', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('cargas_instrumento', 'informe')
    op.drop_column('cargas_instrumento', 'clase')
