"""
Trabajador en segundo plano, proceso aparte del servidor web:
- ingesta: toma, de a uno, los documentos en estado «procesando» y los
  procesa (huella, duplicados, formato, texto u OCR);
- vocabularios: cada cierto tiempo (24 h por defecto) busca pares de
  entidades parecidas y deja sugerencias de fusión, sin fusionar nada;
- auditoría: cada minuto cierra las sesiones vencidas, con su evento;
- preservación: cada cierto tiempo (30 días por defecto) recalcula la
  huella de todas las instanciaciones, primaria y segunda copia, y alerta
  si alguna cambió; cada minuto crea las segundas copias que falten
  (fondos anteriores o cambio del lugar configurado);
- mecanismos: cada minuto vincula a su agente mecanismo del vocabulario
  las filas guardadas antes de la migración 0013 con el programa como texto.
Si el OCR de un archivo pesado falla o consume memoria, el servidor web
sigue respondiendo.

    python -m app.trabajador
"""

import logging
import signal
import time

from sqlalchemy import update
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.db.session import SessionLocal
from app.models.instanciacion import Instanciacion
from app.servicios import mecanismos, preservacion, procesamiento, sesiones, vocabulario

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
    ultima_revision_sesiones = ultima_replica = float("-inf")
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
                # Auditoría: las sesiones vencidas se cierran solas (con su
                # evento de expiración) aunque nadie vuelva a entrar.
                if time.monotonic() - ultima_revision_sesiones >= 60:
                    if sesiones.cerrar_vencidas(db):
                        db.commit()
                    ultima_revision_sesiones = time.monotonic()
                # Vocabularios: búsqueda periódica de candidatos a fusión
                # (solo cuando toca según el intervalo configurado).
                nuevas = vocabulario.deteccion_periodica(db)
                if nuevas:
                    log.info("Vocabulario: %s sugerencia(s) de fusión nuevas.", nuevas)
                # Preservación: verificación periódica de integridad.
                verificadas = preservacion.verificacion_periodica(db)
                if verificadas is not None:
                    log.info("Preservación: %s instanciación(es) verificadas.", verificadas)
                if time.monotonic() - ultima_replica >= 60:
                    replicadas = preservacion.replicar_pendientes(db)
                    if replicadas:
                        log.info("Preservación: %s segunda(s) copia(s) creadas.", replicadas)
                    ultima_replica = time.monotonic()
                    vinculadas = mecanismos.vincular_anteriores(db)
                    if vinculadas:
                        db.commit()
                        log.info("Mecanismos: %s fila(s) anteriores vinculadas a su agente.", vinculadas)
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
