"""
El mapeo a RiC-O se comprueba contra el archivo OWL oficial, no contra la
memoria de quien lo escribió: si un nombre no existe, o si el sistema lo
usa con una clase que su dominio o su rango no admiten, la prueba falla.
"""

from app.models.enums import CODIGO_RELACION_RIC
from app.servicios import ric_o


def test_todo_el_mapeo_es_conforme_al_owl_oficial():
    assert ric_o.verificar_contra_owl() == []


def test_cada_codigo_mapeado_existe_en_el_catalogo_del_sistema():
    faltan = [c for c in ric_o.PROPIEDADES if c not in CODIGO_RELACION_RIC]
    assert faltan == []


def test_la_verificacion_detecta_un_nombre_inventado(monkeypatch):
    falsa = dict(ric_o.PROPIEDADES)
    falsa["documents"] = ric_o.Propiedad("documentaActividad", "RiC-R033", ("Record",), ("Activity",), None)
    monkeypatch.setattr(ric_o, "PROPIEDADES", falsa)
    assert any("documentaActividad" in p for p in ric_o.verificar_contra_owl())


def test_la_verificacion_detecta_un_rango_que_no_corresponde(monkeypatch):
    # performsOrPerformed va de Agent a Activity; usarla hacia un Mandate es un error.
    falsa = dict(ric_o.PROPIEDADES)
    falsa["performs_or_performed"] = ric_o.Propiedad("performsOrPerformed", "RiC-R060i", ("Person",), ("Mandate",),
                                                     "isOrWasPerformedBy")
    monkeypatch.setattr(ric_o, "PROPIEDADES", falsa)
    assert any("no admite Mandate" in p for p in ric_o.verificar_contra_owl())


def test_parte_documental_es_record_part_y_se_une_por_constituyente():
    assert ric_o.clase_de("recurso_documental", nivel="parte_documental") == "RecordPart"
    assert ric_o.uso_valido("has_or_had_constituent", "Record", "RecordPart")
    # La inclusión de RiC-R024 no admite una parte documental como destino.
    assert not ric_o.uso_valido("includes_or_included", "RecordSet", "RecordPart")


def test_grupo_se_instancia_directamente():
    assert ric_o.clase_de("entidad_vocabulario", clase="agente", subtipo="grupo") == "Group"


def test_etiquetas_oficiales_en_espanol():
    assert ric_o.etiqueta_es("RecordPart") == "Componente documental"
    assert ric_o.etiqueta("has_or_had_holder") == "rico:hasOrHadHolder"


def test_ningun_nombre_rico_escrito_en_el_codigo_o_la_interfaz_es_ajeno_al_owl():
    """Hallazgo O-28: toda cadena «rico:X» que el sistema muestra (API, hojas
    de cálculo, interfaz, perfil SHACL) existe en el OWL oficial de RiC-O 1.1."""
    import re
    from pathlib import Path

    from rdflib import URIRef

    raiz = Path(__file__).resolve().parent.parent
    owl = ric_o._owl()
    definidos = {str(s).split("#")[-1] for s in owl.subjects() if isinstance(s, URIRef) and str(s).startswith(ric_o.RICO)}
    hallados = {}
    for carpeta, patrones in (("app", ("*.py", "*.ttl")), ("frontend/src", ("*.ts", "*.tsx"))):
        for patron in patrones:
            for archivo in (raiz / carpeta).rglob(patron):
                if "recursos/ric-o" in str(archivo):
                    continue
                for nombre in re.findall(r"rico:([A-Za-z][A-Za-z0-9]*)", archivo.read_text(encoding="utf-8")):
                    hallados.setdefault(nombre, str(archivo.relative_to(raiz)))
    ajenos = {n: a for n, a in hallados.items() if n not in definidos}
    assert len(hallados) > 30
    assert not ajenos, ajenos


def test_uri_de_la_forma_documental_es_la_del_owl():
    assert ric_o.uri("forma_documental") == "rico:hasDocumentaryFormType"
    assert ric_o.uri("has_successor") == "rico:hasSuccessor" and ric_o.uri_inversa("has_successor") == "rico:isSuccessorOf"
    assert ric_o.uri("no_existe") is None


def test_cada_codigo_del_catalogo_esta_mapeado_y_escrito_o_reservado_con_motivo():
    """Hallazgos CM-20 y O-33: ningún código del catálogo es un «nombre prestado» sin explicación."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent / "app"
    fuente = "".join(p.read_text(encoding="utf-8") for p in raiz.rglob("*.py")
                     if p.name not in ("enums.py", "ric_o.py"))
    for codigo in CODIGO_RELACION_RIC:
        if codigo in ric_o.PROPIEDADES:
            assert f'"{codigo}"' in fuente, f"{codigo} está mapeado pero ningún servicio lo escribe"
            assert codigo not in ric_o.CODIGOS_RESERVADOS, codigo
        else:
            assert len(ric_o.CODIGOS_RESERVADOS.get(codigo, "")) > 20, f"{codigo} sin mapeo ni motivo declarado"
    assert set(ric_o.CODIGOS_RESERVADOS) <= set(CODIGO_RELACION_RIC)


def test_el_perfil_de_cardinalidades_esta_escrito_y_documentado():
    """CM-21: cada restricción propia frente a RiC-O, con su razón, en el código y en el anexo."""
    from pathlib import Path

    anexo = (Path(__file__).resolve().parent.parent / "documentacion" / "anexos" / "verificacion-ric-o-1-1.md").read_text()
    for clave, (regla, razon) in ric_o.PERFIL_CARDINALIDAD.items():
        assert len(regla) > 10 and len(razon) > 20, clave
        assert regla in anexo, f"{clave} no está en el anexo de verificación"


def test_la_exportacion_no_escribe_nombres_rico_sueltos():
    """O-12: todo nombre de RiC-O que usa la exportación sale del mapeo único."""
    import re
    from pathlib import Path

    fuente = (Path(__file__).resolve().parent.parent / "app" / "servicios" / "exportacion_rico.py").read_text()
    assert not re.findall(r"\bRICO\.[A-Za-z]+", fuente)
