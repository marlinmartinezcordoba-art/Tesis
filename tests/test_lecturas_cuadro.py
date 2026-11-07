"""Lectura en segundo plano con avance: cuántos archivos van, cuántos faltan y cómo quedó cada uno."""

import io
import time
import uuid
import zipfile

from app.servicios import cuadro, lecturas_cuadro

CAB = "Código,Dependencia,Código serie,Serie,Subserie,Tipos documentales,AG,AC,CT,E,S,M,Procedimiento\n"


def _zip(n):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(n):
            z.writestr(f"{i:02d}.csv", CAB + f"{100 + i},Despacho {i},1,Actas,,Acta,2,8,X,,,,C\n")
        z.writestr("roto.csv", "Nada,que ver\n1,2\n")
    return buf.getvalue()


def test_el_avance_cuenta_cada_archivo_del_paquete():
    vistos = []
    cuadro.vista_previa(_zip(3), "TRD.zip", lambda h, t, a, arch: vistos.append((h, t, a, len(arch))))
    # Cada archivo se anuncia antes de leerlo; al final, todos hechos.
    assert (0, 4, "00.csv", 0) in vistos and (3, 4, "roto.csv", 3) in vistos
    assert vistos[-1] == (4, 4, None, 4)


def _esperar(lectura_id, usuario):
    for _ in range(200):
        e = lecturas_cuadro.consultar(lectura_id, usuario)
        if e["estado"] != "leyendo":
            return e
        time.sleep(0.05)
    raise AssertionError("la lectura no terminó")


def test_lectura_en_segundo_plano_termina_con_la_vista_previa(monkeypatch):
    from app.servicios import versiones_trd

    monkeypatch.setattr(versiones_trd, "guardar_original",
                        lambda c, n: {"huella": "abc", "archivo": n, "tamano": len(c)})
    usuario = uuid.uuid4()
    inicio = lecturas_cuadro.empezar(_zip(2), "TRD.zip", usuario)
    e = _esperar(inicio["id"], usuario)
    assert e["estado"] == "listo"
    assert e["hechos"] == e["total"] == 3 and e["faltan"] == 0
    assert [a["estado"] for a in e["archivos"]] == ["leido", "leido", "sin_tabla"]
    assert len(e["resultado"]["filas"]) == 2 and e["resultado"]["original"]["huella"] == "abc"
    # Otra persona no ve la lectura.
    assert lecturas_cuadro.consultar(inicio["id"], uuid.uuid4()) is None


def test_lectura_que_falla_informa_el_motivo():
    usuario = uuid.uuid4()
    inicio = lecturas_cuadro.empezar(b"no es un zip", "TRD.zip", usuario)
    e = _esperar(inicio["id"], usuario)
    assert e["estado"] == "error" and "dañado" in e["error"]
