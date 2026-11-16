"""Importación de un FUID existente: cada fila, un expediente en su serie del cuadro."""

import io

from openpyxl import Workbook
from sqlalchemy import select

from app.models.recurso_documental import RecursoDocumental
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def _fuid(filas):
    wb = Workbook()
    h = wb.active
    h.append(["FORMATO ÚNICO DE INVENTARIO DOCUMENTAL"])
    h.append(["Número de orden", "Código", "Nombre de las series, subseries o asuntos", "Fecha inicial", "Fecha final",
              "Caja", "Carpeta", "Tomo", "Otro", "Número de folios", "Soporte", "Frecuencia de consulta", "Notas"])
    for f in filas:
        h.append(f)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_vista_previa_y_aplicar(cliente, db, fondo_descrito, cabeceras_admin, archivista):  # noqa: F811
    f = fondo_descrito
    contenido = _fuid([[1, "CO", "Correspondencia con la Gobernación", "1950", "1952", "4", "2", "", "", 120, "Papel", "Baja", ""],
                       [2, "XX", "Serie que no existe", "1950", "1950", "", "", "", "", 3, "Papel", "", ""]])
    archivo = {"archivo": ("fuid.xlsx", contenido)}
    url = f"/api/fondos/{f['fondo'].id}/fuid"
    r = cliente.post(f"{url}/vista-previa", headers=cabeceras_admin, files=archivo)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["validas"] == 1 and v["con_problemas"] == 1
    ok = v["filas"][0]
    assert ok["serie"] == "Correspondencia" and ok["codigo"] == "CO-0001" and ok["folios"] == 120 and ok["caja"] == "4"
    assert cliente.post(f"{url}/vista-previa", headers=archivista, files=archivo).status_code == 403
    r = cliente.post(f"{url}/aplicar", headers=cabeceras_admin, files={"archivo": ("fuid.xlsx", contenido)})
    assert r.status_code == 200 and r.json()["creados"] == 1 and r.json()["fuera"] == 1, r.text
    e = db.scalar(select(RecursoDocumental).where(RecursoDocumental.codigo_referencia == "CO-0001"))
    assert e.nivel == "expediente" and e.incluido_en_id == f["serie"].id and e.folios == 120
    assert e.frecuencia_consulta == "baja" and e.fechas_extremas_edtf == "1950/1952"
    # Volver a importar el mismo FUID no duplica: la fila ya existe.
    again = cliente.post(f"{url}/vista-previa", headers=cabeceras_admin, files={"archivo": ("fuid.xlsx", contenido)}).json()
    assert again["validas"] == 0
