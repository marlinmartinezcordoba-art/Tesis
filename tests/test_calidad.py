"""Validación semántica y calidad: cada hallazgo dice qué afecta, el problema, la regla y la acción."""

from app.models.descripcion import Relacion
from tests.test_grafo_contexto import consulta  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def _calidad(cliente, quien, fondo):
    r = cliente.get(f"/api/fondos/{fondo.id}/calidad", headers=quien)
    assert r.status_code == 200, r.text
    return r.json()


def test_identificador_repetido_y_relacion_sin_evidencia(cliente, db, fondo_descrito, archivista):  # noqa: F811
    f = fondo_descrito
    f["o115"].codigo_referencia = f["o114"].codigo_referencia
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=f["o115"].id, destino_tipo="entidad_vocabulario",
                    destino_id=f["alcaldia"].id, tipo_relacion="asociacion", codigo_ric="has_or_had_subject",
                    origen="motor", confianza=0.5, motor="m"))
    db.commit()
    d = _calidad(cliente, archivista, f["fondo"])
    resumen = {x["tipo"]: x["total"] for x in d["resumen"]}
    assert resumen["identificador"] == 2 and resumen["sin_evidencia"] == 1
    h = next(x for x in d["hallazgos"] if x["tipo"] == "identificador")
    assert h["afectado"]["titulo"] in ("Oficio N.º 114", "Oficio N.º 115") and h["regla"] and h["accion"]
    assert {"problema", "regla", "accion", "enlace", "gravedad"} <= set(h)
    assert d["descripciones_revisadas"] >= 4 and d["relaciones_revisadas"] > 0


def test_solo_quien_describe_revisa_la_calidad(cliente, fondo_descrito, consulta):  # noqa: F811
    assert cliente.get(f"/api/fondos/{fondo_descrito['fondo'].id}/calidad", headers=consulta).status_code == 403
