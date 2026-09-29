"""Valoración y disposición: retención heredada de la TRD por cada
expediente, fases, transferencias e inventario FUID."""

import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ric import clasificacion, instrumentos, valoracion
from ric.models import Activity, RecordSet

from ._ayudas import CasoModulos
from .test_m1_ingesta import ORGANIGRAMA, TRD


class ValoracionTest(CasoModulos):
    def setUp(self):
        super().setUp()
        instrumentos.importar_organigrama(ORGANIGRAMA, self.archivista)
        instrumentos.importar_trd(TRD, self.archivista)
        self.serie = Activity.objects.get(identificador="TRD 1000-24")  # gestión 3, central 7, S
        self.actas = Activity.objects.get(identificador="TRD 4106-10")  # gestión 2, central 18, CT

    def _expediente(self, serie, nombre, cierre=None, apertura=None):
        e, _ = clasificacion.crear_expediente(serie, nombre, self.archivista, fecha_apertura=apertura)
        e.fecha_cierre = cierre
        e.save()
        clasificacion.registrar_documentos(e, [SimpleUploadedFile(f"{nombre}.txt", b"texto")], self.archivista)
        return e

    def test_fases_calculadas_desde_el_cierre_y_la_trd(self):
        hoy = datetime.date(2026, 9, 29)
        abierto = self._expediente(self.serie, "Abierto")
        gestion = self._expediente(self.serie, "En gestión", cierre=datetime.date(2025, 1, 15))
        central = self._expediente(self.serie, "En central", cierre=datetime.date(2022, 1, 15))
        vencido = self._expediente(self.serie, "Vencido", cierre=datetime.date(2010, 1, 15))
        self.assertEqual(valoracion.resumen(abierto, hoy)["fase"], valoracion.ABIERTO)
        r = valoracion.resumen(gestion, hoy)
        self.assertEqual(r["fase"], valoracion.GESTION)
        self.assertEqual(r["fin_gestion"], datetime.date(2028, 1, 15))
        self.assertEqual(r["fin_central"], datetime.date(2035, 1, 15))
        self.assertFalse(r["pronto"])
        r = valoracion.resumen(central, hoy)
        self.assertEqual(r["fase"], valoracion.CENTRAL)
        self.assertEqual(r["fin_gestion"], datetime.date(2025, 1, 15))
        r = valoracion.resumen(vencido, hoy)
        self.assertEqual(r["fase"], valoracion.DISPOSICION)
        self.assertEqual(r["disposicion"], "Selección")
        self.assertEqual(r["documentos"], 1)
        # por vencer dentro del aviso
        pronto = self._expediente(self.serie, "Pronto", cierre=datetime.date(2023, 10, 20))
        r = valoracion.resumen(pronto, hoy)
        self.assertEqual(r["fase"], valoracion.GESTION)
        self.assertTrue(r["pronto"])
        self.assertEqual(r["dias"], 21)

    def test_listas_de_transferencia_y_disposicion(self):
        hoy = datetime.date(2026, 9, 29)
        self._expediente(self.serie, "En central", cierre=datetime.date(2022, 1, 15))
        self._expediente(self.actas, "Acta vieja", cierre=datetime.date(2000, 1, 15))
        self._expediente(self.serie, "Reciente", cierre=datetime.date(2026, 1, 15))
        listas = valoracion.transferencias(hoy)
        self.assertEqual([r["expediente"].nombre for r in listas["primaria"]], ["En central"])
        self.assertEqual([r["expediente"].nombre for r in listas["disposicion"]], ["Acta vieja"])
        self.assertEqual(listas["disposicion"][0]["codigos"], ["CT"])
        self.assertEqual(valoracion.conteo_vencidos(hoy), 2)

    def test_pantallas_y_edicion_de_fechas(self):
        e = self._expediente(self.serie, "Petición 12", apertura=datetime.date(2026, 2, 1))
        self.client.force_login(self.revisor)
        resp = self.client.get(reverse("valoracion"))
        self.assertContains(resp, "Petición 12")
        self.assertContains(resp, "Abierto (sin fecha de cierre)")
        self.assertContains(resp, "gestión 3 años · central 7 años · Selección")
        self.assertNotContains(resp, 'name="fecha_cierre"')  # el revisor no edita
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("valoracion_expediente", args=[e.pk]), {"fecha_apertura": "2026-02-01", "fecha_cierre": "2026-06-30"}, follow=True)
        self.assertContains(resp, "En archivo de gestión")
        e.refresh_from_db()
        self.assertEqual(str(e.fecha_cierre), "2026-06-30")
        resp = self.client.post(reverse("valoracion_expediente", args=[e.pk]), {"fecha_apertura": "2026-02-01", "fecha_cierre": "2025-01-01"}, follow=True)
        self.assertContains(resp, "no puede ser anterior")
        resp = self.client.get(reverse("valoracion_transferencias"))
        self.assertContains(resp, "Transferencia primaria (0)")
        self.client.force_login(self.consulta)
        self.assertContains(self.client.get(reverse("valoracion"), follow=True), "Esta acción requiere")

    def test_inventario_fuid_en_csv(self):
        self._expediente(self.serie, "Petición 12", apertura=datetime.date(2026, 2, 1), cierre=datetime.date(2026, 6, 30))
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("valoracion_fuid"))
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        cuerpo = resp.content.decode("utf-8-sig")
        self.assertIn("Entidad productora;Unidad administrativa;Oficina productora", cuerpo)
        fila = cuerpo.splitlines()[1].split(";")
        self.assertEqual(fila[1], "Ministerio de Ambiente")
        self.assertEqual(fila[3], "Despacho del Ministro")
        self.assertEqual(fila[5], "Derechos de petición")
        self.assertEqual(fila[6], "Petición 12")
        self.assertEqual(fila[7:9], ["2026-02-01", "2026-06-30"])
        self.assertEqual(fila[13:16], ["3", "7", "Selección"])

    def test_ficha_del_documento_hereda_ruta_y_retencion_del_expediente(self):
        e = self._expediente(self.serie, "Petición 12", cierre=datetime.date(2026, 6, 30))
        from ric.models import Record
        record = Record.objects.get(record_set=e)
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("catalogo_ficha", args=["record", record.pk]))
        self.assertContains(resp, "Ministerio de Ambiente")
        self.assertContains(resp, "Derechos de petición")
        self.assertContains(resp, "Retención heredada")
        self.assertContains(resp, "gestión 3 años · central 7 años · Selección")
        resp = self.client.get(reverse("catalogo_ficha", args=["recordset", e.pk]))
        self.assertContains(resp, "Contenido (0 conjunto(s), 1 documento(s))")
        self.assertContains(resp, "En archivo de gestión")
