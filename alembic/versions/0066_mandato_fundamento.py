"""La norma que un documento cita como fundamento lo regula (RiC-R063), no es su tema.

Hasta ahora, un mandato citado sin una actividad que lo enlazara quedaba como tema del documento
(rico:hasOrHadSubject, «trata de»). La ley o el decreto que se cita como fundamento regula el documento:
rico:Mandate, subclase de rico:Rule, rico:regulatesOrRegulated. Nada se borra: la relación anterior queda
anulada y se crea la nueva con la misma evidencia (fragmento, página, propuesta, quién la confirmó).

Revision ID: 0066
Revises: 0065
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0066'
down_revision: Union[str, None] = '0065'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COPIADAS = ("tipo_relacion, fragmento, fragmento_instanciacion_id, fragmento_inicio, fragmento_pagina, fragmento_zona, "
            "propuesta_id, estado, confirmada_por_id, fecha_edtf, nota, origen, confianza, motor, motor_id, "
            "estado_revision")


def upgrade() -> None:
    op.execute(f"""
        INSERT INTO relaciones (id, origen_tipo, origen_id, destino_tipo, destino_id, codigo_ric, rol, creado_en, {COPIADAS})
        SELECT gen_random_uuid(), 'entidad_vocabulario', destino_id, 'recurso_documental', origen_id,
               'regulates_or_regulated', 'fundamento', creado_en, {COPIADAS}
        FROM relaciones
        WHERE codigo_ric = 'has_or_had_subject' AND rol = 'mandato' AND estado = 'vigente'
          AND origen_tipo = 'recurso_documental' AND destino_tipo = 'entidad_vocabulario'
    """)
    op.execute("""
        UPDATE relaciones SET estado = 'anulada', anulada_en = now(),
               nota = left(coalesce(nota || ' · ', '') || 'Reemplazada: la norma citada regula el documento (RiC-R063)', 500)
        WHERE codigo_ric = 'has_or_had_subject' AND rol = 'mandato' AND estado = 'vigente'
          AND origen_tipo = 'recurso_documental' AND destino_tipo = 'entidad_vocabulario'
    """)
    # El grafo RDF de cada fondo se vuelve a sincronizar con las relaciones nuevas.
    op.execute("""
        INSERT INTO grafos_rdf (id, fondo_id, alcance)
        SELECT gen_random_uuid(), f.id, a.alcance
        FROM (SELECT id FROM recursos_documentales WHERE nivel = 'fondo') AS f(id)
        CROSS JOIN (VALUES ('publico'), ('completo')) AS a(alcance)
        ON CONFLICT (fondo_id, alcance)
        DO UPDATE SET version_datos = grafos_rdf.version_datos + 1, cambiado_en = now()
    """)


def downgrade() -> None:
    # No se deshace: las relaciones anuladas conservan la historia y las nuevas son la corrección.
    pass
