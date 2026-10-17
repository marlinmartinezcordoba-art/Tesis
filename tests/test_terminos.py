"""
Vocabulario único de relaciones (app/servicios/terminos.py).

Un solo nombre por relación en todo el sistema: el grafo, la descripción,
las fichas de autoridad, los instrumentos, la auditoría y la evaluación.
"""

from app.servicios import evaluacion_ric, ric_o, terminos
from app.servicios.autoridad import VINCULOS
from app.servicios.descripcion import RELACION_POR_ROL
from app.servicios.grafo import _arista
from app.servicios.instrumentos import ETIQUETA_RELACION


def test_cada_relacion_que_escribe_el_sistema_tiene_su_termino():
    for codigo in ric_o.PROPIEDADES:
        assert (codigo, None) in terminos.TERMINOS, codigo
    assert ("forma_documental", None) in terminos.TERMINOS
    for (tipo, rol), (codigo, _) in RELACION_POR_ROL.items():
        assert terminos.de(codigo, rol) is not None, (tipo, rol)
    # Los vínculos de autoridades con rol propio tienen su término exacto, no el general.
    for clave, v in VINCULOS.items():
        assert (v.codigo, v.rol) in terminos.TERMINOS, clave
    # Ningún término nombra una relación que el mapeo no conoce.
    for codigo, _ in terminos.TERMINOS:
        assert codigo == "forma_documental" or codigo in ric_o.PROPIEDADES, codigo


def test_un_termino_no_se_repite_para_dos_relaciones_distintas():
    nombres = [t.nombre for t in terminos.TERMINOS.values()]
    assert len(nombres) == len(set(nombres)), sorted(n for n in nombres if nombres.count(n) > 1)


def test_el_grafo_las_autoridades_los_instrumentos_y_la_evaluacion_usan_el_mismo_termino():
    assert ETIQUETA_RELACION["has_creator"] == terminos.directa("has_creator") == "producido por"
    assert _arista("a", "b", "has_addressee")["etiqueta"] == "dirigido a"
    assert VINCULOS["ejercida_por"].directa == terminos.directa("performs_or_performed")
    assert VINCULOS["progenitor_de"].inversa == "es hijo o hija de"
    assert evaluacion_ric.PAPEL["has_addressee"] == terminos.nombre("has_addressee") == "Destinatario"
    cat = {c["codigo"]: c for c in evaluacion_ric.catalogo()}
    assert cat["has_creator"]["papel"] == "Productor"
    # El rol precisa el término sin cambiar la propiedad de RiC-O.
    assert terminos.nombre("is_or_was_location_of", "expedicion") == "Lugar de expedición"
    assert terminos.nombre("has_or_had_subject", "mencionado") == "Mencionado"
    assert terminos.nombre("has_creator", "productor") == "Productor"  # sin término propio: el general


def test_las_copias_para_la_interfaz_y_la_documentacion_estan_al_dia():
    """Si falla: python -m app.cli terminos."""
    assert terminos.ARCHIVO_TS.read_text(encoding="utf-8") == terminos.generar_ts()
    assert terminos.ARCHIVO_MD.read_text(encoding="utf-8") == terminos.generar_md()
    assert "| Destinatario | — | dirigido a | destinatario de | rico:hasAddressee | RiC-R032 | se dirige a |" \
        in terminos.generar_md()
