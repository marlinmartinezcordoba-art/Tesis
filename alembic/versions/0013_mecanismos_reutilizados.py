"""mecanismos reutilizados: cada acción técnica apunta al agente mecanismo
(RiC-E13) del vocabulario del fondo, con su versión exacta, en vez de
guardar el nombre del programa como texto libre

Revision ID: 0013
Revises: 0012

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabla, columna): qué mecanismo ejecutó la acción técnica registrada en la fila.
COLUMNAS = [
    ('instanciaciones', 'mecanismo_identificacion_id'),  # Siegfried, con su versión y sus firmas PRONOM
    ('migraciones', 'mecanismo_id'),  # Ghostscript o Pillow
    ('verificaciones_integridad', 'mecanismo_id'),  # el propio sistema
    ('segundas_copias', 'mecanismo_id'),
    ('restauraciones', 'mecanismo_id'),
    ('entidades_vocabulario', 'motor_id'),  # el motor de análisis que propuso el dato
    ('relaciones', 'motor_id'),
    ('fechas', 'motor_id'),
    ('actividades', 'motor_id'),
    ('recursos_documentales', 'motor_id'),
]


def upgrade() -> None:
    for tabla, columna in COLUMNAS:
        op.add_column(tabla, sa.Column(columna, postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f'fk_{tabla}_{columna}', tabla, 'entidades_vocabulario', [columna], ['id'])
        op.create_index(f'ix_{tabla}_{columna}', tabla, [columna])
    # Lo que el programa hizo (parámetros), separado de quién lo hizo (el mecanismo).
    op.add_column('migraciones', sa.Column('parametros', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('migraciones', 'parametros')
    for tabla, columna in reversed(COLUMNAS):
        op.drop_index(f'ix_{tabla}_{columna}', table_name=tabla)
        op.drop_constraint(f'fk_{tabla}_{columna}', tabla, type_='foreignkey')
        op.drop_column(tabla, columna)
