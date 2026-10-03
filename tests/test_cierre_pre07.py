"""
Cierre (parcial, ver la acción en el panel) del hallazgo PRE-07: la
segunda copia gana una referencia independiente de la base de datos y la
web deja de poder escribir en ella.
"""

from sqlalchemy import select

from app.core.config import settings
from app.models.alerta import Alerta
from app.models.preservacion import SegundaCopia
from app.servicios import preservacion, segunda_copia
from tests import archivos
from tests.test_preservacion import archivista, fondo, ingresar_archivo  # noqa: F401


def test_cada_copia_queda_en_un_manifiesto_de_solo_anexar_fuera_de_la_base(cliente, db, fondo, archivista):
    a = ingresar_archivo(cliente, db, archivista, fondo, "a.txt", archivos.txt("uno"))
    b = ingresar_archivo(cliente, db, archivista, fondo, "b.txt", archivos.txt("dos"))
    raiz = segunda_copia.ubicacion_actual(db)
    manifiesto = segunda_copia._manifiesto(raiz, fondo.id)
    lineas = manifiesto.read_text().splitlines()
    assert any(l.startswith(a.huella) and str(a.id) in l for l in lineas)
    assert any(l.startswith(b.huella) and str(b.id) in l for l in lineas)
    assert segunda_copia.huella_de_manifiesto(a) == a.huella


def test_si_cambia_la_huella_de_la_base_el_manifiesto_lo_delata(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "a.txt", archivos.txt("uno"))
    original = inst.huella
    inst.huella = "0" * 64  # alguien alteró la referencia en la base, no el archivo
    db.commit()
    preservacion.verificar(db, inst, origen="manual")
    alerta = db.scalar(select(Alerta).where(Alerta.tipo == "huella_referencia_alterada", Alerta.atendida_en.is_(None)))
    assert alerta is not None and "lo alterado es la base de datos" in alerta.mensaje
    assert alerta.detalle["huella_manifiesto"] == original


def test_la_web_en_solo_lectura_no_escribe_y_el_trabajador_repone(cliente, db, fondo, archivista, monkeypatch):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "a.txt", archivos.txt("uno"))
    danada = segunda_copia.vigente(db, inst.id)
    monkeypatch.setattr(settings, "segunda_copia_solo_lectura", True)
    r = cliente.post(f"/api/preservacion/instanciacion/{inst.id}/segunda-copia/reponer", headers=archivista,
                     json={"aprobada": True})
    assert r.status_code == 200
    db.refresh(danada)
    assert danada.estado == "reemplazada"  # apartada, no borrada
    assert segunda_copia.ruta_absoluta(danada).exists()
    assert segunda_copia.vigente(db, inst.id) is None
    # La web no puede crearla ni por descuido.
    assert segunda_copia.asegurar(db, inst, "pendiente") is None
    # El trabajador (sin solo lectura) la crea en su vuelta.
    monkeypatch.setattr(settings, "segunda_copia_solo_lectura", False)
    assert preservacion.replicar_pendientes(db) >= 1
    nueva = segunda_copia.vigente(db, inst.id)
    assert nueva is not None and nueva.id != danada.id and nueva.estado == "sincronizada"
    assert len(db.scalars(select(SegundaCopia).where(SegundaCopia.instanciacion_id == inst.id)).all()) == 2
