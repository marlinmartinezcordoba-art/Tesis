"""RiC completo, fase 1: tipos documentales de la serie, estado del documento,
completitud, respuesta y borrador

Revision ID: 0043
Revises: 0042

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0043'
down_revision: Union[str, None] = '0042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for c in ('has_reply', 'is_draft_of'):
            op.execute(f"ALTER TYPE codigo_relacion_ric ADD VALUE IF NOT EXISTS '{c}'")
    op.add_column('recursos_documentales', sa.Column('formas_miembros', postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                                                     nullable=False, server_default='{}'))
    op.add_column('recursos_documentales', sa.Column('estado_documento', sa.String(20), nullable=True))
    op.add_column('recursos_documentales', sa.Column('nota_integridad', sa.Text(), nullable=True))
    # Las series y subseries ya creadas desde la TRD guardaban sus tipos solo
    # como texto en el alcance («Tipos documentales: a; b.»): se enlazan con las
    # formas documentales del vocabulario del fondo que tienen ese nombre.
    op.execute("""
        UPDATE recursos_documentales r SET formas_miembros = sub.ids
        FROM (
            SELECT r2.id, array_agg(DISTINCT e.id ORDER BY e.id) AS ids
            FROM recursos_documentales r2
            CROSS JOIN LATERAL regexp_split_to_table(
                regexp_replace(substring(r2.alcance_contenido FROM 'Tipos documentales: (.*)$'), '\\.$', ''), ';\\s*') AS t(nombre)
            JOIN entidades_vocabulario e ON e.fondo_id = r2.fondo_id AND e.clase = 'forma_documental'
                 AND e.estado = 'activa' AND lower(trim(e.nombre)) = lower(trim(t.nombre))
            WHERE r2.nivel IN ('serie', 'subserie') AND r2.alcance_contenido LIKE 'Tipos documentales: %'
            GROUP BY r2.id
        ) sub
        WHERE r.id = sub.id
    """)


def downgrade() -> None:
    op.drop_column('recursos_documentales', 'nota_integridad')
    op.drop_column('recursos_documentales', 'estado_documento')
    op.drop_column('recursos_documentales', 'formas_miembros')
    # Un valor de un enumerado de PostgreSQL no se retira.
