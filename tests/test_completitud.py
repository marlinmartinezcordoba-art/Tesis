"""
Completitud revisada por el sistema y motor que no respondió.

- Con el texto de cada página, el sistema detecta hojas en blanco o ilegibles,
  numeración que salta, total declarado distinto de las páginas del archivo y
  páginas repetidas; propone la nota de completitud (rico:integrityNote) y cada
  hallazgo dice su página. Sin señales, propone «Completo» con lo que revisó.
- Un archivo sin texto por página no se da por completo: se revisa a mano.
- Un fallo pasajero del motor se reintenta una vez; si aun así no responde, se
  puede volver a consultar desde la pantalla sin perder el avance, y un trabajo
  que se recupera no hereda una propuesta que no llegó.
"""

import uuid

import httpx

from app.models.evidencia_ia import PaginaTexto
from app.servicios import completitud, motor
from tests.test_descripcion import (MotorDePrueba, RESPUESTA_UNO, archivista, documento, fondo,  # noqa: F401
                                    iniciar, motor_prueba)

RELLENO = ("La Secretaría General informa a la Dirección sobre el trámite de la licencia ambiental del proyecto y "
           "solicita los conceptos técnicos de las dependencias competentes para continuar el procedimiento. ")


def _con_paginas(db, fondo, textos, nombre="res.pdf", confianzas=None):  # noqa: F811
    texto, posiciones = "", []
    for t in textos:
        inicio = len(texto)
        texto += t + "\n\f"
        posiciones.append((inicio, inicio + len(t)))
    d = documento(db, fondo, nombre, texto)
    for n, (i, f) in enumerate(posiciones, start=1):
        db.add(PaginaTexto(id=uuid.uuid4(), instanciacion_id=d.id, numero=n, inicio=i, fin=f, origen="ocr",
                           confianza=(confianzas or {}).get(n, 92.0)))
    db.commit()
    return d


def _tipos(r):
    return {h["tipo"]: h for h in r["hallazgos"]}


def test_documento_completo(db, fondo):  # noqa: F811
    d = _con_paginas(db, fondo, [f"{RELLENO}Página {n} de 3. Hoja número {n}." for n in (1, 2, 3)])
    r = completitud.revisar(db, d)
    assert r["hallazgos"] == [] and r["nota"].startswith("Completo según la revisión automática: 3 páginas")
    assert "numeración continua (3 declaradas)" in r["nota"]


def test_falta_una_hoja_y_el_total_no_cuadra(db, fondo):  # noqa: F811
    paginas = [f"{RELLENO}Página {n} de 4. Hoja {n}." for n in (1, 2, 4)]
    r = completitud.revisar(db, _con_paginas(db, fondo, paginas))
    h = _tipos(r)
    assert h["numeracion_salta"]["faltantes"] == [3] and h["numeracion_salta"]["paginas"] == [2, 3]
    assert "falta la hoja 3" in h["numeracion_salta"]["detalle"]
    assert "dice tener 4 páginas y el archivo trae 3: falta 1" in h["total_distinto"]["detalle"]
    assert r["nota"].startswith("Revisión automática, por confirmar:")


def test_folios_que_saltan_y_consta_de(db, fondo):  # noqa: F811
    paginas = [f"Consta de 5 folios. {RELLENO}Folio 1", f"{RELLENO}Folio 2", f"{RELLENO}Folio 5"]
    r = completitud.revisar(db, _con_paginas(db, fondo, paginas))
    h = _tipos(r)
    assert h["numeracion_salta"]["faltantes"] == [3, 4] and "faltan las hojas 3, 4" in h["numeracion_salta"]["detalle"]
    assert "dice tener 5 folios y el archivo trae 3: faltan 2" in h["total_distinto"]["detalle"]


def test_blanca_ilegible_y_repetida(db, fondo):  # noqa: F811
    repetida = RELLENO * 3
    paginas = [repetida, "   ·  ", RELLENO + " Anexo técnico con cifras.", repetida]
    r = completitud.revisar(db, _con_paginas(db, fondo, paginas, confianzas={3: 41.0}))
    h = _tipos(r)
    assert h["pagina_sin_texto"]["paginas"] == [2]
    assert h["ocr_dificil"]["paginas"] == [3]
    assert h["pagina_repetida"]["paginas"] == [4] and "la 4 es igual a la 1" in h["pagina_repetida"]["detalle"]


def test_sin_texto_por_pagina_no_se_da_por_completo(db, fondo):  # noqa: F811
    d = documento(db, fondo, "a.pdf", "Texto sin páginas guardadas.")
    r = completitud.revisar(db, d)
    assert r["revisable"] is False and r["nota"] is None and "a mano" in r["explicacion"]


def test_el_espacio_de_trabajo_trae_la_completitud(cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    d = _con_paginas(db, fondo, [f"{RELLENO}Página {n} de 4." for n in (1, 2, 4)])
    espacio = iniciar(cliente, archivista, [d.id])
    c = espacio["completitud"]
    assert c["con_hallazgos"] == 2 and "falta la hoja 3" in c["nota_propuesta"]


def test_fallo_pasajero_del_motor_se_reintenta_una_vez(monkeypatch):
    llamadas = []

    def post(*_a, **_k):
        llamadas.append(1)
        if len(llamadas) == 1:
            return httpx.Response(503, text="saturado")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "hola"}]}}]})

    monkeypatch.setattr(motor.httpx, "post", post)
    monkeypatch.setattr(motor.time, "sleep", lambda *_: None)
    g = motor.MotorGemini("x", "m")
    assert g._llamar({}) == "hola" and len(llamadas) == 2

    def lento(*_a, **_k):
        raise httpx.ReadTimeout("lento")

    monkeypatch.setattr(motor.httpx, "post", lento)
    try:
        g._llamar({})
    except motor.MotorError as exc:
        assert "tardó más de" in str(exc)
    else:
        raise AssertionError("debía fallar")


def test_volver_a_consultar_el_motor_sin_perder_el_avance(cliente, db, fondo, archivista, monkeypatch):  # noqa: F811
    class Roto:
        nombre = "roto"

        def analizar(self, *_):
            raise motor.MotorError("No hubo conexión con el motor de análisis.")

    monkeypatch.setattr(motor, "motor_activo", lambda: Roto())
    d = documento(db, fondo, "a.pdf", "Oficio de la Alcaldía Municipal sobre el estado del archivo.")
    espacio = iniciar(cliente, archivista, [d.id])
    assert espacio["propuesta"]["disponible"] is False and "Volver a consultar el motor" in espacio["propuesta"]["aviso"]
    cliente.put(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/borrador", headers=archivista,
                json={"borrador": {"titulo": "A mano"}})
    # Si se sale y vuelve, el avance vuelve pero la propuesta fallida no se hereda: se consulta otra vez.
    cliente.post(f"/api/descripcion/{espacio['trabajo_id']}/cancelar", headers=archivista)
    bueno = MotorDePrueba(RESPUESTA_UNO)
    monkeypatch.setattr(motor, "motor_activo", lambda: bueno)
    otra_vez = iniciar(cliente, archivista, [d.id])
    assert otra_vez["borrador"] == {"titulo": "A mano"} and otra_vez["propuesta"]["disponible"] is True
    assert len(bueno.llamadas) == 1
    # Y desde la pantalla se puede volver a consultar cuando haga falta.
    r = cliente.post(f"/api/descripcion/trabajos/{otra_vez['trabajo_id']}/reproponer", headers=archivista)
    assert r.status_code == 200 and r.json()["propuesta"]["disponible"] is True and len(bueno.llamadas) == 2
    assert r.json()["borrador"] == {"titulo": "A mano"}
