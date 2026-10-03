"""
Punto de entrada de RICORA. Un solo proceso sirve la API (bajo /api) y la
interfaz React ya compilada (todo lo demás), para no sumar un servidor web
aparte en un servidor de 2 GB de memoria.
"""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers import (alertas, auditoria, auth, descripcion, evaluacion, exportacion, fondos, ingesta,
                         instrumentos, preservacion, vocabulario)

logging.basicConfig(level=logging.INFO)

if len(settings.secret_key) < 32:
    raise RuntimeError(
        "Falta RICORA_SECRET_KEY (mínimo 32 caracteres) en el .env: sin ella no se pueden firmar las sesiones."
    )

app = FastAPI(
    title="RICORA",
    description=(
        "Sistema de descripción archivística multinivel y preservación digital "
        "basado en Records in Contexts (RiC-CM 1.0, RiC-O 1.1) del Consejo "
        "Internacional de Archivos. Proyecto de tesis de maestría."
    ),
    version="2.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.include_router(auth.router)
app.include_router(auth.usuarios)
app.include_router(fondos.router)
app.include_router(ingesta.router)
app.include_router(alertas.router)
app.include_router(descripcion.router)
app.include_router(descripcion.catalogo)
app.include_router(vocabulario.router)
app.include_router(instrumentos.router)
app.include_router(preservacion.router)
app.include_router(auditoria.router)
app.include_router(auditoria.gestion)
app.include_router(exportacion.router)
app.include_router(evaluacion.router)
app.include_router(exportacion.uris)  # /id/…: antes de la interfaz, que atiende todo lo demás

# Rutas que no exigen sesión. La prueba de seguridad recorre todas las
# demás y falla si alguna quedó sin la dependencia de autenticación.
RUTAS_PUBLICAS = {
    "/api/salud",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/auth/recuperar",
    "/api/auth/token/{token}",
    "/api/auth/recuperar/{token}",
    "/api/docs",
    "/api/openapi.json",
    # Resolución de URI de RiC-O: decide sola. Sin sesión responde 401
    # salvo que el administrador haya encendido «URI públicas», y nunca
    # entrega lo clasificado o reservado.
    "/id/{ruta:path}",
}


@app.get("/api/salud", tags=["Sistema"], summary="Verificación de que el servicio responde")
def salud() -> dict:
    return {"estado": "ok"}


@app.middleware("http")
async def cabeceras_seguridad(request, call_next):
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "no-referrer")
    return respuesta


# --- Interfaz React compilada -------------------------------------------------
_interfaz = settings.directorio_interfaz
if (_interfaz / "index.html").exists():
    if (_interfaz / "assets").exists():
        app.mount("/assets", StaticFiles(directory=_interfaz / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def interfaz(ruta: str):
        if ruta.startswith("api/"):
            return JSONResponse({"detail": "No existe."}, status_code=404)
        archivo = (_interfaz / ruta).resolve()
        if ruta and archivo.is_file() and _interfaz.resolve() in archivo.parents:
            return FileResponse(archivo)
        # Cualquier otra ruta la resuelve el enrutador de React.
        return FileResponse(_interfaz / "index.html", headers={"Cache-Control": "no-cache"})
else:

    @app.get("/", include_in_schema=False)
    def sin_interfaz():
        raise HTTPException(404, "La interfaz no está compilada; en desarrollo use el servidor de Vite (frontend/).")
