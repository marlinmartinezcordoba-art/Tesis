"""
Catálogo de atributos de la descripción (brecha RF-RIC-002).

Cada atributo de un Record Resource declara aquí su tipo, su cardinalidad,
el elemento de ISAD(G) que cubre, la propiedad de RiC-O con la que se
exporta y de dónde sale su procedencia:

- los atributos que el motor puede proponer (título, alcance, idiomas)
  guardan su procedencia en una columna propia (motor, motor corregido por
  una persona, persona) y la confianza del motor;
- los demás los escribe siempre una persona: el motor nunca los propone
  (lo comprueban las pruebas del motor). Quién y cuándo, en las versiones.

Con este catálogo se valida la cardinalidad al publicar y al editar, se
arma la vista interna «atributo · valor · fuente» y se versiona la
descripción (servicios/versiones.py).
"""

from dataclasses import dataclass

from app.models.recurso_documental import RecursoDocumental


class ErrorAtributo(ValueError):
    pass


@dataclass(frozen=True)
class Atributo:
    clave: str  # columna en recursos_documentales
    etiqueta: str
    tipo: str  # texto | texto_largo | codigos | entero | opcion | referencia
    minimo: int  # cardinalidad: mínimo de valores
    maximo: int  # máximo de valores (1 = un solo valor)
    isad: str | None = None
    rico: str | None = None
    origen: str | None = None  # columna con la procedencia, si el motor puede proponerlo
    confianza: str | None = None  # columna con la confianza del motor
    restaurable: bool = True  # una versión anterior lo puede devolver


ATRIBUTOS: tuple[Atributo, ...] = (
    Atributo("titulo", "Título", "texto", 1, 1, "3.1.2", "rico:title", "origen_titulo"),
    Atributo("codigo_referencia", "Código de referencia", "texto", 0, 1, "3.1.1", "rico:identifier"),
    Atributo("fechas_extremas", "Fechas extremas", "texto", 0, 1, "3.1.3", "rico:hasOrHadAllMembersWithCreationDate"),
    Atributo("fechas_extremas_edtf", "Fechas extremas (EDTF)", "texto", 0, 1, "3.1.3", None),
    Atributo("folios", "Folios", "entero", 0, 1, "3.1.5", "rico:recordResourceExtent"),
    Atributo("caja", "Caja", "texto", 0, 1, "3.1.5", "rico:recordResourceExtent"),
    Atributo("carpeta", "Carpeta", "texto", 0, 1, "3.1.5", "rico:recordResourceExtent"),
    Atributo("tomo", "Tomo", "texto", 0, 1, "3.1.5", "rico:recordResourceExtent"),
    Atributo("otra_unidad", "Otra unidad de conservación", "texto", 0, 1, "3.1.5", "rico:recordResourceExtent"),
    Atributo("soporte", "Soporte", "texto", 0, 1, "3.1.5", "rico:recordResourceExtent"),
    Atributo("frecuencia_consulta", "Frecuencia de consulta (FUID)", "opcion", 0, 1),
    Atributo("historia_archivistica", "Historia archivística", "texto_largo", 0, 1, "3.2.3", "rico:history",
             "origen_historia_archivistica"),
    Atributo("forma_ingreso", "Forma de ingreso", "texto_largo", 0, 1, "3.2.4"),
    Atributo("alcance_contenido", "Alcance y contenido", "texto_largo", 0, 1, "3.3.1", "rico:scopeAndContent",
             "origen_alcance", "confianza_alcance"),
    Atributo("valoracion", "Valoración, selección y eliminación", "texto_largo", 0, 1, "3.3.2"),
    Atributo("nuevos_ingresos", "Nuevos ingresos", "texto_largo", 0, 1, "3.3.3", "rico:accruals"),
    Atributo("organizacion", "Organización", "texto_largo", 0, 1, "3.3.4", "rico:structure"),
    Atributo("forma_documental_id", "Forma documental", "referencia", 0, 1, None, "rico:hasDocumentaryFormType"),
    Atributo("condiciones_acceso", "Condiciones de acceso", "texto_largo", 0, 1, "3.4.1", "rico:conditionsOfAccess"),
    Atributo("condiciones_uso", "Condiciones de reproducción", "texto_largo", 0, 1, "3.4.2", "rico:conditionsOfUse"),
    Atributo("idiomas", "Lenguas (ISO 639-3)", "codigos", 0, 5, "3.4.3", "rico:hasOrHadLanguage",
             "origen_idiomas", "confianza_idiomas"),
    Atributo("escrituras", "Escrituras (ISO 15924)", "codigos", 0, 10, "3.4.3"),
    Atributo("instrumentos_descripcion", "Instrumentos de descripción", "texto_largo", 0, 1, "3.4.5"),
    Atributo("localizacion_originales", "Localización de los originales", "texto_largo", 0, 1, "3.5.1"),
    Atributo("localizacion_copias", "Localización de copias", "texto_largo", 0, 1, "3.5.2"),
    Atributo("unidades_relacionadas", "Unidades de descripción relacionadas", "texto_largo", 0, 1, "3.5.3"),
    Atributo("nota_publicaciones", "Nota de publicaciones", "texto_largo", 0, 1, "3.5.4"),
    Atributo("nota", "Notas", "texto_largo", 0, 1, "3.6.1", "rico:generalDescription"),
    Atributo("nota_archivero", "Nota del archivero", "texto_largo", 0, 1, "3.7.1"),
    Atributo("reglas_descripcion", "Reglas o normas", "texto_largo", 0, 1, "3.7.2"),
    Atributo("datos_personales", "Datos personales (Ley 1581)", "opcion", 0, 1),
    Atributo("nota_accesibilidad", "Accesibilidad (Ley 1680)", "texto_largo", 0, 1),
)
POR_CLAVE = {a.clave: a for a in ATRIBUTOS}
# Columnas de procedencia que viajan con su atributo al versionar y restaurar.
PROCEDENCIA = tuple(c for a in ATRIBUTOS for c in (a.origen, a.confianza) if c)


def validar_cardinalidad(clave: str, valores) -> None:
    """Un atributo multivaluado no puede pasar de su máximo; uno obligatorio
    no puede quedar vacío."""
    a = POR_CLAVE[clave]
    if valores is None:
        cuantos = 0
    elif isinstance(valores, (list, tuple, set)):
        cuantos = len([v for v in valores if str(v or "").strip()])
    else:
        cuantos = 1 if str(valores).strip() else 0
    if cuantos > a.maximo:
        raise ErrorAtributo(f"«{a.etiqueta}» admite como máximo {a.maximo} valor{'es' if a.maximo != 1 else ''}; "
                            f"se enviaron {cuantos}.")
    if cuantos < a.minimo:
        raise ErrorAtributo(f"«{a.etiqueta}» es obligatorio.")


def catalogo() -> list[dict]:
    return [{"clave": a.clave, "etiqueta": a.etiqueta, "tipo": a.tipo,
             "cardinalidad": f"{a.minimo}..{'n' if a.maximo > 1 else a.maximo}" + (f" (máx. {a.maximo})" if a.maximo > 1 else ""),
             "minimo": a.minimo, "maximo": a.maximo, "isad": a.isad, "rico": a.rico,
             "procedencia": "columna propia (el motor puede proponerlo)" if a.origen else "siempre una persona"}
            for a in ATRIBUTOS]


def _vacio(valor) -> bool:
    return valor is None or valor == "" or valor == []


def con_fuente(recurso: RecursoDocumental) -> list[dict]:
    """Vista interna: cada atributo con valor, con su fuente y confianza."""
    salida = []
    for a in ATRIBUTOS:
        valor = getattr(recurso, a.clave)
        if _vacio(valor):
            continue
        fuente = (getattr(recurso, a.origen) if a.origen else None) or "persona"
        salida.append({"clave": a.clave, "etiqueta": a.etiqueta, "valor": str(valor) if a.tipo == "referencia" else valor,
                       "fuente": fuente, "confianza": getattr(recurso, a.confianza) if a.confianza else None,
                       "cardinalidad": f"{a.minimo}..{'n' if a.maximo > 1 else a.maximo}", "rico": a.rico, "isad": a.isad})
    return salida
