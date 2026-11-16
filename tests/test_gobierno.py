"""Gobierno archivístico: PGD y PINAR como mandatos RiC que regulan sus programas y acciones."""

from sqlalchemy import select

from app.models.descripcion import EntidadVocabulario, Relacion
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def test_pgd_con_su_programa_en_el_grafo(cliente, db, fondo_descrito, cabeceras_admin, archivista):  # noqa: F811
    url = f"/api/fondos/{fondo_descrito['fondo'].id}/gobierno"
    assert cliente.get(url, headers=archivista).json()["faltan"] == ["PGD", "PINAR"]
    r = cliente.post(f"{url}/planes", headers=cabeceras_admin,
                     json={"tipo": "pgd", "vigencia": "2024/2027", "acto": "Resolución 123 de 2024"})
    assert r.status_code == 200, r.text
    [plan] = r.json()["planes"]
    assert plan["sigla"] == "PGD" and plan["vigencia"] == "2024/2027" and "Resolución 123" in plan["acto"]
    r = cliente.post(f"{url}/planes/{plan['id']}/acciones", headers=cabeceras_admin,
                     json={"tipo": "programa", "nombre": "Programa de documentos vitales"})
    assert r.status_code == 200, r.text
    [accion] = r.json()["planes"][0]["acciones"]
    assert accion["nombre"] == "Programa: Programa de documentos vitales"
    m = db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.nombre == plan["nombre"]))
    assert m.clase == "mandato" and db.scalar(select(Relacion).where(
        Relacion.origen_id == m.id, Relacion.codigo_ric == "regulates_or_regulated", Relacion.estado == "vigente"))
    assert r.json()["faltan"] == ["PINAR"]


def test_validaciones_y_permisos(cliente, fondo_descrito, cabeceras_admin, archivista):  # noqa: F811
    url = f"/api/fondos/{fondo_descrito['fondo'].id}/gobierno/planes"
    assert cliente.post(url, headers=archivista, json={"tipo": "pgd", "vigencia": "2024", "acto": "Resolución 1"}).status_code == 403
    assert cliente.post(url, headers=cabeceras_admin, json={"tipo": "otro", "vigencia": "2024", "acto": "Resolución 1"}).status_code == 422
    assert cliente.post(url, headers=cabeceras_admin, json={"tipo": "pinar", "vigencia": "ayer", "acto": "Resolución 1"}).status_code == 422


def test_pinar_sin_acto_con_vigencia_escrita_y_su_documento(cliente, db, fondo_descrito, cabeceras_admin, archivista):  # noqa: F811
    url = f"/api/fondos/{fondo_descrito['fondo'].id}/gobierno"
    r = cliente.post(f"{url}/planes", headers=cabeceras_admin, json={"tipo": "pinar", "vigencia": "Vigencia 2025 – 2028"})
    assert r.status_code == 200, r.text
    [plan] = r.json()["planes"]
    assert plan["vigencia"] == "2025/2028" and plan["acto"] is None and plan["documento"] is None
    contenido = b"%PDF-1.4 PINAR 2025-2028"
    r = cliente.post(f"{url}/planes/{plan['id']}/documento", headers=cabeceras_admin,
                     files={"archivo": ("PINAR 2025.pdf", contenido, "application/pdf")})
    assert r.status_code == 200, r.text
    doc = r.json()["planes"][0]["documento"]
    assert doc["nombre"] == "PINAR 2025.pdf" and doc["tamano"] == len(contenido) and len(doc["huella"]) == 64
    r = cliente.get(f"{url}/planes/{plan['id']}/documento", headers=archivista)
    assert r.status_code == 200 and r.content == contenido and r.headers["x-huella-sha256"] == doc["huella"]
    # Solo la administración adjunta.
    assert cliente.post(f"{url}/planes/{plan['id']}/documento", headers=archivista,
                        files={"archivo": ("x.pdf", b"x", "application/pdf")}).status_code == 403
