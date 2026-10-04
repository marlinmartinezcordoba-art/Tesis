"""segundo factor de autenticación (brecha RF-SEC-003): TOTP por usuario
con códigos de respaldo; la obligatoriedad por rol es un parámetro

Revision ID: 0033
Revises: 0032

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0033'
down_revision: Union[str, None] = '0032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for valor in ('segundo_factor_activado', 'segundo_factor_restablecido'):
        op.execute(f"ALTER TYPE motivo_cierre_sesion ADD VALUE IF NOT EXISTS '{valor}'")
    op.add_column('usuarios', sa.Column('mfa_secreto', sa.String(64), nullable=True))
    op.add_column('usuarios', sa.Column('mfa_activo', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('usuarios', sa.Column('mfa_activado_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column('usuarios', sa.Column('mfa_ultimo_paso', sa.BigInteger(), nullable=True))
    op.add_column('usuarios', sa.Column('mfa_respaldo', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # PostgreSQL no quita valores de un tipo enumerado; los dos motivos quedan sin uso.
    for columna in ('mfa_respaldo', 'mfa_ultimo_paso', 'mfa_activado_en', 'mfa_activo', 'mfa_secreto'):
        op.drop_column('usuarios', columna)
