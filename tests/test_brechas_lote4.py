"""
Cierre de brechas, lote 4 · Búsqueda (RF-SEARCH-001 y RF-SEARCH-002).

- RF-SEARCH-001: una palabra que solo está en el OCR, un código de
  referencia y un identificador VIAF devuelven los registros correctos; sin
  importar tildes, mayúsculas ni plurales.
- RF-SEARCH-002: el perfil de consulta no encuentra nada reservado ni
  clasificado (propio o heredado, de la descripción o del archivo), ni en
  los resultados, ni en los fragmentos, ni en los conteos, ni en las
  autoridades que solo citan lo reservado.
"""

import json
import uuid

import pytest
from sqlalchemy import select, text

from app.models.descripcion import IdentificadorEntidad
from app.models.instanciacion import Instanciacion
from app.models.preservacion import DeclaracionDerechos
from tests.test_grafo_contexto import consulta  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401

PALABRA_OCR = "Cuervo"  # solo aparece en el texto del oficio 114, no en su descripción


@pytest.fixture()
def fondo(db, fondo_descrito, admin):  # noqa: F811
    f = fondo_descrito
    inst = db.scalar(select(Instanciacion).where(Instanciacion.nombre_original == "Oficio_114_1948.pdf"))
    inst.texto_extraido = ("Señor Gobernador: el inspector de policía Rafael Cuervo informa que los legajos del "
                           "archivo municipal sufrieron humedad durante las lluvias de marzo.")
    db.add(IdentificadorEntidad(entidad_id=f["alcaldia"].id, esquema="viaf", valor="123456789"))
    db.commit()
    f["inst"] = inst
    return f


def _buscar(cliente, quien, q, **params):
    r = cliente.get("/api/buscar", headers=quien, params={"q": q, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _titulos(datos):
    return [d["titulo"] for d in datos["documentos"]]


def _reservar(db, f, entidad_tipo, entidad_id, acceso="reservado"):
    from app.models.usuario import Usuario

    admin = db.scalar(select(Usuario).where(Usuario.rol == "administrador"))
    db.add(DeclaracionDerechos(creada_por_id=admin.id, fondo_id=f["fondo"].id, entidad_tipo=entidad_tipo, entidad_id=entidad_id,
                               base="estatuto", acceso=acceso, reproduccion="no_permitida",
                               fundamento="Ley 1712 de 2014, art. 19"))
    db.commit()


# --- RF-SEARCH-001 -------------------------------------------------------------------------------


def test_una_palabra_que_solo_esta_en_el_ocr_encuentra_el_documento(cliente, fondo, archivista):  # noqa: F811
    d = _buscar(cliente, archivista, PALABRA_OCR.lower())
    assert _titulos(d) == ["Oficio N.º 114"]
    doc = d["documentos"][0]
    assert doc["motivos"] == ["texto del documento"]
    assert "⟦Cuervo⟧" in doc["fragmento"]  # resaltado con las mayúsculas originales
    assert doc["ruta"] == ["Correspondencia", "Correspondencia 1948"] and doc["fechas"] == "1948-03-15"


def test_sin_tildes_ni_plurales_y_con_frases(cliente, fondo, archivista):  # noqa: F811
    # «policia» sin tilde y en otra forma: «policías».
    assert _titulos(_buscar(cliente, archivista, "policias")) == ["Oficio N.º 114"]
    # «alcaldias» encuentra la serie (alcance: «…por la Alcaldía.») y la autoridad.
    d = _buscar(cliente, archivista, "alcaldias")
    assert "Correspondencia" in _titulos(d)
    assert [a["nombre"] for a in d["autoridades"]] == ["Alcaldía Municipal"]
    # Frase entre comillas: las palabras juntas y en ese orden.
    assert _titulos(_buscar(cliente, archivista, '"archivo municipal"', alcance="texto")) == ["Oficio N.º 114"]
    assert _buscar(cliente, archivista, '"municipal archivo"', alcance="texto")["total"] == 0


def test_codigo_de_referencia_completo_o_por_partes(cliente, fondo, archivista):  # noqa: F811
    d = _buscar(cliente, archivista, "co-am-115")
    assert _titulos(d)[0] == "Oficio N.º 115" and "código de referencia" in d["documentos"][0]["motivos"]
    assert set(_titulos(_buscar(cliente, archivista, "AM-11"))) >= {"Oficio N.º 114", "Oficio N.º 115"}


def test_identificador_viaf_encuentra_la_autoridad_y_los_documentos_que_la_citan(cliente, fondo, archivista):  # noqa: F811
    for q in ("123456789", "https://viaf.org/viaf/123456789"):
        d = _buscar(cliente, archivista, q)
        [autoridad] = d["autoridades"]
        assert autoridad["nombre"] == "Alcaldía Municipal" and autoridad["motivo"] == "identificador VIAF: 123456789"
        assert autoridad["documentos"] == 3
        assert set(_titulos(d)) == {"Oficio N.º 114", "Oficio N.º 115", "Correspondencia 1949"}
        assert all("cita Alcaldía Municipal" in x["motivos"] for x in d["documentos"])


def test_filtros_de_nivel_fechas_y_agente_con_sus_facetas(cliente, fondo, archivista):  # noqa: F811
    d = _buscar(cliente, archivista, "correspondencia")
    assert d["facetas"]["niveles"]["expediente"] == 2 and d["facetas"]["anios"] == [1948, 1949]
    assert set(_titulos(_buscar(cliente, archivista, "correspondencia", nivel="expediente"))) == {
        "Correspondencia 1948", "Correspondencia 1949"}
    assert _titulos(_buscar(cliente, archivista, "correspondencia", nivel="expediente", desde=1949)) == ["Correspondencia 1949"]
    agentes = _buscar(cliente, archivista, "oficio")["facetas"]["agentes"]
    gobernador = next(a for a in agentes if a["nombre"] == "Gobernador del Departamento")
    assert _titulos(_buscar(cliente, archivista, "oficio", agente_id=gobernador["id"])) == ["Oficio N.º 114"]


def test_validacion_y_sesion(cliente, fondo, archivista):  # noqa: F811
    assert cliente.get("/api/buscar", params={"q": "oficio"}).status_code == 401
    assert cliente.get("/api/buscar", headers=archivista, params={"q": "o"}).status_code == 422
    assert cliente.get("/api/buscar", headers=archivista, params={"q": "x" * 201}).status_code == 422
    # Solo palabras vacías («de la»): no falla, no encuentra nada por texto.
    assert _buscar(cliente, archivista, "de la", alcance="texto")["total"] == 0


def test_un_ocr_enorme_se_indexa_recortado_sin_detener_la_ingesta(db, fondo):
    """Más de 1 MB de índice no cabe en PostgreSQL: antes de este cambio, un
    OCR así habría hecho fallar la carga del archivo."""
    inst = fondo["inst"]
    db.execute(text("""UPDATE instanciaciones SET texto_extraido = (
                         SELECT string_agg(md5(i::text), ' ') FROM generate_series(1, 120000) i) || ' Cuervo'
                       WHERE id = :i"""), {"i": inst.id})
    tam = db.execute(text("SELECT length(texto_extraido), pg_column_size(busqueda) FROM instanciaciones WHERE id = :i"),
                     {"i": inst.id}).one()
    assert tam[0] > 3_900_000 and 0 < tam[1] < 1_048_576


# --- RF-SEARCH-002 -------------------------------------------------------------------------------


def test_consulta_no_encuentra_lo_reservado_ni_en_fragmentos_ni_en_conteos(cliente, db, fondo, archivista, consulta):  # noqa: F811
    """La reserva del expediente 1948 la heredan sus dos oficios."""
    _reservar(db, fondo, "recurso_documental", fondo["exp48"].id)
    reservados = {"Correspondencia 1948", "Oficio N.º 114", "Oficio N.º 115"}
    for q in (PALABRA_OCR, "co-am-115", "oficio", "correspondencia", "123456789", "gobernador", "humedad"):
        d = _buscar(cliente, consulta, q)
        crudo = json.dumps({k: v for k, v in d.items() if k != "q"}, ensure_ascii=False)  # sin el eco de lo buscado
        assert not reservados & set(_titulos(d)), q
        assert PALABRA_OCR not in crudo and "CO-AM-11" not in crudo and "Gobernador" not in crudo, q
        assert d["total"] == len(d["documentos"]) and d["alcance_reserva"] == "publico"
    # Los conteos solo cuentan lo visible: un expediente, ninguno de 1948.
    d = _buscar(cliente, consulta, "correspondencia")
    assert d["facetas"]["niveles"].get("expediente") == 1 and d["facetas"]["anios"] == [1949, 1949]
    # La Alcaldía sí es pública (la cita el expediente 1949), pero solo cuenta lo visible.
    [alcaldia] = _buscar(cliente, consulta, "123456789")["autoridades"]
    assert alcaldia["documentos"] == 1 and [e["titulo"] for e in alcaldia["ejemplos"]] == ["Correspondencia 1949"]
    # El equipo de archivo sí lo encuentra todo.
    assert "Correspondencia 1948" in _titulos(_buscar(cliente, archivista, "correspondencia"))
    assert {"Oficio N.º 114", "Oficio N.º 115"} <= set(_titulos(_buscar(cliente, archivista, "oficio")))
    assert _titulos(_buscar(cliente, archivista, PALABRA_OCR)) == ["Oficio N.º 114"]


def test_un_archivo_reservado_no_deja_buscar_su_texto_aunque_la_descripcion_sea_publica(
        cliente, db, fondo, archivista, consulta):  # noqa: F811
    _reservar(db, fondo, "instanciacion", fondo["inst"].id, acceso="clasificado")
    assert _buscar(cliente, consulta, PALABRA_OCR)["total"] == 0
    # La descripción sigue siendo pública y se encuentra por lo que dice ella.
    assert _titulos(_buscar(cliente, consulta, "co-am-114")) == ["Oficio N.º 114"]
    assert _titulos(_buscar(cliente, archivista, PALABRA_OCR)) == ["Oficio N.º 114"]


def test_borradores_y_archivos_sin_describir_solo_para_el_equipo_de_archivo(cliente, db, fondo, archivista, consulta):  # noqa: F811
    suelto = Instanciacion(id=uuid.uuid4(), fondo_id=fondo["fondo"].id, nombre_original="acta_1950.pdf", ruta="x/z.pdf",
                           tamano_bytes=10, estado="listo_para_descripcion", huella="b" * 64,
                           texto_extraido="Acta del concejo sobre el acueducto de Chiquinquirá.")
    db.add(suelto)
    db.commit()
    d = _buscar(cliente, archivista, "acueducto")
    assert [a["nombre"] for a in d["archivos_sin_describir"]] == ["acta_1950.pdf"]
    assert _buscar(cliente, consulta, "acueducto") == {**_buscar(cliente, consulta, "acueducto"),
                                                        "archivos_sin_describir": [], "total": 0}
    borrador = _buscar(cliente, archivista, "borrador")["documentos"]
    assert [(x["titulo"], x["borrador"]) for x in borrador] == [("Borrador", True)]
    assert _buscar(cliente, consulta, "borrador")["total"] == 0
