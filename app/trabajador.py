"""
Trabajador de ingesta: proceso aparte del servidor web que toma, de a uno,
los documentos en estado «procesando» y los procesa (huella, duplicados,
formato, texto u OCR). Si el OCR de un archivo pesado falla o consume
memoria, el servidor web sigue respondiendo.

    python -m app.trabajador
"""

import logging
import signal
import time

from sqlalchemy import update
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.db.session import SessionLocal
from app.models.instanciacion import Instanciacion
from app.servicios import procesamiento

log = logging.getLogger("ricora.trabajador")
_detener = False


def _al_detener(*_):
    global _detener
    _detener = True
    log.info("Se pidió detener el trabajador; termina el documento en curso.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _al_detener)
    signal.signal(signal.SIGINT, _al_detener)
    liberado = False
    log.info("Trabajador de ingesta en marcha.")
    while not _detener:
        try:
            with SessionLocal() as db:
                if not liberado:
                    # Hay un solo trabajador: lo que quedó tomado antes de un
                    # reinicio se libera para procesarlo de nuevo.
                    db.execute(update(Instanciacion).where(Instanciacion.estado == "procesando")
                               .values(tomado_en=None))
                    db.commit()
                    liberado = True
                siguiente = procesamiento.tomar_siguiente(db)
                if siguiente is not None:
                    log.info("Procesando %s", siguiente)
                    procesamiento.procesar(db, siguiente)
                    continue
        except (OperationalError, ProgrammingError) as exc:
            # Base de datos aún no disponible o migraciones pendientes.
            log.warning("Base de datos no disponible todavía: %s", type(exc).__name__)
            time.sleep(5)
            continue
        time.sleep(2)
    log.info("Trabajador detenido.")


if __name__ == "__main__":
    main()
