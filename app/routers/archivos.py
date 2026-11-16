"""Lectura del archivo que llega en un formulario (multipart): una sola implementación para las rutas
de carga. Lee a lo sumo `limite + 1` bytes (el servicio decide qué hacer si se pasa), devuelve los
demás campos de texto del formulario y siempre cierra el formulario (libera el archivo temporal)."""

from fastapi import HTTPException, Request, status
from starlette.datastructures import UploadFile as StarletteUploadFile


async def leer_archivo(request: Request, limite: int, *, falta: str = "No llegó el archivo.",
                       nombre_por_defecto: str = "", rechazar_si_excede: bool = False) -> tuple[bytes, str, dict]:
    formulario = await request.form(max_files=1)
    try:
        archivo = formulario.get("archivo")
        if not isinstance(archivo, StarletteUploadFile):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=falta)
        contenido = await archivo.read(limite + 1)
        if rechazar_si_excede and len(contenido) > limite:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                detail=f"El archivo supera {limite // (1024 * 1024)} MB.")
        campos = {k: v for k, v in formulario.items() if isinstance(v, str)}
        return contenido, archivo.filename or nombre_por_defecto, campos
    finally:
        await formulario.close()
