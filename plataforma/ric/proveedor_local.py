"""Proveedor de IA local para el núcleo RiC: no envía nada fuera del
servidor. Usa spaCy en español para reconocer personas, lugares e
instituciones; no distingue su papel frente al documento (esa es la
limitación conocida frente al proveedor en la nube), así que todo lo que
reconoce queda con la relación genérica RiC-R019 'has or had subject' —
el archivista la corrige a algo más específico (p.ej. R027 'has creator')
si corresponde.
"""

from functools import lru_cache

from .proveedores import ErrorProveedorIA as _ErrorBase
from .proveedores import PropuestaCandidata, ProveedorIA

MODELO_SPACY = "es_core_news_md"

# spaCy: PER=persona, LOC/GPE=lugar, ORG=institución. No hay etiqueta para
# actividad (RiC-E15) ni para institución vs. familia: todo ORG se propone
# como Corporate Body (E11), que la persona archivista corrige si hace falta.
ETIQUETAS_A_RIC = {"PER": "E08", "LOC": "E22", "GPE": "E22", "ORG": "E11"}

# Relación genérica y siempre válida (rango = Thing) para "esto aparece
# mencionado en el documento", ya que spaCy no distingue el papel exacto.
RELACION_GENERICA = "R019"  # has or had subject


class ErrorProveedorIA(_ErrorBase):
    pass


@lru_cache(maxsize=1)
def _cargar_modelo():
    import spacy

    try:
        return spacy.load(MODELO_SPACY)
    except OSError:
        raise ErrorProveedorIA(
            f"Falta el modelo de spaCy «{MODELO_SPACY}». "
            f"Instálelo con: python -m spacy download {MODELO_SPACY}"
        )


class ProveedorLocal(ProveedorIA):
    """No requiere conexión a internet; el texto no sale del servidor."""

    nombre = "local-spacy"

    def __init__(self):
        self.version = MODELO_SPACY

    def proponer(self, record, texto):
        nlp = _cargar_modelo()
        self.version = f"{MODELO_SPACY} {nlp.meta.get('version', '')}".strip()
        doc = nlp(texto[:100_000])

        propuestas, vistas = [], set()
        for ent in doc.ents:
            ric_id = ETIQUETAS_A_RIC.get(ent.label_)
            nombre = ent.text.strip()
            if not ric_id or not nombre:
                continue
            clave = (ric_id, nombre.lower())
            if clave in vistas:
                continue
            vistas.add(clave)
            propuestas.append(PropuestaCandidata(
                relacion_id=RELACION_GENERICA,
                entidad_tipo=ric_id,
                entidad_nombre=nombre,
                evidencia=nombre,
                confianza=0.55,  # reconocimiento de entidades sin verificación semántica
                justificacion=f"Entidad reconocida por spaCy ({MODELO_SPACY}).",
            ))
        return propuestas
