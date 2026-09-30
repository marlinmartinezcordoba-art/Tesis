"""
Cierre del módulo transversal de autenticación (prompt §10–11), ahora que
existen los siete módulos: cada uno de los cuatro roles contra un
endpoint real de lectura y uno de escritura de cada módulo, y el revisor
contra TODAS las rutas que modifican algo en la aplicación real.
"""

import uuid

import pytest
from fastapi.routing import APIRoute

from app.main import RUTAS_PUBLICAS, app
from app.models.recurso_documental import RecursoDocumental
from tests.conftest import crear_usuario, ingresar

# Rutas que modifican algo pero son del propio usuario sobre su propia
# cuenta (cualquier rol autenticado puede usarlas).
PROPIAS = {"/api/auth/logout", "/api/auth/refresh", "/api/auth/perfil", "/api/auth/perfil/contrasena"}


@pytest.fixture()
def fondo(db, admin):
    f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Correspondencia municipal")
    f.fondo_id = f.id
    db.add(f)
    db.commit()
    return f


def _peticiones(fondo_id: str):
    """(módulo, operación) → petición real. «Permitido» es que no responda 401/403."""
    otro = str(uuid.uuid4())
    return {
        ("ingesta", "leer"): ("get", "/api/ingesta/cola", {"params": {"fondo_id": fondo_id}}),
        ("ingesta", "escribir"): ("post", "/api/ingesta/cargar", {"data": {"fondo_id": fondo_id},
                                                                  "files": [("archivos", ("a.txt", b"hola", "text/plain"))]}),
        ("descripcion", "leer"): ("get", "/api/descripcion/cola", {"params": {"fondo_id": fondo_id}}),
        ("descripcion", "escribir"): ("post", "/api/descripcion/iniciar", {"json": {"instanciacion_ids": [otro]}}),
        ("vocabularios", "leer"): ("get", "/api/vocabulario", {"params": {"fondo_id": fondo_id}}),
        ("vocabularios", "escribir"): ("post", "/api/vocabulario/detectar", {"params": {"fondo_id": fondo_id}}),
        ("instrumentos", "leer"): ("get", "/api/instrumentos/catalogo", {"params": {"fondo_id": fondo_id}}),
        ("instrumentos", "escribir"): ("post", "/api/instrumentos/guia", {"json": {"fondo_id": fondo_id}}),
        ("preservacion", "leer"): ("get", "/api/preservacion/panel", {"params": {"fondo_id": fondo_id}}),
        ("preservacion", "escribir"): ("post", f"/api/preservacion/instanciacion/{otro}/verificar", {}),
        ("auditoria", "leer"): ("get", "/api/auditoria/mi-trazabilidad", {}),
        ("auditoria", "panel"): ("get", "/api/auditoria/consolidado", {}),
        ("usuarios", "leer"): ("get", "/api/auth/usuarios", {}),
        ("usuarios", "escribir"): ("post", "/api/auth/usuarios", {"json": {"nombre": "X", "correo": "x@correo.com", "rol": "consulta"}}),
    }


T, F = True, False
ESPERADO = {
    #                    ingesta    descripción vocabularios instrumentos preservación auditoría  usuarios
    #                    leer escr  leer escr   leer escr    leer escr    leer escr    mía panel  leer escr
    "administrador": [T, T, T, T, T, T, T, T, T, T, T, T, T, T],
    "archivista":    [T, T, T, T, T, T, T, T, T, T, T, F, F, F],
    "revisor":       [T, F, T, F, T, F, T, F, T, F, T, F, F, F],
    "consulta":      [F, F, F, F, F, F, T, F, F, F, F, F, F, F],  # solo el catálogo de instrumentos
}


@pytest.mark.parametrize("rol", list(ESPERADO))
def test_cada_rol_contra_un_endpoint_real_de_cada_modulo(cliente, db, fondo, buzon, rol):
    crear_usuario(db, f"real.{rol}@correo.com", rol)
    cabeceras = ingresar(cliente, f"real.{rol}@correo.com")
    for (clave, (metodo, ruta, extra)), permitido in zip(_peticiones(str(fondo.id)).items(), ESPERADO[rol]):
        codigo = getattr(cliente, metodo)(ruta, headers=cabeceras, **extra).status_code
        if permitido:
            assert codigo not in (401, 403), (rol, clave, codigo)
        else:
            assert codigo == 403, (rol, clave, codigo)


def _ruta_concreta(ruta: str) -> str:
    """Rellena los parámetros de la ruta con valores que no existen."""
    partes = []
    for p in ruta.split("/"):
        partes.append(str(uuid.uuid4()) if p.startswith("{") else p)
    return "/".join(partes)


def test_el_revisor_no_modifica_nada_en_ninguna_ruta_real(cliente, db):
    crear_usuario(db, "revisor.real@correo.com", "revisor")
    cabeceras = ingresar(cliente, "revisor.real@correo.com")
    revisadas = 0
    for r in app.routes:
        if not isinstance(r, APIRoute) or not r.path.startswith("/api") or r.path in RUTAS_PUBLICAS or r.path in PROPIAS:
            continue
        for metodo in r.methods - {"GET", "HEAD"}:
            codigo = cliente.request(metodo, _ruta_concreta(r.path), headers=cabeceras, json={}).status_code
            assert codigo == 403, f"{metodo} {r.path} respondió {codigo} al revisor"
            revisadas += 1
    assert revisadas > 30  # todas las rutas que modifican algo, de los siete módulos


def test_nadie_entra_sin_sesion_a_ningun_modulo_real(cliente, db, fondo):
    for (clave, (metodo, ruta, extra)) in _peticiones(str(fondo.id)).items():
        assert getattr(cliente, metodo)(ruta, **extra).status_code == 401, clave
