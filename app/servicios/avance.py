"""
Avance del fondo por el recorrido archivístico, para la página de Inicio.

Cada paso dice en qué estado está («hecho», «en curso», «pendiente»), cuánto
lleva y cuál es la siguiente acción recomendada, con el enlace a la pantalla
donde se hace. Solo cuenta: no cambia nada. Los pasos siguen el orden del
proceso (Ley 594 de 2000 y el PGD): instrumentos, carga, descripción,
autoridades, consulta e instrumentos de descripción, preservación.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.descripcion import SugerenciaFusion
from app.models.instanciacion import Instanciacion
from app.models.instrumento_aprobado import InstrumentoAprobado
from app.models.recurso_documental import RecursoDocumental
from app.models.trd import VersionTrd
from app.db.consultas import contar


def _contar(db: Session, consulta) -> int:
    return contar(db, consulta)


def avance(db: Session, fondo: RecursoDocumental) -> dict:
    from app.servicios import descripcion

    f = fondo.id
    vigente = db.scalar(select(VersionTrd).where(VersionTrd.fondo_id == f, VersionTrd.instrumento == "trd",
                                                 VersionTrd.estado == "vigente"))
    borrador = db.scalar(select(VersionTrd).where(VersionTrd.fondo_id == f, VersionTrd.instrumento == "trd",
                                                  VersionTrd.estado == "borrador"))
    series = _contar(db, select(RecursoDocumental.id).where(
        RecursoDocumental.fondo_id == f, RecursoDocumental.nivel.in_(("serie", "subserie"))))
    archivos = _contar(db, select(Instanciacion.id).where(
        Instanciacion.fondo_id == f, Instanciacion.estado != "registro_fisico"))
    en_cola = _contar(db, select(Instanciacion.id).where(
        Instanciacion.fondo_id == f, Instanciacion.estado.in_(("procesando", "duplicado_pendiente", "error"))))
    errores = _contar(db, select(Instanciacion.id).where(Instanciacion.fondo_id == f, Instanciacion.estado == "error"))
    por_describir = len(descripcion.cola(db, f))
    publicadas = _contar(db, select(RecursoDocumental.id).where(
        RecursoDocumental.fondo_id == f, RecursoDocumental.nivel.in_(("unidad_documental", "expediente")),
        RecursoDocumental.publicado_en.is_not(None)))
    duplicados = _contar(db, select(SugerenciaFusion.id).where(
        SugerenciaFusion.fondo_id == f, SugerenciaFusion.estado == "pendiente"))
    aprobados = dict(db.execute(select(InstrumentoAprobado.tipo, func.count()).where(
        InstrumentoAprobado.fondo_id == f, InstrumentoAprobado.estado == "vigente")
        .group_by(InstrumentoAprobado.tipo)).all())
    alterados = _contar(db, select(Instanciacion.id).where(
        Instanciacion.fondo_id == f, Instanciacion.estado_integridad.in_(("alterada", "ausente"))))
    sin_verificar = _contar(db, select(Instanciacion.id).where(
        Instanciacion.fondo_id == f, Instanciacion.estado == "listo_para_descripcion",
        Instanciacion.estado_integridad == "sin_verificar"))

    pasos = []

    def paso(clave, titulo, estado, resumen, accion=None, ruta=None, modulo="catalogo"):
        pasos.append({"clave": clave, "titulo": titulo, "estado": estado, "resumen": resumen,
                      "accion": accion, "ruta": ruta, "modulo": modulo})

    if vigente:
        paso("instrumentos", "Instrumentos archivísticos", "hecho",
             f"{vigente.nombre} vigente · {series} serie(s) y subserie(s) en el cuadro.",
             "Ver el cuadro", "/fondos?vista=versiones")
    elif borrador:
        paso("instrumentos", "Instrumentos archivísticos", "en_curso",
             f"{borrador.nombre} en borrador: falta aplicarla para que rija.",
             "Aplicar la TRD", "/fondos?vista=versiones")
    else:
        paso("instrumentos", "Instrumentos archivísticos", "pendiente",
             "Sin TRD. Todo empieza por cargar el CCD y la TRD.", "Cargar el CCD y la TRD", "/fondos?vista=cargar")

    if errores:
        paso("carga", "Carga de documentos", "en_curso", f"{errores} archivo(s) con error en la carga.",
             "Revisar lo cargado", "/ingesta?vista=cola", "ingesta")
    elif en_cola:
        paso("carga", "Carga de documentos", "en_curso", f"{en_cola} archivo(s) procesándose o por confirmar.",
             "Revisar lo cargado", "/ingesta?vista=cola", "ingesta")
    elif archivos:
        paso("carga", "Carga de documentos", "hecho", f"{archivos} archivo(s) cargados.",
             "Cargar más", "/ingesta", "ingesta")
    else:
        paso("carga", "Carga de documentos", "pendiente", "Todavía no hay archivos.",
             "Cargar documentos", "/ingesta", "ingesta")

    if por_describir:
        paso("descripcion", "Descripción", "en_curso",
             f"{por_describir} documento(s) por describir · {publicadas} descrito(s).",
             "Describir el siguiente", "/descripcion", "descripcion")
    elif publicadas:
        paso("descripcion", "Descripción", "hecho", f"{publicadas} descripción(es) publicadas.",
             "Ver lo descrito", "/descripcion?vista=publicadas", "descripcion")
    else:
        paso("descripcion", "Descripción", "pendiente", "Nada descrito todavía.", None, None, "descripcion")

    if duplicados:
        paso("autoridades", "Agentes y autoridades", "en_curso",
             f"{duplicados} posible(s) duplicado(s) por revisar.", "Revisar duplicados",
             "/vocabularios?vista=sugerencias", "vocabularios")
    else:
        paso("autoridades", "Agentes y autoridades", "hecho" if publicadas else "pendiente",
             "Sin duplicados pendientes." if publicadas else "Se llenan al describir.",
             "Ver autoridades", "/vocabularios", "vocabularios")

    faltan = [n for t, n in (("inventario", "el inventario"), ("guia", "la guía"), ("indice", "el índice"))
              if not aprobados.get(t)]
    if not publicadas:
        paso("difusion", "Instrumentos de descripción", "pendiente",
             "Se generan cuando haya descripciones publicadas.", None, None, "instrumentos")
    elif faltan:
        paso("difusion", "Instrumentos de descripción", "en_curso",
             "Falta aprobar " + ", ".join(faltan) + ".", "Aprobar instrumentos", "/instrumentos?vista=inventario",
             "instrumentos")
    else:
        paso("difusion", "Instrumentos de descripción", "hecho", "Inventario, guía e índice aprobados.",
             "Ver el catálogo", "/instrumentos", "instrumentos")

    # La preservación está fuera del alcance del prototipo: con el módulo apagado no es un paso del avance.
    if settings.preservacion_activa:
        if alterados:
            paso("preservacion", "Preservación", "en_curso", f"{alterados} archivo(s) alterados o ausentes: atienda ya.",
                 "Ver preservación", "/preservacion", "preservacion")
        elif sin_verificar:
            paso("preservacion", "Preservación", "en_curso", f"{sin_verificar} archivo(s) sin verificar todavía.",
                 "Ver preservación", "/preservacion", "preservacion")
        else:
            paso("preservacion", "Preservación", "hecho" if archivos else "pendiente",
                 "Integridad verificada." if archivos else "Sin archivos que preservar.", "Ver preservación",
                 "/preservacion", "preservacion")

    siguiente = next((p for p in pasos if p["estado"] != "hecho" and p["accion"]), None)
    return {"fondo": {"id": str(f), "titulo": fondo.titulo}, "pasos": pasos,
            "siguiente": siguiente["clave"] if siguiente else None,
            "hechos": sum(1 for p in pasos if p["estado"] == "hecho"), "total": len(pasos),
            "conocimiento": conocimiento(db, fondo, duplicados)}


def conocimiento(db: Session, fondo: RecursoDocumental, duplicados: int) -> dict:
    """El conocimiento RiC del fondo en cifras: recursos descritos, entidades de contexto por clase,
    relaciones del grafo, instrumentos vigentes y lo que espera a una persona (descripciones en
    curso, posibles duplicados, relaciones del motor sin evidencia y alertas sin atender)."""
    from app.models.alerta import Alerta
    from app.models.descripcion import EntidadVocabulario, Relacion, TrabajoDescripcion

    f = fondo.id
    recursos = select(RecursoDocumental.id).where(RecursoDocumental.fondo_id == f)
    descritos = _contar(db, select(RecursoDocumental.id).where(
        RecursoDocumental.fondo_id == f, RecursoDocumental.nivel != "fondo", RecursoDocumental.publicado_en.is_not(None)))
    del_fondo = (Relacion.estado == "vigente") & (Relacion.origen_id.in_(recursos) | Relacion.destino_id.in_(recursos))
    relaciones = _contar(db, select(Relacion.id).where(del_fondo))
    # Entidades de contexto citadas por los recursos del fondo, y las unidas a sus actividades (un salto).
    directas = select(Relacion.destino_id).where(Relacion.estado == "vigente", Relacion.origen_id.in_(recursos),
                                                 Relacion.destino_tipo == "entidad_vocabulario").union(
        select(Relacion.origen_id).where(Relacion.estado == "vigente", Relacion.destino_id.in_(recursos),
                                         Relacion.origen_tipo == "entidad_vocabulario"))
    ids = set(db.scalars(directas))
    actividades = set(db.scalars(select(EntidadVocabulario.id).where(EntidadVocabulario.id.in_(ids),
                                                                     EntidadVocabulario.clase == "actividad"))) if ids else set()
    if actividades:
        ids |= set(db.scalars(select(Relacion.destino_id).where(
            Relacion.estado == "vigente", Relacion.origen_id.in_(actividades), Relacion.destino_tipo == "entidad_vocabulario")))
    por_clase = dict(db.execute(select(EntidadVocabulario.clase, func.count()).where(
        EntidadVocabulario.id.in_(ids), EntidadVocabulario.estado == "activa").group_by(EntidadVocabulario.clase)).all()) \
        if ids else {}
    instrumentos = dict(db.execute(select(VersionTrd.instrumento, func.count()).where(
        VersionTrd.fondo_id == f, VersionTrd.estado == "vigente").group_by(VersionTrd.instrumento)).all())
    return {
        "recursos": descritos, "relaciones": relaciones,
        "agentes": por_clase.get("agente", 0), "funciones": por_clase.get("tipo_actividad", 0),
        "actividades": por_clase.get("actividad", 0), "lugares": por_clase.get("lugar", 0),
        "mandatos": por_clase.get("mandato", 0), "materias": por_clase.get("materia", 0),
        "instrumentos_vigentes": sum(instrumentos.values()), "instrumentos": instrumentos,
        "en_curso": _contar(db, select(TrabajoDescripcion.id).where(TrabajoDescripcion.fondo_id == f,
                                                                    TrabajoDescripcion.estado == "abierto")),
        "posibles_duplicados": duplicados,
        "sin_evidencia": _contar(db, select(Relacion.id).where(
            del_fondo, Relacion.origen.in_(("motor", "motor_editado")),
            (Relacion.fragmento.is_(None)) | (Relacion.fragmento == ""))),
        "alertas": _contar(db, select(Alerta.id).where(Alerta.fondo_id == f, Alerta.atendida_en.is_(None))),
    }
