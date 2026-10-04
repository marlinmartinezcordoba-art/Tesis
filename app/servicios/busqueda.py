"""
Buscador unificado (brechas RF-SEARCH-001 y RF-SEARCH-002).

Una sola caja busca en cuatro lugares a la vez:

1. la descripción ISAD(G): título y código de referencia (peso alto),
   alcance y contenido, y el resto de los campos que escribe una persona;
2. el texto de cada archivo (OCR o capa de texto del PDF);
3. los identificadores: el código de referencia del documento y los de las
   autoridades (VIAF, Wikidata, ORCID, ROR…), completos o por partes;
4. el contexto: las autoridades (personas, instituciones, lugares, formas
   documentales…) por su nombre o sus otras formas, y los documentos que
   las citan.

El índice es de PostgreSQL (migración 0035), en español y sin tildes:
«medellin alcaldes» encuentra «Alcalde de Medellín».

**Reserva (Ley 1712, arts. 18 y 19).** Se busca solo dentro de lo que la
persona ya puede ver en el catálogo, con la misma regla de la exportación
RiC-O, el grafo y el índice: lo publicado y, para quien no es del equipo
de archivo, nada clasificado ni reservado, propio o heredado. El texto de
un archivo restringido no se consulta, así que no aparece ni en los
fragmentos ni en los conteos. Una autoridad que solo citan documentos
restringidos tampoco aparece (INS-02).

Quien describe (equipo de archivo) encuentra además los borradores y los
archivos todavía sin describir, marcados como tales.
"""

import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import bindparam, func, or_, select, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, IdentificadorEntidad, Relacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental

LARGO_MAXIMO = 200
POR_PAGINA = 20
ALCANCES = ("todo", "descripcion", "texto", "autoridades")
# Marcas del fragmento resaltado: caracteres que no aparecen en un documento
# de archivo. La interfaz los convierte en resaltado sin interpretar HTML.
ABRE, CIERRA = "⟦", "⟧"
OPCIONES_FRAGMENTO = (f"StartSel={ABRE}, StopSel={CIERRA}, MaxWords=30, MinWords=12, "
                      "MaxFragments=2, FragmentDelimiter=\" … \"")
# Cuánto texto del OCR se recorre para armar el fragmento (no para buscar).
LARGO_FRAGMENTO = 300_000
# Parecido de la palabra buscada con alguna palabra del nombre (pg_trgm):
# «alcaldias» encuentra «Alcaldía Municipal» y tolera una letra cambiada.
SIMILITUD_NOMBRE = 0.6

CAMPOS_FRAGMENTO = ("alcance_contenido", "historia_archivistica", "nota", "organizacion", "valoracion",
                    "localizacion_originales", "unidades_relacionadas")


class ErrorBusqueda(Exception):
    pass


@dataclass
class _Doc:
    recurso: RecursoDocumental
    fondo: RecursoDocumental
    borrador: bool
    puntaje: float = 0.0
    motivos: list[str] = field(default_factory=list)
    texto_de: uuid.UUID | None = None  # instanciación cuyo texto coincidió
    en_descripcion: bool = False

    def motivo(self, m: str, puntos: float) -> None:
        self.puntaje += puntos
        if m not in self.motivos:
            self.motivos.append(m)


@dataclass
class _Fondo:
    fondo: RecursoDocumental
    arbol: object
    visibles: dict[uuid.UUID, RecursoDocumental]
    borradores: set[uuid.UUID]


def _ids(nombre: str):
    return bindparam(nombre, type_=ARRAY(PG_UUID(as_uuid=True)))


def _alcance_del_fondo(db: Session, fondo: RecursoDocumental, ver_restringidos: bool) -> _Fondo:
    from app.servicios import instrumentos

    arbol = instrumentos.arbol(db, fondo, ver_restringidos)
    visibles = dict(arbol.nodos)
    borradores: set[uuid.UUID] = set()
    if ver_restringidos:
        # El equipo de archivo encuentra también lo que aún no se publica.
        for r in db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo.id)):
            if r.id not in visibles:
                visibles[r.id] = r
                borradores.add(r.id)
    return _Fondo(fondo, arbol, visibles, borradores)


def _por_descripcion(db: Session, q: str, f: _Fondo) -> list[tuple[uuid.UUID, float]]:
    filas = db.execute(text("""
        SELECT r.id, ts_rank_cd(r.busqueda, c) AS rango
        FROM recursos_documentales r, websearch_to_tsquery('public.ricora_es', :q) c
        WHERE r.id = ANY(:ids) AND r.busqueda @@ c
        ORDER BY rango DESC LIMIT 500""").bindparams(_ids("ids")), {"q": q, "ids": list(f.visibles)}).all()
    return [(i, float(rango)) for i, rango in filas]


def _por_codigo(db: Session, q: str, f: _Fondo) -> list[tuple[uuid.UUID, bool]]:
    buscado = q.strip().lower()
    filas = db.execute(select(RecursoDocumental.id, func.lower(RecursoDocumental.codigo_referencia)).where(
        RecursoDocumental.id.in_(list(f.visibles)), RecursoDocumental.codigo_referencia.is_not(None),
        or_(func.lower(RecursoDocumental.codigo_referencia) == buscado,
            func.lower(RecursoDocumental.codigo_referencia).contains(buscado, autoescape=True)
            if len(buscado) >= 3 else False))).all()
    return [(i, codigo == buscado) for i, codigo in filas]


def _por_texto(db: Session, q: str, f: _Fondo, ver_restringidos: bool):
    """Archivos cuyo texto coincide, ya filtrados por la reserva: devuelve
    (recurso visible, instanciación, rango) y, para el equipo de archivo, los
    archivos que nadie ha descrito todavía."""
    from app.servicios import derechos

    filas = db.execute(text("""
        SELECT i.id, ts_rank_cd(i.busqueda, c) AS rango
        FROM instanciaciones i, websearch_to_tsquery('public.ricora_es', :q) c
        WHERE i.fondo_id = :fondo AND i.busqueda @@ c AND i.estado <> 'error'
        ORDER BY rango DESC LIMIT 300"""), {"q": q, "fondo": f.fondo.id}).all()
    hallados, sin_describir = [], []
    for inst_id, rango in filas:
        inst = db.get(Instanciacion, inst_id)
        if not ver_restringidos and derechos.instanciacion_restringida(db, inst):
            continue  # el texto de un archivo reservado no se consulta
        recursos = [r for r in derechos.recursos_de(db, inst) if r.id in f.visibles]
        if recursos:
            hallados.extend((r, inst, float(rango)) for r in recursos)
        elif ver_restringidos and not derechos.recursos_de(db, inst):
            sin_describir.append((inst, float(rango)))
    return hallados, sin_describir


def _por_autoridad(db: Session, q: str, f: _Fondo, ver_restringidos: bool):
    """Autoridades del fondo por nombre, otra forma del nombre o
    identificador, con los documentos visibles que las citan."""
    from app.servicios import exportacion_rico, vocabulario

    buscado = vocabulario.normalizar(q)
    crudo = q.strip().lower()
    formas = vocabulario._formas()
    por_nombre = db.execute(
        select(formas.c.entidad_id, formas.c.forma, func.word_similarity(buscado, formas.c.n))
        .join(EntidadVocabulario, EntidadVocabulario.id == formas.c.entidad_id)
        .where(EntidadVocabulario.fondo_id == f.fondo.id, EntidadVocabulario.estado == "activa",
               or_(EntidadVocabulario.subtipo.is_(None), EntidadVocabulario.subtipo != "mecanismo"),
               or_(formas.c.n.contains(buscado, autoescape=True),
                   func.word_similarity(buscado, formas.c.n) >= SIMILITUD_NOMBRE))
    ).all()
    condicion_id = func.lower(IdentificadorEntidad.valor) == crudo
    if len(crudo) >= 4:
        # Un identificador escrito a medias o pegado como enlace
        # (https://viaf.org/viaf/12345) también lo encuentra.
        condicion_id = or_(condicion_id, func.lower(IdentificadorEntidad.valor).contains(crudo, autoescape=True),
                           func.strpos(crudo, func.lower(IdentificadorEntidad.valor)) > 0)
    por_identificador = db.execute(
        select(IdentificadorEntidad.entidad_id, IdentificadorEntidad.esquema, IdentificadorEntidad.valor)
        .join(EntidadVocabulario, EntidadVocabulario.id == IdentificadorEntidad.entidad_id)
        .where(EntidadVocabulario.fondo_id == f.fondo.id, EntidadVocabulario.estado == "activa",
               IdentificadorEntidad.estado == "vigente", func.length(IdentificadorEntidad.valor) >= 4,
               condicion_id)).all()

    encontradas: dict[uuid.UUID, dict] = {}
    for entidad_id, forma, similitud in por_nombre:
        e = encontradas.setdefault(entidad_id, {"puntos": 0.0, "motivo": None})
        puntos = 1.0 + float(similitud)
        if puntos > e["puntos"]:
            e["puntos"], e["motivo"] = puntos, (f"otra forma del nombre: {forma}" if forma else "nombre")
    for entidad_id, esquema, valor in por_identificador:
        exacto = valor.lower() == crudo or valor.lower() in crudo
        e = encontradas.setdefault(entidad_id, {"puntos": 0.0, "motivo": None})
        puntos = 5.0 if exacto else 2.0
        if puntos > e["puntos"]:
            e["puntos"], e["motivo"] = puntos, f"identificador {esquema.upper()}: {valor}"
    if not encontradas:
        return []
    vedadas = set() if ver_restringidos else exportacion_rico._entidades_vedadas(db, f.fondo, f.arbol.nodos)
    docs = vocabulario._documentos_por_entidad(db, list(encontradas))
    salida = []
    for entidad_id, datos in encontradas.items():
        if entidad_id in vedadas:
            continue  # solo la conocen documentos restringidos o sin publicar
        entidad = db.get(EntidadVocabulario, entidad_id)
        visibles = [f.visibles[d] for d in docs.get(entidad_id, ()) if d in f.visibles and d != f.fondo.id]
        salida.append((entidad, datos["puntos"], datos["motivo"], visibles))
    return salida


def _fragmentos(db: Session, q: str, docs: list[_Doc]) -> dict[uuid.UUID, str]:
    """Fragmentos resaltados solo de la página que se muestra: armar uno
    recorre el texto, y un OCR puede tener cientos de páginas."""
    salida: dict[uuid.UUID, str] = {}
    de_texto = {d.texto_de: d.recurso.id for d in docs if d.texto_de and not d.en_descripcion}
    if de_texto:
        for inst_id, frag in db.execute(text(f"""
                SELECT i.id, ts_headline('public.ricora_es', left(i.texto_extraido, {LARGO_FRAGMENTO}), c, :op)
                FROM instanciaciones i, websearch_to_tsquery('public.ricora_es', :q) c
                WHERE i.id = ANY(:ids)""").bindparams(_ids("ids")),
                {"q": q, "op": OPCIONES_FRAGMENTO, "ids": list(de_texto)}):
            if ABRE in (frag or ""):
                salida[de_texto[inst_id]] = frag
    de_descripcion = [d.recurso.id for d in docs if d.en_descripcion]
    if de_descripcion:
        campos = " || ' ' || ".join(f"coalesce(r.{c}, '')" for c in CAMPOS_FRAGMENTO)
        for rid, frag in db.execute(text(f"""
                SELECT r.id, ts_headline('public.ricora_es', {campos}, c, :op)
                FROM recursos_documentales r, websearch_to_tsquery('public.ricora_es', :q) c
                WHERE r.id = ANY(:ids)""").bindparams(_ids("ids")),
                {"q": q, "op": OPCIONES_FRAGMENTO, "ids": de_descripcion}):
            if ABRE in (frag or ""):
                salida[rid] = frag
    return salida


def _anios(f: _Fondo, r: RecursoDocumental) -> tuple[int, int] | None:
    fechas = f.arbol.fechas.get(r.id)
    return (fechas[0].year, fechas[1].year) if fechas else None


def buscar(db: Session, q: str, *, ver_restringidos: bool, fondo_id: uuid.UUID | None = None,
           alcance: str = "todo", nivel: str | None = None, desde: int | None = None, hasta: int | None = None,
           agente_id: uuid.UUID | None = None, pagina: int = 1, por_pagina: int = POR_PAGINA) -> dict:
    from app.servicios import instrumentos

    q = (q or "").strip()
    if len(q) < 2:
        raise ErrorBusqueda("Escriba al menos dos caracteres.")
    if len(q) > LARGO_MAXIMO:
        raise ErrorBusqueda(f"La búsqueda admite hasta {LARGO_MAXIMO} caracteres.")
    if alcance not in ALCANCES:
        raise ErrorBusqueda("Alcance no válido.")

    consulta_fondos = select(RecursoDocumental).where(RecursoDocumental.nivel == "fondo")
    if fondo_id:
        consulta_fondos = consulta_fondos.where(RecursoDocumental.id == fondo_id)
    fondos = [_alcance_del_fondo(db, fondo, ver_restringidos)
              for fondo in db.scalars(consulta_fondos.order_by(RecursoDocumental.titulo))]
    if fondo_id and not fondos:
        raise ErrorBusqueda("El fondo no existe.")

    documentos: dict[uuid.UUID, _Doc] = {}
    por_fondo: dict[uuid.UUID, _Fondo] = {}
    autoridades, archivos = [], []

    def doc(f: _Fondo, recurso: RecursoDocumental) -> _Doc:
        por_fondo[recurso.id] = f
        return documentos.setdefault(recurso.id, _Doc(recurso, f.fondo, recurso.id in f.borradores))

    for f in fondos:
        if alcance in ("todo", "descripcion"):
            for rid, rango in _por_descripcion(db, q, f):
                d = doc(f, f.visibles[rid])
                d.en_descripcion = True
                d.motivo("descripción", 1.0 + 4 * rango)
            for rid, exacto in _por_codigo(db, q, f):
                doc(f, f.visibles[rid]).motivo("código de referencia", 10.0 if exacto else 3.0)
        if alcance in ("todo", "texto"):
            hallados, sin_describir = _por_texto(db, q, f, ver_restringidos)
            for recurso, inst, rango in hallados:
                d = doc(f, recurso)
                d.texto_de = d.texto_de or inst.id
                d.motivo("texto del documento", 0.8 + 4 * rango)
            archivos += [{"id": str(inst.id), "nombre": inst.nombre_original, "fondo_id": str(f.fondo.id),
                          "fondo": f.fondo.titulo, "_rango": rango} for inst, rango in sin_describir]
        if alcance in ("todo", "autoridades"):
            for entidad, puntos, motivo, citan in _por_autoridad(db, q, f, ver_restringidos):
                autoridades.append({
                    "id": str(entidad.id), "nombre": entidad.nombre, "clase": entidad.clase, "subtipo": entidad.subtipo,
                    "fondo_id": str(f.fondo.id), "motivo": motivo, "documentos": len(citan), "_puntos": puntos,
                    "ejemplos": [{"id": str(r.id), "titulo": r.titulo, "nivel": r.nivel} for r in citan[:5]]})
                # Contexto: los documentos que citan la autoridad hallada.
                for r in citan:
                    doc(f, r).motivo(f"cita {entidad.nombre}", 0.5 if puntos < 5 else 4.0)

    # Filtro por fechas (años de creación, propagados en el árbol).
    if desde or hasta:
        def en_rango(d: _Doc) -> bool:
            anios = _anios(por_fondo[d.recurso.id], d.recurso)
            return bool(anios) and (not desde or anios[1] >= desde) and (not hasta or anios[0] <= hasta)
        documentos = {i: d for i, d in documentos.items() if en_rango(d)}

    if agente_id:
        citan = documentos_de_agente(db, agente_id)
        documentos = {i: d for i, d in documentos.items() if i in citan}

    # Facetas sobre lo que el usuario puede ver (antes del filtro de nivel,
    # para poder cambiarlo): nunca cuentan nada restringido.
    niveles = Counter(d.recurso.nivel for d in documentos.values())
    fondos_faceta = Counter(d.fondo.id for d in documentos.values())
    agentes = _agentes(db, documentos, fondos, ver_restringidos)
    if nivel:
        documentos = {i: d for i, d in documentos.items() if d.recurso.nivel == nivel}

    ordenados = sorted(documentos.values(), key=lambda d: (-d.puntaje, d.recurso.titulo.lower()))
    total = len(ordenados)
    pagina = max(pagina, 1)
    vista = ordenados[(pagina - 1) * por_pagina: pagina * por_pagina]
    fragmentos = _fragmentos(db, q, vista)
    anios_todos = [a for d in documentos.values() if (a := _anios(por_fondo[d.recurso.id], d.recurso))]

    def salida_doc(d: _Doc) -> dict:
        f = por_fondo[d.recurso.id]
        migas = f.arbol.ancestros(d.recurso.id) if d.recurso.id in f.arbol.nodos else []
        return {
            "id": str(d.recurso.id), "titulo": d.recurso.titulo, "nivel": d.recurso.nivel,
            "codigo_referencia": d.recurso.codigo_referencia,
            "fechas": instrumentos._fechas_texto(f.arbol, d.recurso) if d.recurso.id in f.arbol.nodos else d.recurso.fechas_extremas,
            "fondo": {"id": str(d.fondo.id), "titulo": d.fondo.titulo},
            "ruta": [x.titulo for x in migas if x.id != d.fondo.id][-3:],
            "motivos": d.motivos, "fragmento": fragmentos.get(d.recurso.id),
            "borrador": d.borrador, "puntaje": round(d.puntaje, 3),
        }

    autoridades.sort(key=lambda a: (-a["_puntos"], a["nombre"].lower()))
    archivos.sort(key=lambda a: -a["_rango"])
    return {
        "q": q, "total": total, "pagina": pagina, "por_pagina": por_pagina,
        "documentos": [salida_doc(d) for d in vista],
        "autoridades": [{k: v for k, v in a.items() if not k.startswith("_")} for a in autoridades[:20]],
        "archivos_sin_describir": [{k: v for k, v in a.items() if not k.startswith("_")} for a in archivos[:20]],
        "facetas": {
            "niveles": dict(niveles),
            "fondos": [{"id": str(i), "titulo": next(f.fondo.titulo for f in fondos if f.fondo.id == i), "total": n}
                       for i, n in fondos_faceta.most_common()],
            "agentes": agentes,
            "anios": [min(a[0] for a in anios_todos), max(a[1] for a in anios_todos)] if anios_todos else None,
        },
        "alcance_reserva": "completo" if ver_restringidos else "publico",
    }


def _agentes(db: Session, documentos: dict[uuid.UUID, _Doc], fondos: list[_Fondo], ver_restringidos: bool) -> list[dict]:
    """Los agentes que más citan los resultados (productores, autores,
    destinatarios…), para afinar. Sin los que solo conocen documentos
    restringidos."""
    from app.servicios import exportacion_rico

    if not documentos:
        return []
    cuenta: Counter = Counter()
    for entidad_id, recurso_id in db.execute(
            select(Relacion.destino_id, Relacion.origen_id)
            .join(EntidadVocabulario, EntidadVocabulario.id == Relacion.destino_id)
            .where(Relacion.origen_id.in_(list(documentos)), Relacion.origen_tipo == "recurso_documental",
                   Relacion.estado == "vigente", EntidadVocabulario.clase == "agente",
                   EntidadVocabulario.estado == "activa")):
        cuenta[entidad_id] += 1
    if not cuenta:
        return []
    vedadas: set = set()
    if not ver_restringidos:
        for f in fondos:
            vedadas |= exportacion_rico._entidades_vedadas(db, f.fondo, f.arbol.nodos)
    nombres = dict(db.execute(select(EntidadVocabulario.id, EntidadVocabulario.nombre)
                              .where(EntidadVocabulario.id.in_(list(cuenta)))).all())
    return [{"id": str(i), "nombre": nombres[i], "documentos": n}
            for i, n in cuenta.most_common() if i not in vedadas][:8]


def documentos_de_agente(db: Session, agente_id: uuid.UUID) -> set[uuid.UUID]:
    return {o for (o,) in db.execute(select(Relacion.origen_id).where(
        Relacion.destino_id == agente_id, Relacion.origen_tipo == "recurso_documental", Relacion.estado == "vigente"))}

