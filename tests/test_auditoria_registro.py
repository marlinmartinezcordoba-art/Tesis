"""
Registro de actividad de todas las personas (Auditoría · Registro de actividad).

La administración ve las acciones de todas las personas, filtra por persona,
acción y fechas, pagina y exporta. El resultado es real: «fallida» para los
intentos que no se cumplieron (un ingreso fallido), «realizada» para el resto.
"""

import io

from openpyxl import load_workbook

from tests.conftest import crear_usuario, ingresar


def test_la_administracion_ve_la_actividad_de_todas_las_personas(cliente, db, admin, cabeceras_admin):
    ana_u = crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana Ruiz")
    ana = ingresar(cliente, "ana@correo.com")
    cliente.post("/api/auth/login", json={"correo": "ana@correo.com", "contrasena": "equivocada-123"})

    r = cliente.get("/api/auditoria/registro", headers=cabeceras_admin, params={"por_pagina": 5})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["pagina"] == 1 and datos["por_pagina"] == 5 and datos["total"] >= 3
    usuarios = {e["usuario"] for e in datos["eventos"]}
    assert {"Ana Ruiz", admin.nombre} & usuarios
    assert {"Ana Ruiz", admin.nombre} <= {p["nombre"] for p in datos["personas"]}
    resultados = {e["accion"]: e["resultado"] for e in datos["eventos"]}
    assert resultados.get("ingreso_fallido") == "fallida" and resultados.get("inicio_sesion") == "realizada"

    # Filtro por persona.
    solo_ana = cliente.get("/api/auditoria/registro", headers=cabeceras_admin, params={"usuario_id": str(ana_u.id)}).json()
    assert solo_ana["total"] >= 1 and {e["usuario"] for e in solo_ana["eventos"]} == {"Ana Ruiz"}
    # Paginación: una página más allá del final devuelve la última.
    ultima = cliente.get("/api/auditoria/registro", headers=cabeceras_admin, params={"por_pagina": 5, "pagina": 999}).json()
    assert ultima["pagina"] == ultima["paginas"]
    # Excel con el mismo filtro.
    x = cliente.get("/api/auditoria/registro/exportar", headers=cabeceras_admin, params={"usuario_id": str(ana_u.id)})
    filas = list(load_workbook(io.BytesIO(x.content)).active.iter_rows(values_only=True))
    assert filas[0][2] == "Persona" and {f[2] for f in filas[1:]} == {"Ana Ruiz"}

    # Quien no ve toda la auditoría no entra.
    assert cliente.get("/api/auditoria/registro", headers=ana).status_code == 403
    assert cliente.get("/api/auditoria/registro/exportar", headers=ana).status_code == 403
