"""Propuestas de descripción en lote, en segundo plano.

RICORA describe y la archivista valida: para cada documento listo y sin describir del fondo se
consulta el motor (con el texto sin datos personales, como siempre) y se guarda su propuesta como
registro inalterable (origen «lote»). Nada se publica: al abrir el documento, el espacio de trabajo
toma esa propuesta en vez de esperar al motor, y la persona revisa, corrige y publica.

El avance vive en la memoria del proceso web; las propuestas quedan en la base a medida que se hacen.
Un documento que ya tiene una propuesta en lote vigente (misma versión de las instrucciones del motor)
no se vuelve a consultar.
"""

import threading
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidencia_ia import PropuestaIA
from app.models.instanciacion import Instanciacion

ORIGEN = "lote"
NIVEL = "unidad_documental"
_en_curso: dict[str, dict] = {}
_candado = threading.Lock()


def vigente(db: Session, instanciacion_id: uuid.UUID) -> PropuestaIA | None:
    """La propuesta en lote de un documento, si sigue vigente y nadie la usó todavía."""
    return db.scalars(select(PropuestaIA).where(PropuestaIA.instanciaciones == [instanciacion_id], *_sin_usar())
                      .order_by(PropuestaIA.generada_en.desc())).first()


def _sin_usar():
    """Condiciones de una propuesta en lote vigente. La propuesta es evidencia inalterable: no se marca al
    usarla; un trabajo que la tomó la cita (trabajos_descripcion.propuesta_id) y con eso deja de estar libre."""
    from app.models.descripcion import TrabajoDescripcion
    from app.servicios import motor

    usada = select(TrabajoDescripcion.id).where(TrabajoDescripcion.propuesta_id == PropuestaIA.id).exists()
    return (PropuestaIA.origen == ORIGEN, PropuestaIA.trabajo_id.is_(None), PropuestaIA.disponible.is_(True),
            PropuestaIA.version_prompt == motor.VERSION_PROMPT, ~usada)


def pendientes(db: Session, fondo_id: uuid.UUID) -> list[Instanciacion]:
    """Los documentos de la cola que no están abiertos por nadie y no tienen propuesta en lote vigente."""
    from app.servicios import descripcion

    return [i for i, quien in descripcion.cola(db, fondo_id) if quien is None and vigente(db, i.id) is None]


def proponer(db: Session, fondo_id: uuid.UUID, inst: Instanciacion, usuario_id: uuid.UUID) -> PropuestaIA | None:
    """La propuesta del motor para un documento, guardada como registro (sin trabajo todavía)."""
    from app.servicios import formas_trd, motor, propuestas_ia, vocabulario
    from app.servicios.datos_personales import anonimizar_para_motor

    documentos = [motor.Documento(id=inst.id, nombre=inst.nombre_original,
                                  texto=anonimizar_para_motor(inst.texto_extraido or "")[0])]
    contexto = vocabulario.contexto_para_motor(db, fondo_id, documentos[0].texto)
    propuesta = motor.proponer(documentos, NIVEL, contexto)
    formas_trd.ajustar(db, fondo_id, propuesta, documentos)
    propuestas_ia.ubicar_fragmentos(db, propuesta)
    return propuestas_ia.registrar(db, propuesta, origen=ORIGEN, fondo_id=fondo_id, nivel=NIVEL,
                                   instanciaciones=[inst.id], solicitada_por_id=usuario_id)


def avance(fondo_id) -> dict | None:
    with _candado:
        e = _en_curso.get(str(fondo_id))
        return dict(e) if e else None


def empezar(fondo_id: uuid.UUID, usuario_id: uuid.UUID, total: int) -> dict:
    clave = str(fondo_id)
    with _candado:
        e = _en_curso.get(clave)
        if e and e["estado"] == "generando":
            return dict(e)
        _en_curso[clave] = estado = {"estado": "generando", "hechas": 0, "total": total, "fallidas": 0,
                                     "inicio": time.time(), "error": None}

    def trabajar():
        import logging

        from app.db.session import SessionLocal
        from app.servicios.auditoria import registrar

        log = logging.getLogger("ricora.propuestas_lote")
        db = SessionLocal()
        hechas = fallidas = 0
        try:
            for inst in pendientes(db, fondo_id):
                try:
                    if proponer(db, fondo_id, inst, usuario_id) is None:
                        raise RuntimeError("sin motor configurado")
                    db.commit()
                    hechas += 1
                except Exception:  # noqa: BLE001 — un documento que falla no detiene a los demás
                    db.rollback()
                    fallidas += 1
                    log.exception("No se pudo proponer la descripción de %s", inst.id)
                with _candado:
                    estado.update(hechas=hechas, fallidas=fallidas)
            registrar(db, modulo="descripcion", accion="propuestas_lote_generadas", usuario_id=usuario_id,
                      entidad_tipo="recurso_documental", entidad_id=fondo_id,
                      detalle=f"{hechas} propuesta(s) de descripción en lote; {fallidas} sin propuesta.")
            db.commit()
            with _candado:
                estado.update(estado="listo")
        except Exception:  # noqa: BLE001
            log.exception("Falló la generación de propuestas en lote")
            db.rollback()
            with _candado:
                estado.update(estado="error", error="No se pudieron generar las propuestas. Intente de nuevo.")
        finally:
            db.close()

    threading.Thread(target=trabajar, name=f"lote-{clave[:8]}", daemon=True).start()
    return dict(estado)
