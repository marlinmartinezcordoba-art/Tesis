"""cierre de la auditoría RiC (CM-13): el hito institucional con su lugar

Revision ID: 0022
Revises: 0021

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0022'
down_revision: Union[str, None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('hitos', sa.Column('lugar_id', postgresql.UUID(as_uuid=True),
                                     sa.ForeignKey('entidades_vocabulario.id'), nullable=True))


def downgrade() -> None:
    op.drop_column('hitos', 'lugar_id')
