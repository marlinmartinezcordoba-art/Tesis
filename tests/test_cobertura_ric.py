"""
Cobertura de RiC-CM 1.0 (documentacion/brechas-ric-lineamiento-completo.md): no es una
afirmación del documento, se mide desde el mapeo que usa la exportación, y no puede bajar.
Todo código que falta lleva su prioridad y su motivo.
"""

from app.servicios import cobertura_ric


def test_la_cobertura_de_ric_cm_es_total():
    m = cobertura_ric.medir()
    assert m["atributos"] == {"cubiertos": 42, "por_especializacion": 0, "total": 42}, m["atributos"]
    # 84 escritas y la procedencia orgánica (R026) por su especialización (hasCreator, hasAccumulator).
    assert m["relaciones"] == {"cubiertos": 84, "por_especializacion": 1, "total": 85}, m["relaciones"]


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
    # La procedencia orgánica la cubre su especialización (hasCreator), como pide RiC-O.
    assert "hasCreator" in por_codigo["R027"] and cobertura_ric.FALTANTES["R026"][0] == "especializada"
