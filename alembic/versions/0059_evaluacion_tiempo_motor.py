"""tiempo de procesamiento del motor por documento de la evaluación

La Tabla 3 de la tesis (dimensión 5) compara el tiempo medio por unidad documental: el de la
archivista ya se mide (de abrir a enviar); el del motor se guarda al generar la propuesta.

Revision ID: 0059
Revises: 0058

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0059'
down_revision: Union[str, None] = '0058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('evaluacion_documentos', sa.Column('segundos_motor', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('evaluacion_documentos', 'segundos_motor')
