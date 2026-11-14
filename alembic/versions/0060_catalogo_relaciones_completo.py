"""catálogo de relaciones completo: toda relación de RiC-CM 1.0 que RiC-O 1.1 implementa

Las relaciones que el sistema ya escribía al exportar (fechas, original y copia, regla expresada
en su documento, migraciones) entran en el catálogo único, y las que nadie podía declarar
(asociación con un evento, un lugar o una regla, parte de, procedencia orgánica…) se pueden
declarar. Solo agrega valores al tipo enumerado: no cambia datos.

Revision ID: 0060
Revises: 0059

"""
from typing import Sequence, Union

from alembic import op

revision: str = '0060'
down_revision: Union[str, None] = '0059'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODIGOS = ('has_or_had_part', 'has_or_had_subevent', 'precedes_in_time', 'has_child', 'describes_or_described', 'is_record_resource_associated_with_record_resource', 'has_genetic_link_to_record_resource', 'has_organic_provenance', 'is_instantiation_associated_with_instantiation', 'is_functionally_equivalent_to', 'has_sibling', 'has_or_had_spouse', 'is_event_associated_with', 'results_or_resulted_in', 'is_rule_associated_with', 'is_or_was_enforced_by', 'is_birth_date_of', 'is_death_date_of', 'is_place_associated_with', 'is_or_was_creation_date_of_all_members_of', 'is_or_was_creation_date_of_some_members_of', 'is_or_was_creation_date_of_most_members_of', 'is_date_of_occurrence_of', 'is_within', 'intersects')


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for c in CODIGOS:
            op.execute(f"ALTER TYPE codigo_relacion_ric ADD VALUE IF NOT EXISTS '{c}'")


def downgrade() -> None:
    # PostgreSQL no quita valores de un tipo enumerado; quedan sin uso.
    pass
