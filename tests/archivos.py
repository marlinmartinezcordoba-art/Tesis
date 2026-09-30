"""Archivos de prueba generados en el momento (nada de datos reales)."""

import io
import os

from PIL import Image, ImageDraw, ImageFont

TEXTO_ACTA = "Acta del Concejo Municipal, sesion ordinaria del 20 de julio de 1948. Se aprobo el presupuesto."


def txt(texto: str = TEXTO_ACTA) -> bytes:
    return texto.encode("utf-8")


def pdf_con_texto(texto: str = TEXTO_ACTA) -> bytes:
    """PDF mínimo válido, de una página, con capa de texto."""
    flujo = f"BT /F1 12 Tf 50 750 Td ({texto}) Tj ET".encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(flujo)).encode() + b" >>\nstream\n" + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = io.BytesIO()
    salida.write(b"%PDF-1.4\n")
    posiciones = []
    for i, obj in enumerate(objetos, start=1):
        posiciones.append(salida.tell())
        salida.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = salida.tell()
    salida.write(f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode())
    for p in posiciones:
        salida.write(f"{p:010d} 00000 n \n".encode())
    salida.write(f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return salida.getvalue()


def _imagen_con_texto(lineas=("ARCHIVO MUNICIPAL", "OFICIO NUMERO 114", "BOGOTA 1948")) -> Image.Image:
    img = Image.new("L", (1700, 700), 255)
    dibujo = ImageDraw.Draw(img)
    fuente = ImageFont.load_default(size=90)
    for i, linea in enumerate(lineas):
        dibujo.text((80, 80 + i * 180), linea, fill=0, font=fuente)
    return img


def png_con_texto() -> bytes:
    salida = io.BytesIO()
    _imagen_con_texto().save(salida, format="PNG")
    return salida.getvalue()


def pdf_escaneado() -> bytes:
    """PDF sin capa de texto: una imagen de página, como sale de un escáner."""
    salida = io.BytesIO()
    _imagen_con_texto().convert("RGB").save(salida, format="PDF", resolution=150)
    return salida.getvalue()


def pdf_danado() -> bytes:
    return b"%PDF-1.4\n1 0 obj << /Type /Catalog basura sin terminar"


def desconocido() -> bytes:
    """Bytes sin ninguna firma conocida, con una extensión inventada."""
    return b"\x13\x37RICORA" + os.urandom(512)
