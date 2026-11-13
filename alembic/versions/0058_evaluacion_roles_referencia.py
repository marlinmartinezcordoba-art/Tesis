"""evaluación por roles separados, referencia adjudicada, prueba piloto y versión congelada

Las archivistas de referencia describen a ciegas, una adjudicadora consolida la referencia, las
validadoras revisan las propuestas del motor sin ver la referencia y la prueba piloto usa
documentos que no entran en los resultados. Al iniciar, la evaluación guarda la versión del
sistema, del motor, de la instrucción y del perfil de aplicación con que se mide.

Revision ID: 0058
Revises: 0057

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0058'
down_revision: Union[str, None] = '0057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for valor in ("validadora", "adjudicadora", "piloto"):
        op.execute(f"ALTER TYPE rol_participante ADD VALUE IF NOT EXISTS '{valor}'")
    op.execute("ALTER TYPE condicion_anotacion ADD VALUE IF NOT EXISTS 'adjudicada'")
    op.add_column('evaluacion_documentos', sa.Column('piloto', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('evaluacion_anotaciones', sa.Column('justificacion', sa.Text(), nullable=True))
    op.add_column('evaluaciones', sa.Column('version_congelada', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('evaluaciones', 'version_congelada')
    op.drop_column('evaluacion_anotaciones', 'justificacion')
    op.drop_column('evaluacion_documentos', 'piloto')
    # Los valores agregados a los tipos enumerados de PostgreSQL no se retiran.
