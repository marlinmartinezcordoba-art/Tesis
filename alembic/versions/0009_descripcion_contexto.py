"""descripción: fechas EDTF, actividad, tipo de actividad y mandato en el vocabulario

Revision ID: 0009
Revises: 0008

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLASES_NUEVAS = ('actividad', 'tipo_actividad', 'mandato')
CODIGOS_NUEVOS = ('has_activity_type', 'performs_or_performed', 'has_successor', 'is_agent_associated_with_agent',
                  'is_date_associated_with')


def upgrade() -> None:
    # Valores nuevos de tipos enumerados: fuera de la transacción, para
    # poder usarlos enseguida al mover las actividades.
    with op.get_context().autocommit_block():
        for c in CLASES_NUEVAS:
            op.execute(f"ALTER TYPE clase_vocabulario ADD VALUE IF NOT EXISTS '{c}'")
        for c in CODIGOS_NUEVOS:
            op.execute(f"ALTER TYPE codigo_relacion_ric ADD VALUE IF NOT EXISTS '{c}'")
    subtipo = postgresql.ENUM('simple', 'rango', 'conjunto', name='subtipo_fecha', create_type=False)
    sa.Enum('simple', 'rango', 'conjunto', name='subtipo_fecha').create(op.get_bind(), checkfirst=True)
    op.add_column('fechas', sa.Column('subtipo', subtipo, server_default='simple', nullable=False))
    op.add_column('fechas', sa.Column('edtf', sa.String(length=200), nullable=True))
    op.add_column('fechas', sa.Column('inicio', sa.Date(), nullable=True))
    op.add_column('fechas', sa.Column('fin', sa.Date(), nullable=True))
    # Las fechas exactas de la primera versión ya son EDTF de nivel 0.
    op.execute("UPDATE fechas SET edtf = to_char(normalizada, 'YYYY-MM-DD'), inicio = normalizada, fin = normalizada "
               "WHERE normalizada IS NOT NULL")
    op.add_column('relaciones', sa.Column('origen_original_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_relaciones_origen_original_id'), 'relaciones', ['origen_original_id'], unique=False)
    # Las actividades pasan al vocabulario (mismo identificador) para
    # verificarse y fusionarse como agentes y lugares. La tabla vieja queda.
    op.execute("""
        INSERT INTO entidades_vocabulario (id, fondo_id, clase, subtipo, nombre, nombre_normalizado, estado, origen,
                                           confianza, motor, estado_revision, creado_en)
        SELECT a.id, a.fondo_id, 'actividad', NULL, a.nombre,
               lower(regexp_replace(translate(a.nombre, 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun'), '\\s+', ' ', 'g')),
               'activa', a.origen, a.confianza, a.motor, a.estado_revision, a.creado_en
        FROM actividades a ON CONFLICT (id) DO NOTHING""")
    op.execute("UPDATE relaciones SET destino_tipo = 'entidad_vocabulario' WHERE destino_tipo = 'actividad'")
    op.execute("UPDATE relaciones SET origen_tipo = 'entidad_vocabulario' WHERE origen_tipo = 'actividad'")


def downgrade() -> None:
    # Los valores agregados a los tipos enumerados no se pueden quitar en
    # PostgreSQL; quedan sin uso. Las actividades vuelven a su tabla.
    op.execute("UPDATE relaciones SET destino_tipo = 'actividad' WHERE destino_id IN (SELECT id FROM actividades)")
    op.execute("UPDATE relaciones SET origen_tipo = 'actividad' WHERE origen_id IN (SELECT id FROM actividades)")
    op.execute("DELETE FROM entidades_vocabulario WHERE id IN (SELECT id FROM actividades)")
    op.drop_index(op.f('ix_relaciones_origen_original_id'), table_name='relaciones')
    op.drop_column('relaciones', 'origen_original_id')
    op.drop_column('fechas', 'fin')
    op.drop_column('fechas', 'inicio')
    op.drop_column('fechas', 'edtf')
    op.drop_column('fechas', 'subtipo')
    sa.Enum(name='subtipo_fecha').drop(op.get_bind(), checkfirst=True)
