"""Pruebas de la auditoría por muestreo de relaciones RiC (T071)."""

from django.contrib.auth.models import User
from django.test import TestCase

from ric.auditoria import MuestraRiC, reporte_exactitud, seleccionar_muestra
from ric.models import CorporateBody, Record, RelacionRiC


class SeleccionarMuestraTest(TestCase):
    def setUp(self):
        self.record = Record.objects.create(nombre="Acta")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")

    def test_solo_elige_relaciones_aceptadas_o_modificadas(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.PENDIENTE,
        )
        self.assertEqual(seleccionar_muestra(10), [])

    def test_elige_hasta_el_tamano_pedido_sin_repetir(self):
        for _ in range(3):
            record = Record.objects.create(nombre="Acta")
            RelacionRiC.objects.create(
                relacion_id="R027", origen=record, destino=self.cabildo,
                estado=RelacionRiC.Estado.ACEPTADA,
            )
        muestras = seleccionar_muestra(2)
        self.assertEqual(len(muestras), 2)
        self.assertEqual(MuestraRiC.objects.count(), 2)
        # una segunda selección no repite las ya elegidas
        segunda = seleccionar_muestra(10)
        self.assertEqual(len(segunda), 1)

    def test_filtra_por_relacion_id(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.ACEPTADA,
        )
        self.assertEqual(seleccionar_muestra(10, relacion_id="R001"), [])
        self.assertEqual(len(seleccionar_muestra(10, relacion_id="R027")), 1)


class RevisarMuestraTest(TestCase):
    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        record = Record.objects.create(nombre="Acta")
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        relacion = RelacionRiC.objects.create(
            relacion_id="R027", origen=record, destino=cabildo, estado=RelacionRiC.Estado.ACEPTADA,
        )
        self.muestra = MuestraRiC.objects.create(relacion=relacion)

    def test_revisar_correcta(self):
        self.muestra.revisar(self.archivista, MuestraRiC.Resultado.CORRECTA)
        self.muestra.refresh_from_db()
        self.assertEqual(self.muestra.resultado, MuestraRiC.Resultado.CORRECTA)
        self.assertEqual(self.muestra.revisado_por, self.archivista)

    def test_incorrecta_sin_observacion_falla(self):
        with self.assertRaises(ValueError):
            self.muestra.revisar(self.archivista, MuestraRiC.Resultado.INCORRECTA)

    def test_no_se_puede_revisar_dos_veces(self):
        self.muestra.revisar(self.archivista, MuestraRiC.Resultado.CORRECTA)
        with self.assertRaises(ValueError):
            self.muestra.revisar(self.archivista, MuestraRiC.Resultado.INCORRECTA, "algo")

    def test_requiere_usuario_autenticado(self):
        with self.assertRaises(PermissionError):
            self.muestra.revisar(None, MuestraRiC.Resultado.CORRECTA)


class ReporteExactitudTest(TestCase):
    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")

    def _muestra(self):
        relacion = RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo, estado=RelacionRiC.Estado.ACEPTADA,
        )
        return MuestraRiC.objects.create(relacion=relacion)

    def test_sin_muestras_revisadas_exactitud_es_none(self):
        self.assertEqual(reporte_exactitud(), {"total_revisadas": 0, "correctas": 0, "exactitud": None})

    def test_calcula_porcentaje_de_aciertos(self):
        self._muestra().revisar(self.archivista, MuestraRiC.Resultado.CORRECTA)
        self._muestra().revisar(self.archivista, MuestraRiC.Resultado.INCORRECTA, "mal")
        self._muestra()  # pendiente, no cuenta
        r = reporte_exactitud()
        self.assertEqual(r, {"total_revisadas": 2, "correctas": 1, "exactitud": 50.0})
