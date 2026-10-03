"""cierre de la auditoría RiC (CM-04): el original físico como Instantiation
y la instanciación derivada (recorte → su archivo de origen)

Revision ID: 0021
Revises: 0020

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0021'
down_revision: Union[str, None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE estado_ingesta ADD VALUE IF NOT EXISTS 'registro_fisico'")
    op.alter_column('instanciaciones', 'ruta', existing_type=sa.String(length=500), nullable=True)
    op.alter_column('instanciaciones', 'tamano_bytes', existing_type=sa.BigInteger(), nullable=True)
    op.add_column('instanciaciones', sa.Column('soporte', sa.String(length=40), nullable=True))
    op.add_column('instanciaciones', sa.Column('ubicacion_fisica', sa.String(length=300), nullable=True))
    # Los recortes ya hechos: su relación de derivación con el archivo de origen.
    op.execute("""
        INSERT INTO relaciones (id, origen_tipo, origen_id, destino_tipo, destino_id, tipo_relacion, codigo_ric,
                                origen, estado, creado_en)
        SELECT gen_random_uuid(), 'instanciacion', i.recorte_de_id, 'instanciacion', i.id, 'identidad',
               'has_or_had_derived_instantiation', 'persona', 'vigente', now()
          FROM instanciaciones i
         WHERE i.recorte_de_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM relaciones r WHERE r.destino_id = i.id
                              AND r.codigo_ric = 'has_or_had_derived_instantiation')
    """)


def downgrade() -> None:
    op.drop_column('instanciaciones', 'ubicacion_fisica')
    op.drop_column('instanciaciones', 'soporte')
