"""
Prueba de OCR intermitente (auditoría, sección 4; ING-05/ING-09): con
varios reconocimientos a la vez, Tesseract (OpenMP) se volvía lento e
impredecible y podía pasar del límite de tiempo. Con un hilo por proceso,
ocho reconocimientos simultáneos terminan a tiempo y dan la misma confianza.
"""

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from app.servicios import texto
from tests import archivos


def test_tesseract_se_ejecuta_con_un_hilo(monkeypatch, tmp_path):
    vistos = []
    original = subprocess.run

    def espia(*a, **kw):
        vistos.append(kw.get("env") or {})
        return original(*a, **kw)

    monkeypatch.setattr(texto.subprocess, "run", espia)
    imagen = tmp_path / "oficio.png"
    imagen.write_bytes(archivos.png_con_texto())
    texto._tesseract(imagen)
    assert vistos and vistos[0].get("OMP_THREAD_LIMIT") == "1"


def test_ocho_reconocimientos_simultaneos_terminan_a_tiempo_y_coinciden(tmp_path):
    imagen = tmp_path / "oficio.png"
    imagen.write_bytes(archivos.png_con_texto())
    inicio = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as grupo:
        lecturas = list(grupo.map(lambda _: texto._tesseract(imagen), range(8)))
    duracion = time.monotonic() - inicio
    promedios = {texto.promedio([lectura]) for lectura in lecturas}
    assert len(promedios) == 1, promedios  # mismo resultado en las ocho
    [(confianza, palabras)] = promedios
    assert palabras > 0 and confianza >= 70
    assert duracion < 60, f"ocho reconocimientos tardaron {duracion:.0f} s"
