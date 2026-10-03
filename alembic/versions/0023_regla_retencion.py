"""cierre de la auditoría RiC (CM-18, DES-09): la regla de retención de la
TRD como rico:Rule del vocabulario, ligada a la serie que regula

Revision ID: 0023
Revises: 0022

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0023'
down_revision: Union[str, None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE clase_vocabulario ADD VALUE IF NOT EXISTS 'regla'")
    op.add_column('entidades_vocabulario', sa.Column('retencion_gestion_anios', sa.Integer(), nullable=True))
    op.add_column('entidades_vocabulario', sa.Column('retencion_central_anios', sa.Integer(), nullable=True))
    op.add_column('entidades_vocabulario', sa.Column('disposicion_final', sa.String(length=30), nullable=True))
    op.execute("ALTER TABLE entidades_vocabulario ADD CONSTRAINT ck_disposicion_final CHECK (disposicion_final IS NULL "
               "OR disposicion_final IN ('conservacion_total', 'eliminacion', 'seleccion', 'medio_tecnico'))")


def downgrade() -> None:
    op.execute("ALTER TABLE entidades_vocabulario DROP CONSTRAINT IF EXISTS ck_disposicion_final")
    for c in ('disposicion_final', 'retencion_central_anios', 'retencion_gestion_anios'):
        op.drop_column('entidades_vocabulario', c)
