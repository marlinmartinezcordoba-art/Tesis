"""
Lectura en segundo plano de la TRD, el CCD o la TVD, con su avance.

Un paquete de 100 PDF, o uno que lee la IA local, puede tardar muchos minutos. En vez de
dejar a la persona mirando una barra sin saber nada, la lectura corre aparte y la pantalla
pregunta cada pocos segundos: cuántos archivos van, cuántos faltan, cuál se está leyendo y
cómo quedó cada uno. El estado vive en la memoria del proceso web (un solo proceso) y se
olvida a la hora; nada de esto se guarda en la base.
"""

import threading
import time
import uuid

from app.servicios import cuadro

DURACION = 3600  # segundos que se recuerda una lectura terminada
_lecturas: dict[str, dict] = {}
_candado = threading.Lock()


def _limpiar() -> None:
    ahora = time.time()
    for clave in [k for k, v in _lecturas.items() if ahora - v["actualizada"] > DURACION]:
        _lecturas.pop(clave, None)


def empezar(contenido: bytes, nombre: str, usuario_id) -> dict:
    """Empieza a leer en segundo plano y devuelve el estado inicial (con su id)."""
    lectura_id = uuid.uuid4().hex
    estado = {"id": lectura_id, "usuario": str(usuario_id), "estado": "leyendo", "hechos": 0, "total": 1,
              "actual": nombre, "archivos": [], "inicio": time.time(), "actualizada": time.time(),
              "resultado": None, "error": None, "codigo": None}
    with _candado:
        _limpiar()
        _lecturas[lectura_id] = estado

    def avance(hechos, total, actual, archivos):
        with _candado:
            estado.update(hechos=hechos, total=max(total, 1), actual=actual, archivos=list(archivos),
                          actualizada=time.time())

    def leer():
        try:
            vista = cuadro.vista_previa(contenido, nombre, avance)
            from app.servicios import versiones_trd

            original = versiones_trd.guardar_original(contenido, nombre)
            resultado = {**vista, "original": {k: original[k] for k in ("huella", "archivo", "tamano")}}
            with _candado:
                estado.update(estado="listo", resultado=resultado, hechos=estado["total"], actual=None,
                              archivos=vista.get("archivos", estado["archivos"]), actualizada=time.time())
        except cuadro.ErrorCuadro as exc:
            with _candado:
                estado.update(estado="error", error=str(exc), codigo=exc.codigo, actual=None, actualizada=time.time())
        except Exception:  # noqa: BLE001 — cualquier otra falla se informa sin detalles técnicos
            import logging

            logging.getLogger("ricora.cuadro").exception("Falló la lectura en segundo plano de %s", nombre)
            with _candado:
                estado.update(estado="error", error="No se pudo leer el archivo. Intente de nuevo.", codigo=500,
                              actual=None, actualizada=time.time())

    threading.Thread(target=leer, name=f"lectura-{lectura_id[:8]}", daemon=True).start()
    return consultar(lectura_id, usuario_id)


def consultar(lectura_id: str, usuario_id) -> dict | None:
    """El avance de una lectura de esta persona (None si no existe o es de otra)."""
    with _candado:
        e = _lecturas.get(lectura_id)
        if e is None or e["usuario"] != str(usuario_id):
            return None
        return {"id": e["id"], "estado": e["estado"], "hechos": e["hechos"], "total": e["total"],
                "faltan": max(0, e["total"] - e["hechos"]), "actual": e["actual"], "archivos": e["archivos"],
                "segundos": round(time.time() - e["inicio"]), "error": e["error"], "codigo": e["codigo"],
                "resultado": e["resultado"]}
