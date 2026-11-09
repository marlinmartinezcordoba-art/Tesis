"""Mejora de la página escaneada antes del OCR: sin sombras ni fondo, con contraste y en blanco y negro."""

import random
import shutil
import subprocess

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from app.servicios import mejora_imagen


def _pagina_mala() -> Image.Image:
    ancho, alto = 1400, 900
    img = Image.new("L", (ancho, alto), 255)
    d = ImageDraw.Draw(img)
    try:
        fuente = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 34)
    except OSError:
        fuente = ImageFont.load_default()
    for i, t in enumerate(["Resolución 0457 del 12 de marzo de 1994", "Por la cual se sustrae un área de la",
                           "reserva forestal del Pacífico en Tumaco.", "El Director General del INDERENA"] * 2):
        d.text((100, 80 + i * 90), t, fill=70, font=fuente)
    # Sombra que oscurece la mitad derecha, desenfoque y motas.
    sombra = Image.linear_gradient("L").rotate(90).resize((ancho, alto)).point(lambda v: int(v * 0.6))
    img = ImageChops.subtract(img, sombra).filter(ImageFilter.GaussianBlur(1.4))
    px, azar = img.load(), random.Random(1)
    for _ in range(20000):
        px[azar.randrange(ancho), azar.randrange(alto)] = azar.randrange(40, 200)
    return img


def test_la_pagina_mejorada_conserva_su_tamano_y_queda_en_blanco_y_negro():
    mala = _pagina_mala()
    limpia = mejora_imagen.mejorar(mala)
    assert limpia.size == mala.size  # las cajas de la evidencia siguen coincidiendo con el original
    assert set(limpia.getdata()) <= {0, 255}
    # El fondo queda blanco: la sombra desaparece (la esquina derecha, antes gris oscuro, ahora es papel).
    assert mala.crop((1300, 800, 1390, 890)).convert("L").getextrema()[1] < 200
    assert sum(limpia.crop((1300, 800, 1390, 890)).getdata()) / (90 * 90) > 240


def test_el_ocr_lee_mas_y_con_mas_confianza_la_pagina_mejorada(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Sin Tesseract en este equipo")
    mala = _pagina_mala()
    mala.save(tmp_path / "mala.png")
    mejora_imagen.mejorar(mala).save(tmp_path / "limpia.png")

    def lectura(nombre):
        filas = subprocess.run(["tesseract", str(tmp_path / nombre), "-", "-l", "spa", "tsv"], capture_output=True,
                               text=True).stdout.splitlines()[1:]
        conf = [float(c[10]) for c in (f.split("\t") for f in filas) if len(c) > 11 and c[11].strip() and float(c[10]) >= 0]
        return len(conf), sum(conf) / max(1, len(conf)), " ".join(c[11] for c in (f.split("\t") for f in filas) if len(c) > 11)

    palabras_mala, conf_mala, _ = lectura("mala.png")
    palabras_limpia, conf_limpia, texto = lectura("limpia.png")
    assert conf_limpia >= conf_mala
    assert "INDERENA" in texto and "1994" in texto


def test_umbral_otsu_separa_papel_y_tinta():
    img = Image.new("L", (100, 100), 230)
    ImageDraw.Draw(img).rectangle((0, 0, 30, 100), fill=40)
    assert 40 <= mejora_imagen._umbral_otsu(img) < 230
