"""
El panel de hallazgos refleja la auditoría de conformidad RiC: los 69
hallazgos no conformes entran con su identificador y los cierres se
aplican con fecha, acción y pruebas que existen de verdad.
"""

import ast
from pathlib import Path

from sqlalchemy import select

from app.models.auditoria import RegistroAuditoria
from app.models.hallazgo import HallazgoConformidad
from app.servicios import cierre_auditoria

RAIZ = Path(__file__).resolve().parent.parent


def test_siembra_los_69_hallazgos_con_su_identificador_y_es_idempotente(db):
    primera = cierre_auditoria.sincronizar(db)
    assert primera["sembrados"] == 69
    assert cierre_auditoria.sincronizar(db) == {"sembrados": 0, "cerrados": 0}
    filas = db.scalars(select(HallazgoConformidad).where(HallazgoConformidad.referencia.is_not(None))).all()
    assert len(filas) == 69 and len({h.numero for h in filas}) == 69
    ins02 = next(h for h in filas if h.referencia == "INS-02")
    assert ins02.titulo.startswith("INS-02 · ") and "Ley 1712" in ins02.descripcion


def test_los_cierres_quedan_cerrados_con_fecha_accion_y_rastro(db):
    cierre_auditoria.sincronizar(db)
    for ref, c in cierre_auditoria.CIERRES.items():
        h = db.scalar(select(HallazgoConformidad).where(HallazgoConformidad.referencia == ref))
        if c.pendiente:  # lo que depende de infraestructura o de una decisión queda en corrección
            assert h.estado == "en_correccion" and h.cerrado_en is None and "Falta:" in h.accion, ref
        else:
            assert h.estado == "cerrado" and h.cerrado_en == c.fecha, ref
            assert h.accion.startswith(f"Corregido el {c.fecha.isoformat()}"), ref
        assert db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.entidad_id == str(h.id),
                                                         RegistroAuditoria.accion == "hallazgo_actualizado")), ref


def test_cada_cierre_cita_hallazgos_y_pruebas_que_existen():
    referencias = {x["referencia"] for x in cierre_auditoria.hallazgos_auditoria()}
    for ref, c in cierre_auditoria.CIERRES.items():
        assert ref in referencias, ref
        assert c.pruebas, f"{ref} se cerró sin prueba automatizada"
        for prueba in c.pruebas:
            archivo, funcion = prueba.split("::")
            if archivo.endswith((".ts", ".tsx")):  # prueba de la interfaz (vitest): it("…")
                assert f'it("{funcion}"' in (RAIZ / archivo).read_text(encoding="utf-8"), prueba
                continue
            arbol = ast.parse((RAIZ / archivo).read_text(encoding="utf-8"))
            assert funcion in {n.name for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)}, prueba
