"""cierre de la auditoría RiC: datos de relaciones que RiC-O no admite

- CM-05 y CM-12: restricciones de la base para el subtipo de agente y el
  tipo de lugar.
- O-29: la fecha de expedición de un mandato estaba con isCreationDateOf
  (R080), cuyo rango es Record Resource o Instantiation. Pasa a
  isDateAssociatedWith (R068, rango Thing) con rol «expedicion». La fila no
  se borra: cambia su código y queda la nota.

Revision ID: 0018
Revises: 0017

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0018'
down_revision: Union[str, None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUBTIPOS_AGENTE = ("persona", "entidad_corporativa", "grupo", "cargo", "familia", "mecanismo")
TIPOS_LUGAR = ("pais", "departamento", "provincia", "municipio", "corregimiento", "vereda", "barrio", "edificio",
               "otro")


def upgrade() -> None:
    # CM-05: la jerarquía de subtipos del agente es una restricción de la base.
    # NOT VALID: rige para lo nuevo sin bloquear el despliegue por un dato viejo.
    lista = ", ".join(f"'{s}'" for s in SUBTIPOS_AGENTE)
    op.execute(f"ALTER TABLE entidades_vocabulario ADD CONSTRAINT ck_subtipo_agente "
               f"CHECK (clase <> 'agente' OR subtipo IS NULL OR subtipo IN ({lista})) NOT VALID")
    # CM-12: un solo vocabulario de tipos de lugar.
    lugares = ", ".join(f"'{t}'" for t in TIPOS_LUGAR)
    op.execute(f"ALTER TABLE entidades_vocabulario ADD CONSTRAINT ck_tipo_lugar "
               f"CHECK (tipo_lugar IS NULL OR tipo_lugar IN ({lugares})) NOT VALID")
    op.execute("""
        UPDATE relaciones SET codigo_ric = 'is_date_associated_with', rol = 'expedicion',
               nota = coalesce(nota || ' · ', '') || 'Antes isCreationDateOf (O-29, 2026-10-03)'
         WHERE codigo_ric = 'is_creation_date_of' AND origen_tipo = 'fecha'
           AND destino_tipo = 'entidad_vocabulario'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE entidades_vocabulario DROP CONSTRAINT IF EXISTS ck_tipo_lugar")
    op.execute("ALTER TABLE entidades_vocabulario DROP CONSTRAINT IF EXISTS ck_subtipo_agente")
    op.execute("""
        UPDATE relaciones SET codigo_ric = 'is_creation_date_of', rol = NULL
         WHERE codigo_ric = 'is_date_associated_with' AND rol = 'expedicion'
    """)
