"""
ISAD(G) 2.ª ed. completa sobre el Record Resource (hallazgo DES-07).

Una sola tabla con los 26 elementos: de dónde sale cada uno en el sistema
(columna propia, relación, ficha del agente, lote de transferencia, regla de
retención, instanciaciones) y con qué propiedad de RiC-O se exporta, o por
qué no tiene una. La ficha ISAD(G) de cualquier unidad de descripción se
arma con esta tabla; una prueba exige que los 26 tengan fuente.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Fecha, Relacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import fechas

# Textos que escribe una persona (columna → elemento ISAD-G).
CAMPOS_TEXTO = {
    "forma_ingreso": "3.2.4",
    "valoracion": "3.3.2",
    "nuevos_ingresos": "3.3.3",
    "organizacion": "3.3.4",
    "instrumentos_descripcion": "3.4.5",
    "localizacion_originales": "3.5.1",
    "localizacion_copias": "3.5.2",
    "unidades_relacionadas": "3.5.3",
    "nota_publicaciones": "3.5.4",
    "nota": "3.6.1",
    "nota_archivero": "3.7.1",
    "reglas_descripcion": "3.7.2",
}

# Escrituras (ISO 15924) que puede tener un fondo colombiano y su contexto.
# Código de cuatro letras: la primera en mayúscula.
ESCRITURAS = {
    "Latn": "latina", "Grek": "griega", "Hebr": "hebrea", "Arab": "árabe", "Cyrl": "cirílica",
    "Hani": "han (china)", "Jpan": "japonesa", "Zmth": "notación matemática", "Zsym": "símbolos",
    "Zyyy": "común (sin escritura determinada)", "Zxxx": "sin escritura (no escrito)", "Zzzz": "escritura desconocida",
}
NOMBRE_NIVEL = {"fondo": "Fondo", "seccion": "Sección", "subseccion": "Subsección", "serie": "Serie",
                "subserie": "Subserie", "expediente": "Expediente", "unidad_documental": "Unidad documental",
                "parte_documental": "Parte documental"}


class ErrorIsadg(ValueError):
    pass


def escrituras_validas(valores: list[str] | None) -> list[str] | None:
    if valores is None:
        return None
    salida = []
    for v in valores:
        v = (v or "").strip()
        if not v:
            continue
        v = v[:1].upper() + v[1:].lower()
        if not re.fullmatch(r"[A-Z][a-z]{3}", v) or v not in ESCRITURAS:
            raise ErrorIsadg(f"«{v}» no es un código de escritura ISO 15924 admitido "
                             f"({', '.join(sorted(ESCRITURAS))}).")
        if v not in salida:
            salida.append(v)
    return salida or None


def aplicar(recurso: RecursoDocumental, textos: dict | None, escrituras: list[str] | None) -> None:
    """None: no cambia; texto vacío: se borra el dato. Los escribe siempre una persona."""
    for campo, valor in (textos or {}).items():
        if campo not in CAMPOS_TEXTO:
            raise ErrorIsadg(f"«{campo}» no es un elemento de ISAD(G) editable.")
        if valor is not None:
            setattr(recurso, campo, (valor or "").strip()[:20000] or None)
    if escrituras is not None:
        recurso.escrituras = escrituras_validas(escrituras)


def valores(recurso: RecursoDocumental) -> dict:
    return {c: getattr(recurso, c) for c in CAMPOS_TEXTO} | {"escrituras": recurso.escrituras or []}


# --- Ficha ISAD(G) ------------------------------------------------------------------------

AREAS = {"3.1": "Identificación", "3.2": "Contexto", "3.3": "Contenido y estructura",
         "3.4": "Condiciones de acceso y uso", "3.5": "Documentación asociada", "3.6": "Notas",
         "3.7": "Control de la descripción"}

# Elemento → (nombre, fuente en el sistema, exportación RiC-O).
ELEMENTOS = {
    "3.1.1": ("Código de referencia", "codigo_referencia", "rico:identifier"),
    "3.1.2": ("Título", "titulo", "rico:title"),
    "3.1.3": ("Fecha(s)", "fechas: nodo Date (creación) y fechas extremas EDTF",
              "rico:hasCreationDate · rico:hasOrHadAllMembersWithCreationDate"),
    "3.1.4": ("Nivel de descripción", "nivel", "rico:hasRecordSetType / clase Record, RecordPart"),
    "3.1.5": ("Volumen y soporte", "folios, caja, carpeta, soporte", "rico:recordResourceExtent"),
    "3.2.1": ("Nombre del o de los productores", "relación has_creator al agente", "rico:hasCreator"),
    "3.2.2": ("Historia institucional / reseña biográfica", "historia del productor (ficha de autoridad)",
              "rico:history (del agente)"),
    "3.2.3": ("Historia archivística", "historia_archivistica y cadena de custodia",
              "rico:history · rico:hasOrHadHolder"),
    "3.2.4": ("Forma de ingreso", "lote de transferencia confirmado + forma_ingreso",
              "rico:hasOrHadHolder (custodia anterior); el texto no tiene propiedad"),
    "3.3.1": ("Alcance y contenido", "alcance_contenido", "rico:scopeAndContent"),
    "3.3.2": ("Valoración, selección y eliminación", "regla de retención (TRD) + valoracion",
              "rico:regulatesOrRegulated desde la regla (rico:Rule)"),
    "3.3.3": ("Nuevos ingresos", "nuevos_ingresos", "rico:accruals (solo agrupaciones)"),
    "3.3.4": ("Organización", "organizacion", "rico:structure"),
    "3.4.1": ("Condiciones de acceso", "condiciones_acceso", "rico:conditionsOfAccess"),
    "3.4.2": ("Condiciones de reproducción", "condiciones_uso", "rico:conditionsOfUse"),
    "3.4.3": ("Lengua / escritura", "idiomas (ISO 639-3) y escrituras (ISO 15924)",
              "rico:hasOrHadLanguage; la escritura no tiene propiedad"),
    "3.4.4": ("Características físicas y requisitos técnicos",
              "instanciaciones: formato PRONOM, soporte y características físicas del original",
              "rico:physicalCharacteristicsNote · rico:hasCarrierType (de la instanciación)"),
    "3.4.5": ("Instrumentos de descripción", "instrumentos que genera el sistema + instrumentos_descripcion", None),
    "3.5.1": ("Existencia y localización de los originales", "original físico registrado + localizacion_originales",
              "rico:hasOrHadInstantiation (original físico)"),
    "3.5.2": ("Existencia y localización de copias", "localizacion_copias", None),
    "3.5.3": ("Unidades de descripción relacionadas", "secuencia, partes, relacionadas + unidades_relacionadas",
              "rico:precedesOrPreceded · rico:hasOrHadConstituent · rico:isRelatedTo"),
    "3.5.4": ("Nota de publicaciones", "nota_publicaciones", None),
    "3.6.1": ("Notas", "nota", "rico:generalDescription"),
    "3.7.1": ("Nota del archivero", "nota_archivero + quién publicó", None),
    "3.7.2": ("Reglas o normas", "reglas_descripcion", None),
    "3.7.3": ("Fecha(s) de la descripción", "publicado_en, actualizado_en", None),
}

# Por qué algunos elementos no tienen propiedad en RiC-O 1.1 (se conservan en
# el sistema y en la ficha ISAD(G), no en el RDF).
SIN_PROPIEDAD_RICO = {
    "3.4.5": "RiC-O enlazaría el instrumento como otro Record Resource (isOrWasDescribedBy); un texto no tiene "
             "propiedad.",
    "3.5.2": "R012 hasCopy une dos Record Resources descritos; la localización de una copia fuera del archivo es "
             "texto sin propiedad.",
    "3.5.4": "RiC-O no tiene una propiedad literal para la bibliografía sobre la unidad.",
    "3.7.1": "Área 7: metadatos de la descripción misma; RiC-O describe el documento, no el registro descriptivo.",
    "3.7.2": "Mismo motivo que 3.7.1 (rico:ruleFollowed es la regla que rige el documento, no la descripción).",
    "3.7.3": "Mismo motivo que 3.7.1.",
}


def _fechas(db: Session, recurso: RecursoDocumental) -> str | None:
    partes = []
    if recurso.fechas_extremas_edtf or recurso.fechas_extremas:
        partes.append(recurso.fechas_extremas or fechas.legible(recurso.fechas_extremas_edtf))
    for f in db.scalars(select(Fecha).join(Relacion, Relacion.origen_id == Fecha.id).where(
            Relacion.destino_id == recurso.id, Relacion.codigo_ric == "is_creation_date_of",
            Relacion.estado == "vigente")).all():
        partes.append(fechas.legible(f.edtf, f.expresion) if f.edtf else f.expresion)
    return "; ".join(partes) or None


def _agentes(db: Session, recurso: RecursoDocumental, codigo: str) -> list[EntidadVocabulario]:
    return list(db.scalars(select(EntidadVocabulario).join(Relacion, Relacion.destino_id == EntidadVocabulario.id)
                           .where(Relacion.origen_id == recurso.id, Relacion.codigo_ric == codigo,
                                  Relacion.estado == "vigente")).all())


def _instancias(db: Session, recurso: RecursoDocumental) -> list[Instanciacion]:
    return list(db.scalars(select(Instanciacion).join(Relacion, Relacion.destino_id == Instanciacion.id).where(
        Relacion.origen_id == recurso.id, Relacion.codigo_ric == "has_or_had_instantiation",
        Relacion.estado == "vigente")).all())


def _unir(*partes) -> str | None:
    return "; ".join(p for p in partes if p) or None


def ficha(db: Session, recurso: RecursoDocumental) -> list[dict]:
    """Los 26 elementos con su valor (o vacío) y de dónde sale cada uno."""
    from app.servicios import lotes, retencion

    productores = _agentes(db, recurso, "has_creator")
    instancias = _instancias(db, recurso)
    digitales = sorted({i.formato_nombre or i.formato_puid for i in instancias
                        if i.estado != "registro_fisico" and (i.formato_nombre or i.formato_puid)})
    fisicos = [i for i in instancias if i.estado == "registro_fisico"]
    volumen = ", ".join(x for x in (f"{recurso.folios} folios" if recurso.folios is not None else None,
                                    f"caja {recurso.caja}" if recurso.caja else None,
                                    f"carpeta {recurso.carpeta}" if recurso.carpeta else None,
                                    recurso.soporte) if x) or None
    reglas_ret = retencion.retencion_de(db, recurso)
    relacionadas = db.scalars(select(Relacion).where(
        Relacion.estado == "vigente", Relacion.codigo_ric.in_(("precedes_or_preceded", "is_related_to")),
        ((Relacion.origen_id == recurso.id) | (Relacion.destino_id == recurso.id)),
        Relacion.origen_tipo == "recurso_documental", Relacion.destino_tipo == "recurso_documental")).all()
    titulos_rel = []
    for r in relacionadas:
        otro = db.get(RecursoDocumental, r.destino_id if r.origen_id == recurso.id else r.origen_id)
        if otro is not None:
            titulos_rel.append(otro.titulo)
    publicado_por = None
    if recurso.publicado_por_id:
        from app.models.usuario import Usuario

        u = db.get(Usuario, recurso.publicado_por_id)
        publicado_por = f"Descrito por {u.nombre}" if u else None
    idiomas = ", ".join(recurso.idiomas or [])
    escrituras = ", ".join(f"{c} ({ESCRITURAS.get(c, c)})" for c in recurso.escrituras or [])
    valor = {
        "3.1.1": recurso.codigo_referencia,
        "3.1.2": recurso.titulo,
        "3.1.3": _fechas(db, recurso),
        "3.1.4": NOMBRE_NIVEL.get(recurso.nivel, recurso.nivel),
        "3.1.5": volumen,
        "3.2.1": ", ".join(a.nombre for a in productores) or None,
        "3.2.2": " ".join(a.historia for a in productores if a.historia) or None,
        "3.2.3": recurso.historia_archivistica,
        "3.2.4": _unir(lotes.forma_ingreso_de(db, recurso), recurso.forma_ingreso),
        "3.3.1": recurso.alcance_contenido,
        "3.3.2": _unir(_texto_retencion(reglas_ret), recurso.valoracion),
        "3.3.3": recurso.nuevos_ingresos,
        "3.3.4": recurso.organizacion,
        "3.4.1": recurso.condiciones_acceso,
        "3.4.2": recurso.condiciones_uso,
        "3.4.3": _unir(f"Lenguas: {idiomas}" if idiomas else None, f"Escrituras: {escrituras}" if escrituras else None),
        "3.4.4": _unir(f"Formatos digitales: {', '.join(digitales)}" if digitales else None,
                       *(f"Original en {i.soporte or 'soporte sin indicar'}"
                         + (f": {i.caracteristicas_fisicas}" if i.caracteristicas_fisicas else "") for i in fisicos)),
        "3.4.5": _unir("Inventario documental (FUID) y guía del fondo, generados por el sistema"
                       if recurso.publicado_en else None, recurso.instrumentos_descripcion),
        "3.5.1": _unir(*(f"Original en {i.soporte or 'soporte'}: {i.ubicacion_fisica}" for i in fisicos
                         if i.ubicacion_fisica), recurso.localizacion_originales),
        "3.5.2": recurso.localizacion_copias,
        "3.5.3": _unir(", ".join(titulos_rel) if titulos_rel else None, recurso.unidades_relacionadas),
        "3.5.4": recurso.nota_publicaciones,
        "3.6.1": recurso.nota,
        "3.7.1": _unir(publicado_por, recurso.nota_archivero),
        "3.7.2": recurso.reglas_descripcion,
        "3.7.3": _unir(f"Publicada el {recurso.publicado_en.date().isoformat()}" if recurso.publicado_en else None,
                       f"actualizada el {recurso.actualizado_en.date().isoformat()}" if recurso.actualizado_en else None),
    }
    return [{"elemento": e, "area": AREAS[e[:3]], "nombre": n, "valor": valor[e], "fuente": fuente, "rico": rico,
             "sin_propiedad": SIN_PROPIEDAD_RICO.get(e)} for e, (n, fuente, rico) in ELEMENTOS.items()]


def _texto_retencion(r: dict | None) -> str | None:
    if not r:
        return None
    texto = f"Regla de retención «{r['regla']['nombre']}»: {r['resumen']}"
    if r.get("heredada_de"):
        texto += f" (heredada de {NOMBRE_NIVEL.get(r['heredada_de']['nivel'], '')} «{r['heredada_de']['titulo']}»)"
    return texto
