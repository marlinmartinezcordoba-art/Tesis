"""
Cierre del hallazgo PRE-08 de la auditoría RiC: la verificación periódica
de fijeza no se salta nada si el trabajador se reinicia a mitad de camino,
y avisa si se atrasa.
"""

from datetime import timedelta

from sqlalchemy import select

from app.db.base import ahora
from app.models.alerta import Alerta
from app.servicios import preservacion
from tests import archivos
from tests.test_preservacion import archivista, fondo, ingresar_archivo  # noqa: F401


def test_un_reinicio_a_mitad_de_pasada_no_salta_ningun_archivo(cliente, db, fondo, archivista):
    inst = [ingresar_archivo(cliente, db, archivista, fondo, f"d{i}.txt", archivos.txt(f"doc {i}")) for i in range(5)]
    # El trabajador alcanza a verificar dos y «se reinicia» (despliegue).
    assert preservacion.verificacion_periodica(db, lote=2) == 2
    # En la vuelta siguiente sigue con los que faltan, sin esperar 30 días.
    assert preservacion.verificacion_periodica(db, lote=2) == 2
    assert preservacion.verificacion_periodica(db, lote=2) == 1
    assert preservacion.verificacion_periodica(db, lote=2) is None
    for i in inst:
        db.refresh(i)
        assert i.ultima_verificacion_en is not None and i.estado_integridad == "integra"


def test_los_mas_viejos_se_verifican_primero(cliente, db, fondo, archivista):
    viejo = ingresar_archivo(cliente, db, archivista, fondo, "viejo.txt", archivos.txt("viejo"))
    nuevo = ingresar_archivo(cliente, db, archivista, fondo, "nuevo.txt", archivos.txt("nuevo"))
    viejo.ultima_verificacion_en = ahora() - timedelta(days=90)
    nuevo.ultima_verificacion_en = ahora() - timedelta(days=40)
    db.commit()
    assert preservacion.verificacion_periodica(db, lote=1) == 1
    db.refresh(viejo)
    db.refresh(nuevo)
    assert viejo.ultima_verificacion_en > ahora() - timedelta(minutes=1)
    assert nuevo.ultima_verificacion_en < ahora() - timedelta(days=39)


def test_la_verificacion_atrasada_genera_alerta_y_se_resuelve_sola(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "a.txt", archivos.txt("a"))
    inst.ultima_verificacion_en = ahora() - timedelta(days=45)  # 30 días + 2 de margen superados
    db.commit()
    assert preservacion.revisar_atraso(db, 30) == 1
    alerta = db.scalar(select(Alerta).where(Alerta.tipo == "verificacion_atrasada", Alerta.atendida_en.is_(None)))
    assert alerta is not None and alerta.severidad == "alta"
    assert preservacion.verificacion_periodica(db) == 1
    assert preservacion.revisar_atraso(db, 30) == 0
    db.refresh(alerta)
    assert alerta.atendida_en is not None
