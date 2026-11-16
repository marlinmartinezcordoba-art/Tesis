"""La política de aprobación de la IA es configurable, auditable y en modo evaluación siempre «revisar_todo»."""

from sqlalchemy import select

from app.core.config import settings
from app.models.auditoria import RegistroAuditoria
from tests.test_vocabularios import archivista  # noqa: F401


def test_politica_configurable_y_auditada(cliente, db, cabeceras_admin, archivista, monkeypatch):  # noqa: F811
    r = cliente.get("/api/descripcion/politica-ia", headers=archivista)
    assert r.status_code == 200 and r.json()["politica"] == "alta_confianza"
    assert cliente.put("/api/descripcion/politica-ia", headers=archivista, json={"politica": "todo"}).status_code == 403
    r = cliente.put("/api/descripcion/politica-ia", headers=cabeceras_admin, json={"politica": "revisar_todo"})
    assert r.status_code == 200 and r.json()["politica"] == "revisar_todo"
    assert db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.entidad_id == "ia_politica_aceptacion")) is not None \
        or db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion.like("%parametro%")))
    assert cliente.put("/api/descripcion/politica-ia", headers=cabeceras_admin, json={"politica": "otra"}).status_code == 422
    monkeypatch.setattr(settings, "modo_evaluacion", True)
    cliente.put("/api/descripcion/politica-ia", headers=cabeceras_admin, json={"politica": "todo"})
    r = cliente.get("/api/descripcion/politica-ia", headers=archivista)
    assert r.json() == {"politica": "revisar_todo", "modo_evaluacion": True}
