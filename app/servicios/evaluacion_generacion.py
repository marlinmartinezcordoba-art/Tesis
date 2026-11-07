"""
Propuestas de una evaluación generadas en segundo plano, con su avance.

Con dos motores (consenso) o con la IA local, cada documento tarda minutos: generar las
propuestas de 20 documentos en una sola petición se cortaría. Aquí se generan aparte, se
guardan una por una y la pantalla pregunta cuántas van. El estado vive en la memoria del
proceso web; lo que cuenta (las propuestas) queda en la base a medida que se hace.
"""

import threading
import time
import uuid

_en_curso: dict[str, dict] = {}
_candado = threading.Lock()


def avance(evaluacion_id) -> dict | None:
    with _candado:
        e = _en_curso.get(str(evaluacion_id))
        return dict(e) if e else None


def empezar(evaluacion_id: uuid.UUID, usuario_id: uuid.UUID, total: int) -> dict:
    clave = str(evaluacion_id)
    with _candado:
        e = _en_curso.get(clave)
        if e and e["estado"] == "generando":
            return dict(e)
        _en_curso[clave] = estado = {"estado": "generando", "hechas": 0, "total": total, "avisos": [],
                                     "inicio": time.time(), "error": None}

    def trabajar():
        from app.db.session import SessionLocal
        from app.models.evaluacion import Evaluacion
        from app.servicios import evaluacion

        db = SessionLocal()
        try:
            ev = db.get(Evaluacion, evaluacion_id)

            def al_avanzar(hechas, avisos):
                db.commit()
                with _candado:
                    estado.update(hechas=hechas, avisos=list(avisos))

            r = evaluacion.generar_propuestas(db, ev, usuario_id, al_avanzar)
            db.commit()
            with _candado:
                estado.update(estado="listo", hechas=r["generadas"], avisos=r["avisos"])
        except evaluacion.ErrorEvaluacion as exc:
            db.rollback()
            with _candado:
                estado.update(estado="error", error=str(exc))
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger("ricora.evaluacion").exception("Falló la generación de propuestas")
            db.rollback()
            with _candado:
                estado.update(estado="error", error="No se pudieron generar las propuestas. Intente de nuevo.")
        finally:
            db.close()

    threading.Thread(target=trabajar, name=f"propuestas-{clave[:8]}", daemon=True).start()
    return dict(estado)
