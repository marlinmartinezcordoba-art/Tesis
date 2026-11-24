"""La norma citada como fundamento regula el documento (RiC-R063): al publicar y en los datos de antes."""

import importlib.util
import pathlib
import uuid

from sqlalchemy import select, text

from app.models.descripcion import EntidadVocabulario, Relacion
from app.servicios import descripcion
from tests.test_instrumentos import fondo_descrito  # noqa: F401


def test_la_migracion_convierte_lo_anterior_sin_borrar(db, fondo_descrito):  # noqa: F811
    f = fondo_descrito
    ley = EntidadVocabulario(id=uuid.uuid4(), fondo_id=f["fondo"].id, clase="mandato", subtipo="ley", nombre="Ley 1437 de 2011",
                             nombre_normalizado="ley 1437 de 2011", origen="persona", estado="activa")
    db.add(ley)
    db.flush()
    vieja = Relacion(origen_tipo="recurso_documental", origen_id=f["o114"].id, destino_tipo="entidad_vocabulario",
                     destino_id=ley.id, tipo_relacion="asociacion", codigo_ric="has_or_had_subject", rol="mandato",
                     origen="persona", fragmento="conforme a la Ley 1437 de 2011")
    db.add(vieja)
    db.commit()
    ruta = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / "0066_mandato_fundamento.py"
    spec = importlib.util.spec_from_file_location("m0066", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.op = type("Op", (), {"execute": staticmethod(lambda sql: db.execute(text(sql)))})
    m.upgrade()
    db.commit()
    db.refresh(vieja)
    assert vieja.estado == "anulada"
    [nueva] = db.scalars(select(Relacion).where(Relacion.origen_id == ley.id, Relacion.destino_id == f["o114"].id)).all()
    assert (nueva.codigo_ric, nueva.rol, nueva.estado) == ("regulates_or_regulated", "fundamento", "vigente")
    assert nueva.fragmento == "conforme a la Ley 1437 de 2011"
    assert descripcion.codigo_de_decision("mandato", {}) == "regulates_or_regulated"
