"""
Grafo de contexto del fondo: el subgrafo RiC alrededor de una entidad raíz,
acotado a 1, 2 o 3 saltos y a cuatro filtros (tipo de entidad, tipo de
relación, rango de fechas y estado de la descripción).

Lee las mismas tablas relacionales que la descripción ya mantiene
(`relaciones`, la jerarquía de `recursos_documentales` y la forma
documental); no modela nada nuevo. La visibilidad es la de la exportación
RiC-O, por construcción: se usa su misma función, así que lo que no se
exporta (borradores, lo clasificado o reservado para quien no puede verlo,
lo que cuelga de un nivel oculto, los mecanismos) tampoco se dibuja.

Los filtros se aplican durante el recorrido, no después: una entidad que no
pasa el filtro no aparece y el recorrido no sigue a través de ella. Así el
dibujo nunca muestra islas sueltas que solo se conectaban por algo oculto.
La entidad raíz siempre se muestra.
"""

import io
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from rdflib import RDF, RDFS, Graph, Literal, URIRef
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.descripcion import Actividad, EntidadVocabulario, Fecha, Relacion, TrabajoDescripcion
from app.models.enums import URI_RICO
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, fechas, ric_o, vocabulario
from app.servicios.decisiones_ia import SUBTIPO_NOMBRE
from app.servicios.instrumentos import ETIQUETA_RELACION, NIVEL_NOMBRE, ErrorInstrumento, sin_campos_internos

TIPOS_RAIZ = ("recurso_documental", "entidad_vocabulario", "fecha", "instanciacion")
SALTOS_MAXIMOS = 3
# Por encima de este número el SVG deja de ser fluido y el dibujo, legible
# (prueba de carga y tabla de decisión en la documentación).
MAX_NODOS = 300

# Tipo de entidad RiC de cada nodo, el que se filtra y se colorea.
FAMILIAS = {
    "RecordSet": "Agrupación documental (Record Set)",
    "Record": "Documento (Record)",
    "RecordPart": "Parte documental (Record Part)",
    "Agent": "Agente (Agent)",
    "Place": "Lugar (Place)",
    "Activity": "Actividad (Activity)",
    "Date": "Fecha (Date)",
    "Instantiation": "Archivo (Instantiation)",
    "DocumentaryFormType": "Forma documental (Documentary Form Type)",
    "ActivityType": "Tipo de actividad (Activity Type)",
    "Mandate": "Mandato o norma (Mandate)",
}
_FAMILIA_CLASE = {"agente": "Agent", "lugar": "Place", "actividad": "Activity", "tipo_actividad": "ActivityType",
                  "mandato": "Mandate", "forma_documental": "DocumentaryFormType", "tipo_parte": "DocumentaryFormType"}
_FAMILIA_NIVEL = {"unidad_documental": "Record", "parte_documental": "RecordPart"}
# Estado de la descripción de un Record Resource visible en el grafo. Los
# borradores nunca se dibujan (ver documentación), así que no son opción.
ESTADOS = {"publicada": "Publicada", "en_edicion": "Publicada, reabierta para corregir"}
# La única relación del catálogo sin dirección (RiC-O no distingue un extremo).
SIMETRICAS = {"is_agent_associated_with_agent"}
_AÑOS = re.compile(r"^\s*(\d{4})\s*(?:[–—-]\s*(\d{4}))?\s*$")


@dataclass
class Filtros:
    familias: set[str] = field(default_factory=set)
    relaciones: set[str] = field(default_factory=set)
    desde: date | None = None
    hasta: date | None = None
    estados: set[str] = field(default_factory=set)

    def activos(self) -> int:
        return sum(bool(x) for x in (self.familias, self.relaciones, self.desde or self.hasta, self.estados))

    def describir(self) -> str:
        """Para el nombre del archivo exportado: deja claro que es un fragmento."""
        partes = []
        if self.familias:
            partes.append("tipos-" + "-".join(sorted(self.familias)))
        if self.relaciones:
            partes.append(f"{len(self.relaciones)}-relaciones")
        if self.desde or self.hasta:
            partes.append(f"{self.desde or 'inicio'}_a_{self.hasta or 'hoy'}")
        if self.estados:
            partes.append("-".join(sorted(self.estados)))
        return "_".join(partes) or "sin-filtros"


def _se_cruza(inicio: date | None, fin: date | None, f: Filtros) -> bool:
    """¿El intervalo de la entidad cae en el rango? Sin fecha no se excluye:
    no hay evidencia de que caiga fuera."""
    if inicio is None and fin is None:
        return True
    if f.hasta and inicio and inicio > f.hasta:
        return False
    if f.desde and fin and fin < f.desde:
        return False
    return True


def _limites_edtf(edtf: str | None) -> tuple[date | None, date | None]:
    if not edtf:
        return None, None
    try:
        i = fechas.interpretar(edtf)
        return i.inicio, i.fin
    except fechas.FechaInvalida:
        return None, None


class _Contexto:
    """Lo que se calcula una vez por consulta: las descripciones visibles del
    fondo, sus fechas y cuáles están reabiertas, y cachés de nodos."""

    def __init__(self, db: Session, fondo: RecursoDocumental, ver_restringidos: bool):
        self.db, self.fondo = db, fondo
        self.recursos = exportacion_rico._recursos(db, fondo, ver_restringidos, Counter())
        self.hijos: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        self.por_forma: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for r in self.recursos.values():
            if r.id != fondo.id and r.incluido_en_id in self.recursos:
                self.hijos[r.incluido_en_id].append(r.id)
            forma = r.tipo_parte_id if r.nivel == "parte_documental" else r.forma_documental_id
            if forma:
                self.por_forma[forma].append(r.id)
        ids = list(self.recursos)
        self.reabiertas = set(db.scalars(select(TrabajoDescripcion.recurso_id).where(
            TrabajoDescripcion.estado == "abierto", TrabajoDescripcion.recurso_id.in_(ids))))
        # Fechas de cada descripción: sus fechas extremas y las fechas RiC
        # (Date) que tiene relacionadas.
        self.fechas_recurso: dict[uuid.UUID, list[tuple[date | None, date | None]]] = defaultdict(list)
        for r in self.recursos.values():
            m = _AÑOS.match(r.fechas_extremas or "")
            if m:
                self.fechas_recurso[r.id].append((date(int(m.group(1)), 1, 1), date(int(m.group(2) or m.group(1)), 12, 31)))
        enlaces = db.execute(select(Relacion.origen_tipo, Relacion.origen_id, Relacion.destino_id).where(
            Relacion.estado == "vigente",
            or_((Relacion.origen_tipo == "fecha") & Relacion.destino_id.in_(ids),
                (Relacion.destino_tipo == "fecha") & Relacion.origen_id.in_(ids)))).all()
        if enlaces:
            fechas_ = {f.id: f for f in db.scalars(select(Fecha).where(Fecha.id.in_(
                [o if t == "fecha" else d for t, o, d in enlaces])))}
            for t, o, d in enlaces:
                f = fechas_.get(o if t == "fecha" else d)
                if f is not None:
                    self.fechas_recurso[d if t == "fecha" else o].append(_limites_fecha(f))
        self._entidades: dict[uuid.UUID, EntidadVocabulario | None] = {}
        self._fechas: dict[uuid.UUID, Fecha | None] = {}
        self._instancias: dict[uuid.UUID, Instanciacion | None] = {}
        self._actividades: dict[uuid.UUID, Actividad | None] = {}

    def precargar(self, pares: list[tuple[str, uuid.UUID]]) -> None:
        """Carga en lote los nodos que aún no se conocen (un SELECT por tabla)."""
        for tipo, modelo, cache in (("entidad_vocabulario", EntidadVocabulario, self._entidades),
                                    ("fecha", Fecha, self._fechas), ("instanciacion", Instanciacion, self._instancias),
                                    ("actividad", Actividad, self._actividades)):
            faltan = {i for t, i in pares if t == tipo and i not in cache}
            if faltan:
                encontrados = {x.id: x for x in self.db.scalars(select(modelo).where(modelo.id.in_(faltan)))}
                for i in faltan:
                    cache[i] = encontrados.get(i)

    def nodo(self, tipo: str, ident: uuid.UUID) -> dict | None:
        """Datos públicos de un nodo, o None si no es visible."""
        fid = self.fondo.id
        if tipo == "recurso_documental":
            r = self.recursos.get(ident)
            if r is None:
                return None
            familia = _FAMILIA_NIVEL.get(r.nivel, "RecordSet")
            ints = self.fechas_recurso.get(r.id, [])
            inicios = [a for a, _ in ints if a]
            fines = [b for _, b in ints if b]
            return {"tipo": tipo, "clase": r.nivel, "familia": familia, "etiqueta": r.titulo,
                    "subtitulo": NIVEL_NOMBRE[r.nivel],
                    "estado": "en_edicion" if r.id in self.reabiertas else "publicada",
                    "fecha_inicio": min(inicios) if inicios else None, "fecha_fin": max(fines) if fines else None}
        if tipo == "entidad_vocabulario":
            self.precargar([(tipo, ident)])
            e = self._entidades.get(ident)
            if e is None or e.fondo_id != fid or e.estado != "activa" or e.subtipo == "mecanismo":
                return None
            return {"tipo": tipo, "clase": e.clase, "familia": _FAMILIA_CLASE[e.clase], "etiqueta": e.nombre,
                    "subtitulo": e.subtipo, "estado": None,
                    "fecha_inicio": e.existencia_inicio, "fecha_fin": e.existencia_fin}
        if tipo == "fecha":
            self.precargar([(tipo, ident)])
            f = self._fechas.get(ident)
            if f is None:
                return None
            inicio, fin = _limites_fecha(f)
            return {"tipo": tipo, "clase": "fecha", "familia": "Date", "etiqueta": fechas.legible(f.edtf, f.expresion),
                    "subtitulo": f.edtf, "estado": None, "fecha_inicio": inicio, "fecha_fin": fin}
        if tipo == "instanciacion":
            self.precargar([(tipo, ident)])
            i = self._instancias.get(ident)
            if i is None or i.fondo_id != fid or i.estado != "listo_para_descripcion":
                return None
            return {"tipo": tipo, "clase": "instanciacion", "familia": "Instantiation", "etiqueta": i.nombre_original,
                    "subtitulo": i.formato_puid, "estado": None, "fecha_inicio": None, "fecha_fin": None}
        if tipo == "actividad":
            self.precargar([(tipo, ident)])
            a = self._actividades.get(ident)
            if a is None or a.fondo_id != fid:
                return None
            return {"tipo": tipo, "clase": "actividad", "familia": "Activity", "etiqueta": a.nombre, "subtitulo": None,
                    "estado": None, "fecha_inicio": None, "fecha_fin": None}
        return None

    def vecinos(self, frontera: list[tuple[str, uuid.UUID]]) -> list[tuple]:
        """Aristas candidatas alrededor de la frontera:
        (tipo_o, id_o, tipo_d, id_d, código, fecha EDTF, registrada en)."""
        ids = [i for _, i in frontera]
        filas = self.db.scalars(select(Relacion).where(
            Relacion.estado == "vigente", or_(Relacion.origen_id.in_(ids), Relacion.destino_id.in_(ids)))).all()
        salida = [(r.origen_tipo, r.origen_id, r.destino_tipo, r.destino_id, r.codigo_ric, r.fecha_edtf, r.creado_en)
                  for r in filas]
        for t, i in frontera:
            if t == "recurso_documental" and i in self.recursos:
                r = self.recursos[i]
                # La jerarquía desde el árbol (incluido_en), como la recorre el catálogo y
                # como la exporta RiC-O: una parte documental es constitutiva (R003), no incluida.
                if r.id != self.fondo.id and r.incluido_en_id in self.recursos:
                    salida.append((t, r.incluido_en_id, t, i, _jerarquia(r), None, r.creado_en))
                for h in self.hijos.get(i, []):
                    salida.append((t, i, t, h, _jerarquia(self.recursos[h]), None, self.recursos[h].creado_en))
                # La forma documental es un atributo (RiC-A17) que se dibuja como arista.
                forma = r.tipo_parte_id if r.nivel == "parte_documental" else r.forma_documental_id
                if forma:
                    salida.append((t, i, "entidad_vocabulario", forma, "forma_documental", None, r.creado_en))
            if t == "entidad_vocabulario":
                for rid in self.por_forma.get(i, []):
                    salida.append(("recurso_documental", rid, t, i, "forma_documental", None,
                                   self.recursos[rid].creado_en))
        return salida


def _jerarquia(hijo: RecursoDocumental) -> str:
    return "has_or_had_constituent" if hijo.nivel == "parte_documental" else "includes_or_included"


def _limites_fecha(f: Fecha) -> tuple[date | None, date | None]:
    inicio, fin = f.inicio, f.fin
    if inicio is None and fin is None and f.edtf:
        inicio, fin = _limites_edtf(f.edtf)
    if inicio is None and fin is None and f.normalizada:
        inicio = fin = f.normalizada
    return inicio, fin


def _pasa(n: dict, f: Filtros) -> bool:
    if f.familias and n["familia"] not in f.familias:
        return False
    if f.estados and n["tipo"] == "recurso_documental" and n["estado"] not in f.estados:
        return False
    return _se_cruza(n["fecha_inicio"], n["fecha_fin"], f)


def uri_rico(codigo: str) -> str | None:
    """La propiedad RiC-O del código, del mapeo único que usa la exportación."""
    if codigo == "forma_documental":
        return "rico:hasOrHadDocumentaryFormType"
    p = ric_o.propiedad(codigo)
    return f"rico:{p.rico}" if p is not None else URI_RICO.get(codigo)


def _arista(desde: str, hacia: str, codigo: str) -> dict:
    return {"desde": desde, "hacia": hacia, "codigo_ric": codigo,
            "uri_rico": uri_rico(codigo),
            "etiqueta": ETIQUETA_RELACION.get(codigo, codigo.replace("_", " ")), "dirigida": codigo not in SIMETRICAS}


def fondo_de(db: Session, tipo: str, ident: uuid.UUID) -> uuid.UUID | None:
    """El fondo de una entidad raíz (la fecha no tiene fondo propio)."""
    if tipo == "recurso_documental":
        r = db.get(RecursoDocumental, ident)
        return (r.fondo_id or r.id) if r else None
    if tipo == "entidad_vocabulario":
        e = db.get(EntidadVocabulario, ident)
        return e.fondo_id if e else None
    if tipo == "instanciacion":
        i = db.get(Instanciacion, ident)
        return i.fondo_id if i else None
    return None


def _recorrer(ctx: _Contexto, raiz_tipo: str, raiz_id: uuid.UUID, saltos: int, f: Filtros,
              max_nodos: int = MAX_NODOS):
    if raiz_tipo not in TIPOS_RAIZ:
        raise ErrorInstrumento("Tipo de entidad raíz desconocido.")
    inicial = ctx.nodo(raiz_tipo, raiz_id)
    if inicial is None:
        raise ErrorInstrumento("Esa entidad no existe en el fondo o no es visible.", 404)
    raiz = f"{raiz_tipo}:{raiz_id}"
    nodos = {raiz: {**inicial, "id": str(raiz_id), "clave": raiz, "salto": 0}}
    aristas: dict[tuple, dict] = {}
    descartados: set[str] = set()
    frontera, truncado = [(raiz_tipo, raiz_id)], False
    for salto in range(1, max(1, min(saltos, SALTOS_MAXIMOS)) + 1):
        candidatas = [c for c in ctx.vecinos(frontera)
                      if (not f.relaciones or c[4] in f.relaciones)
                      and (c[5] is None or _se_cruza(*_limites_edtf(c[5]), f))]
        ctx.precargar([(t, i) for c in candidatas for t, i in ((c[0], c[1]), (c[2], c[3]))])
        siguiente = []
        for ot, oi, dt, di, codigo, _, registrada in candidatas:
            claves = []
            for t, i in ((ot, oi), (dt, di)):
                clave = f"{t}:{i}"
                if clave in descartados:
                    break
                if clave not in nodos:
                    if len(nodos) >= max_nodos:
                        truncado = True
                        break
                    datos = ctx.nodo(t, i)
                    if datos is None or not _pasa(datos, f):
                        descartados.add(clave)
                        break
                    nodos[clave] = {**datos, "id": str(i), "clave": clave, "salto": salto}
                    siguiente.append((t, i))
                claves.append(clave)
            if len(claves) == 2 and claves[0] != claves[1]:
                previa = aristas.get((claves[0], claves[1], codigo))
                if previa is None or (registrada and registrada > previa["_registrada"]):
                    aristas[(claves[0], claves[1], codigo)] = {**_arista(claves[0], claves[1], codigo),
                                                               "_registrada": registrada}
        frontera = siguiente
        if not frontera:
            break
    return raiz, nodos, aristas, truncado


def subgrafo(db: Session, fondo: RecursoDocumental, raiz_tipo: str, raiz_id: uuid.UUID, saltos: int = 1,
             filtros: Filtros | None = None, ver_restringidos: bool = False, max_nodos: int = MAX_NODOS) -> dict:
    f = filtros or Filtros()
    ctx = _Contexto(db, fondo, ver_restringidos)
    raiz, nodos, aristas, truncado = _recorrer(ctx, raiz_tipo, raiz_id, saltos, f, max_nodos)
    conexiones = vocabulario.conexiones_de(
        db, [uuid.UUID(n["id"]) for n in nodos.values() if n["tipo"] == "entidad_vocabulario"])
    for n in nodos.values():
        if n["tipo"] == "entidad_vocabulario":
            n["documentos"] = conexiones.get(uuid.UUID(n["id"]), 0)
        for k in ("fecha_inicio", "fecha_fin"):
            n[k] = n[k].isoformat() if n[k] else None
    return sin_campos_internos({
        "fondo": {"id": str(fondo.id), "titulo": fondo.titulo}, "centro": raiz, "saltos": max(1, min(saltos, SALTOS_MAXIMOS)),
        "nodos": list(nodos.values()),
        "aristas": [{k: v for k, v in a.items() if not k.startswith("_")} for a in aristas.values()],
        "truncado": truncado, "maximo_nodos": max_nodos, "filtros_activos": f.activos()})


def opciones(db: Session, fondo: RecursoDocumental, ver_restringidos: bool) -> dict:
    """Lo que ofrece el panel de filtros y el selector de entidad raíz."""
    from app.models.enums import CODIGO_RELACION_RIC

    ctx = _Contexto(db, fondo, ver_restringidos)
    raices = [{"clave": f"recurso_documental:{r.id}", "etiqueta": r.titulo, "subtitulo": NIVEL_NOMBRE[r.nivel],
               "familia": _FAMILIA_NIVEL.get(r.nivel, "RecordSet")}
              for r in sorted(ctx.recursos.values(), key=lambda r: (r.id != fondo.id, NIVEL_ORDEN[r.nivel], r.titulo))]
    for e in db.scalars(select(EntidadVocabulario).where(
            EntidadVocabulario.fondo_id == fondo.id, EntidadVocabulario.estado == "activa",
            or_(EntidadVocabulario.subtipo.is_(None), EntidadVocabulario.subtipo != "mecanismo"))
            .order_by(EntidadVocabulario.nombre)):
        raices.append({"clave": f"entidad_vocabulario:{e.id}", "etiqueta": e.nombre,
                       "subtitulo": FAMILIAS[_FAMILIA_CLASE[e.clase]].split(" (")[0], "familia": _FAMILIA_CLASE[e.clase]})
    # Solo los tipos de relación que el fondo usa de verdad (no todo el catálogo).
    ids = list(ctx.recursos) + list(db.scalars(select(EntidadVocabulario.id).where(EntidadVocabulario.fondo_id == fondo.id)))
    usados = set(db.scalars(select(Relacion.codigo_ric).distinct().where(
        Relacion.estado == "vigente", or_(Relacion.origen_id.in_(ids), Relacion.destino_id.in_(ids)))))
    usados |= {_jerarquia(r) for r in ctx.recursos.values() if r.id != fondo.id}
    if ctx.por_forma:
        usados.add("forma_documental")
    codigos = [c for c in list(CODIGO_RELACION_RIC) + ["forma_documental"] if c in usados]
    return {"familias": [{"clave": k, "nombre": v} for k, v in FAMILIAS.items()],
            "relaciones": sorted(({"clave": c, "nombre": ETIQUETA_RELACION.get(c, c.replace("_", " ")),
                                   "uri_rico": uri_rico(c)} for c in codigos), key=lambda x: x["nombre"]),
            "estados": [{"clave": k, "nombre": v} for k, v in ESTADOS.items()],
            "raices": raices, "saltos_maximos": SALTOS_MAXIMOS, "maximo_nodos": MAX_NODOS}


NIVEL_ORDEN = {n: i for i, n in enumerate(NIVEL_NOMBRE)}


# --- Ficha de la entidad seleccionada --------------------------------------------------------------------

RELACIONES_VISIBLES = 15


def _campo(campo: str, valor, icono: str) -> dict | None:
    if valor in (None, "", []):
        return None
    if isinstance(valor, (date, datetime)):
        valor = valor.strftime("%d/%m/%Y")
    return {"campo": campo, "valor": str(valor), "icono": icono}


def _fichas(db: Session, ctx: _Contexto, tipo: str, ident: uuid.UUID) -> tuple[list, list]:
    if tipo == "recurso_documental":
        r = ctx.recursos[ident]
        forma_id = r.tipo_parte_id if r.nivel == "parte_documental" else r.forma_documental_id
        forma = db.get(EntidadVocabulario, forma_id) if forma_id else None
        n = ctx.nodo(tipo, ident)
        rango = " – ".join(x.strftime("%d/%m/%Y") for x in (n["fecha_inicio"], n["fecha_fin"]) if x) if n["fecha_inicio"] else None
        resumen = [_campo("Identificador", r.codigo_referencia, "identificador"), _campo("Título", r.titulo, "titulo"),
                   _campo("Nivel", NIVEL_NOMBRE[r.nivel], "nivel"),
                   _campo("Alcance y contenido", r.alcance_contenido, "texto"),
                   _campo("Fechas", r.fechas_extremas or rango, "fecha"),
                   _campo("Estado", ESTADOS[n["estado"]] if r.nivel != "fondo" else "Fondo registrado", "estado")]
        atributos = [_campo("Forma documental", forma.nombre if forma else None, "forma"),
                     _campo("Idiomas (ISO 639-3)", ", ".join(r.idiomas or []), "idioma"),
                     _campo("Condiciones de acceso", r.condiciones_acceso, "acceso"),
                     _campo("Condiciones de uso", r.condiciones_uso, "acceso"),
                     _campo("Caja", r.caja, "ubicacion"), _campo("Carpeta", r.carpeta, "ubicacion"),
                     _campo("Folios", r.folios, "extension"), _campo("Soporte", r.soporte, "extension"),
                     _campo("Publicada el", r.publicado_en, "fecha"), _campo("Actualizada el", r.actualizado_en, "fecha")]
    elif tipo == "entidad_vocabulario":
        e = ctx._entidades[ident]
        resumen = [_campo("Nombre", e.nombre, "titulo"),
                   _campo("Tipo", SUBTIPO_NOMBRE.get(e.subtipo or "", e.subtipo) or FAMILIAS[_FAMILIA_CLASE[e.clase]].split(" (")[0], "nivel"),
                   _campo("Existencia", fechas.legible(e.existencia_edtf), "fecha"),
                   _campo("Tipo de lugar", e.tipo_lugar, "ubicacion"),
                   _campo("Coordenadas", f"{e.latitud}, {e.longitud}" if e.latitud is not None else None, "ubicacion")]
        atributos = [_campo("Historia", e.historia, "texto"), _campo("Estatuto jurídico", e.estatuto_juridico, "acceso"),
                     _campo("Estructura interna", e.estructura, "texto"), _campo("Contexto general", e.contexto_general, "texto"),
                     _campo("Reglas o convenciones", e.reglas, "identificador"),
                     _campo("Nivel de detalle", e.nivel_detalle, "estado"), _campo("Fuentes", e.fuentes, "texto"),
                     _campo("Registrada el", e.creado_en, "fecha")]
    elif tipo == "fecha":
        f = ctx._fechas[ident]
        resumen = [_campo("Fecha", fechas.legible(f.edtf, f.expresion), "fecha"),
                   _campo("Como aparece en el documento", f.expresion, "texto"),
                   _campo("Forma normalizada (EDTF)", f.edtf, "identificador")]
        atributos = [_campo("Tipo de fecha", f.subtipo, "nivel"), _campo("Calendario", f.calendario, "fecha")]
    elif tipo == "instanciacion":
        i = ctx._instancias[ident]
        resumen = [_campo("Archivo", i.nombre_original, "titulo"),
                   _campo("Formato", f"{i.formato_nombre or ''} ({i.formato_puid})" if i.formato_puid else i.formato_nombre, "forma"),
                   _campo("Tamaño", f"{i.tamano_bytes:,} bytes".replace(",", "."), "extension"),
                   _campo("Páginas", i.paginas, "extension")]
        atributos = [_campo("Huella SHA-256", i.huella, "identificador"), _campo("Cargado el", i.cargado_en, "fecha")]
    else:
        a = ctx._actividades[ident]
        resumen, atributos = [_campo("Nombre", a.nombre, "titulo")], []
    return [x for x in resumen if x], [x for x in atributos if x]


def _relaciones_de(ctx: _Contexto, tipo: str, ident: uuid.UUID) -> list[dict]:
    """Todas las relaciones visibles de la entidad, las más recientes primero."""
    raiz, nodos, aristas, _ = _recorrer(ctx, tipo, ident, 1, Filtros(), max_nodos=10**6)
    filas = []
    for a in aristas.values():
        otro = a["hacia"] if a["desde"] == raiz else a["desde"]
        n = nodos[otro]
        filas.append({"codigo_ric": a["codigo_ric"], "etiqueta": a["etiqueta"], "uri_rico": a["uri_rico"],
                      "sentido": "sale" if a["desde"] == raiz else "entra",
                      "otro": {"clave": otro, "etiqueta": n["etiqueta"], "familia": n["familia"]},
                      "registrada": a["_registrada"]})
    filas.sort(key=lambda x: (x["registrada"] is None, -(x["registrada"].timestamp() if x["registrada"] else 0),
                              x["etiqueta"], x["otro"]["etiqueta"]))
    return filas


def ficha(db: Session, fondo: RecursoDocumental, tipo: str, ident: uuid.UUID, ver_restringidos: bool) -> dict:
    ctx = _Contexto(db, fondo, ver_restringidos)
    nodo = ctx.nodo(tipo, ident) if tipo in TIPOS_RAIZ else None
    if nodo is None:
        raise ErrorInstrumento("Esa entidad no existe en el fondo o no es visible.", 404)
    resumen, atributos = _fichas(db, ctx, tipo, ident)
    relaciones = _relaciones_de(ctx, tipo, ident)
    for r in relaciones:
        r["registrada"] = r["registrada"].isoformat() if r["registrada"] else None
    return sin_campos_internos({
        "clave": f"{tipo}:{ident}", "id": str(ident), "tipo": tipo, "clase": nodo["clase"], "familia": nodo["familia"],
        "familia_nombre": FAMILIAS[nodo["familia"]], "etiqueta": nodo["etiqueta"],
        "resumen": resumen, "atributos": atributos, "relaciones_total": len(relaciones),
        "relaciones": relaciones[:RELACIONES_VISIBLES]})


def hoja_relaciones(db: Session, fondo: RecursoDocumental, tipo: str, ident: uuid.UUID, ver_restringidos: bool) -> bytes:
    """La lista completa de relaciones de la entidad, en Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    ctx = _Contexto(db, fondo, ver_restringidos)
    nodo = ctx.nodo(tipo, ident) if tipo in TIPOS_RAIZ else None
    if nodo is None:
        raise ErrorInstrumento("Esa entidad no existe en el fondo o no es visible.", 404)
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Relaciones"
    hoja.append(["Entidad", nodo["etiqueta"], FAMILIAS[nodo["familia"]]])
    hoja.append([])
    hoja.append(["Relación", "Propiedad RiC-O", "Sentido", "Entidad del otro extremo", "Tipo de entidad",
                 "Registrada el", "Clave interna del otro extremo"])
    for c in hoja[3]:
        c.font = Font(bold=True)
    for r in _relaciones_de(ctx, tipo, ident):
        hoja.append([r["etiqueta"], r["uri_rico"], "de esta entidad hacia la otra" if r["sentido"] == "sale" else "de la otra hacia esta",
                     r["otro"]["etiqueta"], FAMILIAS[r["otro"]["familia"]],
                     r["registrada"].replace(tzinfo=None) if r["registrada"] else None, r["otro"]["clave"]])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# --- Exportación del fragmento visible -------------------------------------------------------------------


def exportar_fragmento(db: Session, fondo: RecursoDocumental, raiz_tipo: str, raiz_id: uuid.UUID, saltos: int,
                       filtros: Filtros, ver_restringidos: bool) -> tuple[Graph, dict]:
    """El subgrafo visible en RiC-O: se genera con el mismo servicio de la
    exportación del fondo y se recorta a las entidades y relaciones que el
    archivista tiene en pantalla, con sus nodos de apoyo (nombres, fechas
    propias, tipos de agrupación, idiomas)."""
    datos = subgrafo(db, fondo, raiz_tipo, raiz_id, saltos, filtros, ver_restringidos)
    ex = exportacion_rico.exportar(db, fondo, ver_restringidos)
    completo = ex.grafo
    visibles = {exportacion_rico.uri(n["id"]) for n in datos["nodos"]}
    # Las entidades del fondo (lo que tiene URI propia): nunca se arrastran
    # como apoyo; solo entran si están en pantalla.
    entidades = {exportacion_rico.uri(i) for i in ex.nodos}
    pares = {frozenset((exportacion_rico.uri(a["desde"].split(":", 1)[1]), exportacion_rico.uri(a["hacia"].split(":", 1)[1])))
             for a in datos["aristas"]}
    salida = Graph()
    for p, ns in completo.namespaces():
        salida.bind(p, ns)
    pendientes, vistos = list(visibles), set()
    while pendientes:
        s = pendientes.pop()
        if s in vistos:
            continue
        vistos.add(s)
        for _, p, o in completo.triples((s, None, None)):
            if isinstance(o, Literal) or (o in visibles and frozenset((s, o)) in pares and s in visibles):
                salida.add((s, p, o))
            elif isinstance(o, URIRef) and o not in entidades:
                salida.add((s, p, o))  # nodo de apoyo o vocabulario controlado
                pendientes.append(o)
    # Clase y etiqueta de lo citado como apoyo, para que el archivo se lea solo.
    for o in set(salida.objects()):
        if isinstance(o, URIRef) and o not in vistos:
            for p in (RDF.type, RDFS.label):
                for v in completo.objects(o, p):
                    salida.add((o, p, v))
    return salida, datos
