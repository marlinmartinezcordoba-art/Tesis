"""
Validación semántica y calidad del fondo.

Una sola revisión reúne lo que puede estar mal en el conocimiento RiC del
fondo. Cada hallazgo dice qué descripción o entidad afecta, cuál es el
problema, qué regla incumple y qué acción lo corrige, con el enlace a la
pantalla donde se hace. Solo lee: no cambia nada.

Revisiones:
- entidades duplicadas (sugerencias de fusión pendientes);
- identificadores repetidos (el mismo código de referencia en dos recursos);
- fechas contradictorias (un recurso fuera de las fechas del conjunto que lo incluye);
- entidades incompletas (un recurso publicado sin identificador o sin alcance);
- relaciones sin evidencia (propuestas por el motor sin fragmento que las respalde);
- relaciones incompatibles y propiedades no permitidas (dominio, rango y
  vocabulario frente al OWL de RiC-O 1.1);
- errores de validación SHACL del perfil de RICORA;
- inconsistencias entre instrumentos (el último cotejo del CCD con la TRD vigente).
"""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Relacion, SugerenciaFusion
from app.models.recurso_documental import RecursoDocumental
from app.models.trd import VersionTrd

TIPOS = {
    "duplicado": "Entidades duplicadas",
    "identificador": "Identificadores repetidos",
    "fechas": "Fechas contradictorias",
    "incompleta": "Entidades incompletas",
    "sin_evidencia": "Relaciones sin evidencia",
    "owl": "Relaciones incompatibles o propiedades no permitidas",
    "shacl": "Errores de validación SHACL",
    "instrumentos": "Inconsistencias entre instrumentos",
}
GRAVEDAD = {"shacl": "error", "owl": "error", "identificador": "error", "fechas": "error", "instrumentos": "error",
            "duplicado": "aviso", "incompleta": "aviso", "sin_evidencia": "aviso"}
MAXIMO = 200  # hallazgos que se listan por tipo; el resto se cuenta


def _recurso(r: RecursoDocumental) -> dict:
    return {"tipo": "recurso_documental", "id": str(r.id), "titulo": r.titulo, "nivel": r.nivel,
            "enlace": f"/descripcion/registro/{r.id}"}


def _entidad(e: EntidadVocabulario) -> dict:
    return {"tipo": "entidad_vocabulario", "id": str(e.id), "titulo": e.nombre, "nivel": e.clase,
            "enlace": f"/vocabularios/{e.id}"}


def _intervalo(edtf: str | None):
    from app.servicios import fechas

    if not edtf:
        return None
    try:
        i = fechas.interpretar(edtf)
    except fechas.FechaInvalida:
        return None
    return (i.inicio, i.fin) if i.inicio and i.fin else None


def revisar(db: Session, fondo: RecursoDocumental, *, con_grafo: bool = False) -> dict:
    hallazgos: list[dict] = []

    def poner(tipo: str, afectado: dict | None, problema: str, regla: str, accion: str, enlace: str | None = None):
        hallazgos.append({"tipo": tipo, "gravedad": GRAVEDAD[tipo], "afectado": afectado, "problema": problema,
                          "regla": regla, "accion": accion, "enlace": enlace or (afectado or {}).get("enlace")})

    f = fondo.id
    recursos = {r.id: r for r in db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == f))}
    publicados = [r for r in recursos.values() if r.publicado_en is not None and r.nivel != "fondo"]

    # Entidades duplicadas.
    for s in db.scalars(select(SugerenciaFusion).where(SugerenciaFusion.fondo_id == f,
                                                       SugerenciaFusion.estado == "pendiente").limit(MAXIMO)):
        a, b = db.get(EntidadVocabulario, s.entidad_a_id), db.get(EntidadVocabulario, s.entidad_b_id)
        if a is None or b is None:
            continue
        poner("duplicado", _entidad(a), f"«{a.nombre}» y «{b.nombre}» parecen la misma entidad.",
              "Una entidad RiC se registra una sola vez y se reutiliza en todas las descripciones.",
              "Revise la sugerencia: fusione las dos o márquelas como distintas.", "/vocabularios?vista=sugerencias")

    # Identificadores repetidos.
    cuenta = Counter((r.codigo_referencia or "").strip() for r in publicados if (r.codigo_referencia or "").strip())
    for codigo, n in cuenta.items():
        if n > 1:
            for r in (x for x in publicados if (x.codigo_referencia or "").strip() == codigo):
                poner("identificador", _recurso(r), f"El identificador «{codigo}» lo tienen {n} recursos.",
                      "Cada recurso tiene un identificador único (rico:identifier).",
                      "Corrija el código de referencia en los datos de control de la descripción.")

    # Fechas contradictorias: un recurso fuera de las fechas del conjunto que lo incluye (un intervalo
    # invertido no llega aquí: la captura lo rechaza).
    for r in publicados:
        propio = _intervalo(r.fechas_extremas_edtf)
        padre = recursos.get(r.incluido_en_id) if r.incluido_en_id else None
        del_padre = _intervalo(padre.fechas_extremas_edtf) if padre is not None else None
        if propio and del_padre and (propio[0] < del_padre[0] or propio[1] > del_padre[1]):
            poner("fechas", _recurso(r), f"Sus fechas ({r.fechas_extremas_edtf}) quedan fuera de las de «{padre.titulo}» "
                  f"({padre.fechas_extremas_edtf}).",
                  "Las fechas de un recurso están dentro de las del conjunto que lo incluye (rico:isWithin, R085).",
                  "Corrija las fechas del recurso o amplíe las del conjunto.")

    # Entidades incompletas.
    for r in publicados:
        faltan = [n for n, v in (("identificador", r.codigo_referencia), ("alcance y contenido", r.alcance_contenido))
                  if not (v or "").strip()]
        if faltan:
            poner("incompleta", _recurso(r), "Le falta " + " y ".join(faltan) + ".",
                  "Un recurso documental RiC se identifica (rico:identifier) y dice su contenido (rico:scopeAndContent).",
                  "Complete la descripción.")

    # Documentos y expedientes sin serie del cuadro (cuando el fondo tiene TRD): sin regla de retención.
    from app.servicios import componentes_ric, descripcion

    if descripcion.tiene_cuadro(db, f):
        for r in publicados:
            if r.nivel in ("expediente", "unidad_documental") and not componentes_ric._en_serie(db, r):
                poner("incompleta", _recurso(r), "No está ubicado en una serie o subserie del cuadro.",
                      "Cada recurso se rige por la regla de retención de su serie (Acuerdo AGN 004 de 2019).",
                      "Ubíquelo en su serie o subserie desde «Queda incluido en».")

    # Relaciones del motor sin evidencia.
    ids = list(recursos)
    sin = db.scalars(select(Relacion).where(
        Relacion.estado == "vigente", Relacion.origen.in_(("motor", "motor_editado")),
        (Relacion.fragmento.is_(None)) | (Relacion.fragmento == ""),
        Relacion.origen_id.in_(ids) | Relacion.destino_id.in_(ids)).limit(MAXIMO)).all()
    for rel in sin:
        r = recursos.get(rel.origen_id) or recursos.get(rel.destino_id)
        poner("sin_evidencia", _recurso(r) if r else None,
              f"La relación {rel.codigo_ric.replace('_', ' ')} la propuso el motor sin el fragmento que la respalda.",
              "Toda relación propuesta por la IA cita su evidencia (rico:relationSource).",
              "Revise la relación: agregue la evidencia o anúlela.")

    # Grafo: OWL (dominio, rango, vocabulario) y SHACL.
    if con_grafo:
        from app.servicios import conformidad_rico, grafo_rdf

        ex = grafo_rdf.leer(db, fondo, incluir_restringidos=True)
        for problema in conformidad_rico.verificar_owl(ex.grafo)[:MAXIMO]:
            poner("owl", None, problema, "Solo clases y propiedades de RiC-O 1.1 (o SKOS, RDF, RDFS, OWL), con su dominio "
                  "y rango.", "Corrija la relación en la descripción; si viene de una importación, revise el archivo.",
                  "/instrumentos?vista=rico")
        shacl = conformidad_rico.validar_shacl(ex.grafo)
        for x in shacl["resultados"][:MAXIMO]:
            afectado = None
            foco = x.get("foco") or ""
            for rid, r in recursos.items():
                if foco.endswith(str(rid)):
                    afectado = _recurso(r)
                    break
            poner("shacl", afectado, x.get("mensaje") or "No cumple el perfil.",
                  f"Perfil SHACL de RICORA ({x.get('forma') or 'forma'}{' · ' + x['ruta'] if x.get('ruta') else ''}).",
                  "Complete o corrija el dato que pide la regla.", None if afectado else "/instrumentos?vista=rico")

    # Instrumentos: el último cotejo del CCD con la TRD vigente.
    from app.servicios import cotejo_ccd

    vigente = db.scalar(select(VersionTrd).where(VersionTrd.fondo_id == f, VersionTrd.instrumento == "trd",
                                                 VersionTrd.estado == "vigente"))
    informe = cotejo_ccd.ultimo(db, vigente) if vigente else None
    if informe:
        for s in informe.get("sin_retencion", [])[:MAXIMO]:
            poner("instrumentos", None, f"La serie {s.get('codigo')} {s.get('nombre', '')} está en el CCD y no en la TRD vigente.",
                  "Toda serie del cuadro tiene su regla de retención (Acuerdo AGN 004 de 2019).",
                  "Agregue la serie a la TRD o corrija el CCD.", "/fondos?vista=versiones")
        for s in informe.get("solo_en_trd", [])[:MAXIMO]:
            poner("instrumentos", None, f"La serie {s.get('codigo')} {s.get('nombre', '')} está en la TRD y no en el CCD.",
                  "El CCD y la TRD describen las mismas series.", "Agregue la serie al CCD o retírela de la TRD.",
                  "/fondos?vista=versiones")
        for s in informe.get("nombre_distinto", [])[:MAXIMO]:
            poner("instrumentos", None, f"La serie {s.get('codigo')} se llama distinto en el CCD y en la TRD.",
                  "Una serie tiene una sola denominación en los instrumentos vigentes.",
                  "Unifique la denominación con el banco terminológico.", "/fondos?vista=versiones")

    por_tipo = Counter(h["tipo"] for h in hallazgos)
    return {"fondo": {"id": str(f), "titulo": fondo.titulo},
            "resumen": [{"tipo": t, "nombre": n, "gravedad": GRAVEDAD[t], "total": por_tipo.get(t, 0)} for t, n in TIPOS.items()],
            "errores": sum(1 for h in hallazgos if h["gravedad"] == "error"),
            "avisos": sum(1 for h in hallazgos if h["gravedad"] == "aviso"),
            "hallazgos": hallazgos,
            "descripciones_revisadas": len(publicados),
            "relaciones_revisadas": db.scalar(select(func.count()).select_from(Relacion).where(
                Relacion.estado == "vigente", Relacion.origen_id.in_(ids) | Relacion.destino_id.in_(ids))) or 0}
