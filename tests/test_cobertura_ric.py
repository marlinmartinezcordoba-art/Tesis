"""
Cobertura de RiC-CM 1.0 (documentacion/brechas-ric-lineamiento-completo.md): no es una
afirmación del documento, se mide desde el mapeo que usa la exportación, y no puede bajar.
Todo código que falta lleva su prioridad y su motivo.
"""

from app.servicios import cobertura_ric


def test_la_cobertura_de_ric_cm_es_total():
    m = cobertura_ric.medir()
    assert m["atributos"] == {"cubiertos": 42, "por_especializacion": 0, "total": 42}, m["atributos"]
    # Las 85 relaciones que RiC-O 1.1 implementa (R043 no tiene término en el OWL oficial).
    assert m["relaciones"] == {"cubiertos": 85, "por_especializacion": 0, "total": 85}, m["relaciones"]
    assert set(cobertura_ric.NO_IMPLEMENTADAS_EN_RICO) == {"R043"}
    assert "R043" not in m["por_codigo"]


def test_el_catalogo_unico_tiene_toda_relacion_que_ric_o_implementa():
    """Cada código RiC-R que el OWL cita tiene su entrada en el catálogo de relaciones (ric_o.PROPIEDADES),
    con su nombre en español; las que no se guardan como fila se escriben al exportar con la propiedad
    del catálogo."""
    import re

    from app.servicios import ric_o, terminos

    en_catalogo = {c for p in ric_o.PROPIEDADES.values() for c in re.findall(r"R\d{3}", p.codigo_cm or "")}
    en_owl = {c for c in cobertura_ric._codigos() if c.startswith("R")}
    assert en_owl <= en_catalogo, sorted(en_owl - en_catalogo)
    assert len(en_catalogo) == 85
    for codigo, clave in cobertura_ric.ESCRITAS_AL_EXPORTAR.items():
        p = ric_o.PROPIEDADES[codigo]
        assert ric_o.APOYO[clave][0] in (p.rico, p.inversa), (codigo, clave)
        assert (codigo, None) in terminos.TERMINOS


def test_lo_que_falta_esta_declarado_con_su_prioridad_y_su_motivo():
    m = cobertura_ric.medir()
    sin_declarar = [f["codigo"] for f in m["faltantes"] if f["prioridad"] == "sin declarar"]
    assert not sin_declarar, sin_declarar
    assert all(len(f["motivo"]) > 20 for f in m["faltantes"])
    # Lo que ya se cubre no sigue declarado como faltante.
    cubiertos = {c for c, t in m["por_codigo"].items() if t}
    assert not cubiertos & set(cobertura_ric.FALTANTES), cubiertos & set(cobertura_ric.FALTANTES)


def test_la_fase_1_cubre_las_brechas_a():
    por_codigo = cobertura_ric.medir()["por_codigo"]
    for codigo in ("A04", "A07", "A17", "A24", "A27", "A37", "A39", "R011", "R013", "R021", "R061", "R064"):
        assert por_codigo[codigo], codigo
    # La procedencia orgánica general (R026) ya tiene su propiedad, para lo que no es creación ni acumulación.
    assert "hasCreator" in por_codigo["R027"] and "hasOrganicProvenance" in por_codigo["R026"]
