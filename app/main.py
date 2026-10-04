"""
Punto de entrada de RICORA. Un solo proceso sirve la API (bajo /api) y la
interfaz React ya compilada (todo lo demás), para no sumar un servidor web
aparte en un servidor de 2 GB de memoria.
"""

import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.routers import (alertas, auditoria, auth, busqueda, descripcion, evaluacion, exportacion, fondos, ingesta, publico,
                         grafo, instrumentos, perfil_agn, preservacion, vocabulario)

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
app.include_router(perfil_agn.router)
app.include_router(preservacion.router)
app.include_router(auditoria.router)
app.include_router(auditoria.gestion)
app.include_router(auditoria.revision)
app.include_router(exportacion.router)
app.include_router(grafo.router)
app.include_router(busqueda.router)
app.include_router(evaluacion.router)
app.include_router(publico.router)  # datos abiertos: el subconjunto público (INS-01, INS-04, INS-05, INS-08)
app.include_router(exportacion.uris)  # /id/…: antes de la interfaz, que atiende todo lo demás

# Rutas que no exigen sesión. La prueba de seguridad recorre todas las
# demás y falla si alguna quedó sin la dependencia de autenticación.
RUTAS_PUBLICAS = {
    "/api/salud",
    "/api/auth/login",
    "/api/auth/login/segundo-factor",
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
    # Datos abiertos (app/routers/publico.py): la misma regla que /id/.
    "/api/publico/rdf",
    "/api/publico/sparql",
    "/api/publico/ead3",
    "/api/publico/eac/{entidad_id}",
    "/api/publico/ley1712",
    "/api/publico/iiif/{recurso_id}/manifest",
    "/api/publico/iiif/imagen/{instanciacion_id}/{pagina}.png",
    "/api/publico/dip/{recurso_id}",
}


@app.get("/api/salud", tags=["Sistema"],
         summary="Salud del sistema: base de datos, almacén, trabajador y respaldo (para un monitor externo)")
def salud(db: Session = Depends(get_db)):
    from app.servicios import salud as servicio_salud

    codigo, datos = servicio_salud.estado(db)
    return JSONResponse(datos, status_code=codigo)


@app.middleware("http")
async def cabeceras_seguridad(request, call_next):
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "no-referrer")
    # Brecha NFR-01 (lote 3): política de contenido, permisos del navegador y HSTS.
    respuesta.headers.setdefault("Content-Security-Policy", politica_contenido(request.url.path, request.url.scheme == "https"))
    respuesta.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    respuesta.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.url.scheme == "https":
        # Un año, con subdominios: el navegador no vuelve a intentar HTTP.
        respuesta.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return respuesta


# Lo único externo que carga la interfaz: las fuentes tipográficas (Google
# Fonts) y el mapa de un lugar (OpenStreetMap, en un marco). Nada de scripts
# de terceros. La documentación de la API (Swagger) trae su propio código de
# un CDN y por eso tiene una política aparte, solo en /api/docs.
POLITICA_INTERFAZ = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob:; connect-src 'self'; frame-src https://www.openstreetmap.org; "
    "frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"
)
POLITICA_DOCS = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
)


def politica_contenido(ruta: str, https: bool) -> str:
    politica = POLITICA_DOCS if ruta.startswith("/api/docs") else POLITICA_INTERFAZ
    return politica + ("; upgrade-insecure-requests" if https else "")


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
