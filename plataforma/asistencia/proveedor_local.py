"""Proveedor de IA local: no envía nada fuera del servidor de la entidad.

Usa spaCy en español para reconocer personas, lugares e instituciones, y
reglas simples para fechas. No redacta título ni resumen: eso requiere un
modelo de lenguaje generativo, que en este proveedor no está disponible.

Se usa cuando el documento está restringido, cuando la entidad no puede
enviar información a la nube por su política de datos, o como opción sin
costo. El modelo de spaCy se carga una sola vez por proceso.
"""

import re
from functools import lru_cache

from acervo.models import UnidadClasificacion

from .proveedores import Propuesta, ProveedorIA

MODELO_SPACY = "es_core_news_md"

# spaCy: PER=persona, LOC/GPE=lugar, ORG=institución.
ETIQUETAS = {"PER": "persona", "LOC": "lugar", "GPE": "lugar", "ORG": "institucion"}

ANIO = re.compile(r"\b(1[5-9]\d{2}|20[0-2]\d)\b")


class ErrorProveedorIA(Exception):
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

    def proponer(self, documento, texto):
        if not texto.strip():
            raise ErrorProveedorIA("El documento no tiene texto. Extraiga el texto primero.")

        nlp = _cargar_modelo()
        self.version = f"{MODELO_SPACY} {nlp.meta.get('version', '')}".strip()
        doc = nlp(texto[:100_000])  # límite razonable para un documento de archivo

        propuestas = []
        vistas = set()
        for ent in doc.ents:
            tipo = ETIQUETAS.get(ent.label_)
            nombre = ent.text.strip()
            if not tipo or not nombre:
                continue
            clave = (tipo, nombre.lower())
            if clave in vistas:
                continue
            vistas.add(clave)
            propuestas.append(Propuesta(
                proceso="descripcion",
                campo=tipo,
                valor=nombre,
                confianza=0.55,  # reconocimiento de entidades sin verificación semántica
                justificacion=f"{tipo.capitalize()} reconocida por spaCy ({MODELO_SPACY}).",
                evidencia=nombre,
                criterios=["DES-02", "DES-03", "ACC-02"],
            ))

        anios = sorted({int(a) for a in ANIO.findall(texto)})
        if anios:
            valor = str(anios[0]) if len(anios) == 1 else f"{anios[0]}-{anios[-1]}"
            propuestas.append(Propuesta(
                proceso="descripcion",
                campo="fechas",
                valor=valor,
                confianza=0.5,
                justificacion=f"Años encontrados en el texto: {anios}",
                evidencia=str(anios[0]),
                criterios=["DES-01", "DES-02", "DES-03"],
            ))
        return propuestas


def _normalizar(s):
    return " ".join(s.lower().split())


class ProveedorClasificacionLocal(ProveedorIA):
    """Propone la serie por coincidencia de palabras clave, sin conexión a
    internet. Es más simple que un modelo de lenguaje: solo compara qué
    unidad del cuadro tiene más palabras clave presentes en el texto."""

    nombre = "local-reglas"
    version = "0.1"

    def proponer(self, documento, texto):
        if not texto.strip():
            raise ErrorProveedorIA("El documento no tiene texto. Extraiga el texto primero.")

        texto_norm = _normalizar(texto)
        unidades = list(
            UnidadClasificacion.objects.filter(
                tipo__in=[UnidadClasificacion.Tipo.SERIE, UnidadClasificacion.Tipo.SUBSERIE]
            ).exclude(palabras_clave="")
        )
        if not unidades:
            raise ErrorProveedorIA(
                "No hay unidades del cuadro de clasificación con palabras clave cargadas."
            )

        mejor, mejor_coincidencias = None, []
        for unidad in unidades:
            terminos = [t.strip() for t in unidad.palabras_clave.split(",") if t.strip()]
            coincidencias = [t for t in terminos if _normalizar(t) in texto_norm]
            if len(coincidencias) > len(mejor_coincidencias):
                mejor, mejor_coincidencias = unidad, coincidencias

        if not mejor or not mejor_coincidencias:
            return []  # ninguna serie coincide: mejor no proponer que adivinar

        confianza = min(0.3 + 0.1 * len(mejor_coincidencias), 0.6)
        return [Propuesta(
            proceso="clasificacion",
            campo="clasificacion",
            valor=mejor.codigo,
            confianza=confianza,
            justificacion=f"Coincide con las palabras clave de «{mejor.nombre}»: {', '.join(mejor_coincidencias)}.",
            evidencia=mejor_coincidencias[0],
            criterios=["CLA-01", "CLA-02", "CLA-03"],
        )]
