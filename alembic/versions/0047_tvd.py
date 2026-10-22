"""TVD: la tabla de valoración documental como versión del mismo instrumento

Una versión puede ser de la TRD o de la TVD (Acuerdo 004 de 2019). La TVD
cubre un periodo institucional del fondo acumulado (desde, hasta): sus
reglas rigen los documentos producidos en ese periodo. La numeración de las
versiones va por instrumento.

Revision ID: 0047
Revises: 0046

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0047'
down_revision: Union[str, None] = '0046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trd_versiones', sa.Column('instrumento', sa.String(3), nullable=False, server_default='trd'))
    op.add_column('trd_versiones', sa.Column('periodo', sa.String(300), nullable=True))
    op.add_column('trd_versiones', sa.Column('periodo_desde', sa.Date(), nullable=True))
    op.add_column('trd_versiones', sa.Column('periodo_hasta', sa.Date(), nullable=True))
    op.create_check_constraint('ck_trd_version_instrumento', 'trd_versiones', "instrumento IN ('trd', 'tvd')")
    op.create_check_constraint('ck_trd_version_periodo', 'trd_versiones',
                               "periodo_desde IS NULL OR periodo_hasta IS NULL OR periodo_desde <= periodo_hasta")
    op.drop_constraint('uq_trd_version_numero', 'trd_versiones', type_='unique')
    op.create_unique_constraint('uq_trd_version_numero', 'trd_versiones', ['fondo_id', 'instrumento', 'numero'])


def downgrade() -> None:
    op.drop_constraint('uq_trd_version_numero', 'trd_versiones', type_='unique')
    op.execute("DELETE FROM trd_versiones WHERE instrumento = 'tvd'")
    op.create_unique_constraint('uq_trd_version_numero', 'trd_versiones', ['fondo_id', 'numero'])
    op.drop_constraint('ck_trd_version_periodo', 'trd_versiones', type_='check')
    op.drop_constraint('ck_trd_version_instrumento', 'trd_versiones', type_='check')
    for columna in ('periodo_hasta', 'periodo_desde', 'periodo', 'instrumento'):
        op.drop_column('trd_versiones', columna)
