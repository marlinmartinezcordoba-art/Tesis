"""Los instrumentos se cargan en el formato que tenga la entidad: OpenDocument, página web, RTF, texto tabulado."""

import io
import zipfile

import pytest

from app.servicios import cuadro

CABECERA = ["Código", "Serie", "Subserie"]
FILA = ["2103.31.03", "Instrumentos normativos", "Resoluciones"]


def _ods(tabla_xml: str) -> bytes:
    contenido = ('<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                 'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
                 f'<office:body><office:spreadsheet>{tabla_xml}</office:spreadsheet></office:body></office:document-content>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("content.xml", contenido)
    return b.getvalue()


def _fila_ods(celdas):
    return "<table:table-row>" + "".join(f"<table:table-cell><text:p>{c}</text:p></table:table-cell>" for c in celdas) \
        + '<table:table-cell table:number-columns-repeated="1000"/></table:table-row>'


def test_ods_odt():
    datos = _ods(f'<table:table table:name="TRD">{_fila_ods(CABECERA)}{_fila_ods(FILA)}</table:table>')
    assert cuadro._hojas(datos, "trd.ods") == [[CABECERA, FILA]]
    assert cuadro._hojas(datos, "trd.odt") == [[CABECERA, FILA]]


def test_html_rtf_y_texto_tabulado():
    html = "<html><body><p>TRD</p><table><tr><th>Código</th><th>Serie</th><th>Subserie</th></tr>" \
           "<tr><td>2103.31.03</td><td>Instrumentos normativos</td><td>Resoluciones</td></tr></table></body></html>"
    assert cuadro._hojas(html.encode(), "trd.html") == [[CABECERA, FILA]]
    rtf = r"{\rtf1\ansi C\'f3digo\cell Serie\cell Subserie\row 2103.31.03\cell Instrumentos normativos\cell Resoluciones\row}"
    assert cuadro._hojas(rtf.encode("latin-1"), "trd.rtf") == [[CABECERA, FILA]]
    tsv = "\t".join(CABECERA) + "\n" + "\t".join(FILA) + "\n"
    assert cuadro._hojas(tsv.encode(), "trd.txt") == [[CABECERA, FILA]]


def test_formato_antiguo_dice_que_hacer():
    with pytest.raises(cuadro.ErrorCuadro, match="guárdelo como"):
        cuadro._hojas(b"\xd0\xcf\x11\xe0", "trd.xls")
