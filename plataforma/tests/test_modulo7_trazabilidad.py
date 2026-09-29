"""Módulo 7 · Trazabilidad (historia de usuario 7): cada propuesta y cada
decisión con fecha y responsable (RF-M7-01), historial completo y no solo
la última decisión (RF-M7-02), cada punto con qué cambió (antes → después),
«Ver estado en este punto» con la descripción completa de ese momento
(RF-M7-03) y exportación del historial como evidencia."""

import json

from django.urls import reverse
from django.utils import timezone

from ric import trazabilidad
from ric.models import EventoRiC, FormaDocumental, RegistroAuditoria, RelacionRiC

from ._ayudas import CasoModulos, candidato


class TrazabilidadTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()
        [p] = self.proponer(self.record, candidato())
        p.validar(self.archivista, aceptar=True)
        self.relacion = RelacionRiC.objects.get(relacion_id="R027")
        self.antes_de_corregir = timezone.now()
        self.client.force_login(self.revisor)
        self.client.post(reverse("revision_confirmar", args=[self.record.pk, self.relacion.pk]), {"nombre": "Cabildo de Santa Fe"})

    def test_propuesta_y_decisiones_con_fecha_y_responsable(self):
        puntos = trazabilidad.linea_de_tiempo(self.record)
        tipos = [p["tipo"] for p in puntos]
        self.assertIn(EventoRiC.Tipo.PROPUESTA_IA, tipos)
        self.assertIn(EventoRiC.Tipo.VALIDACION, tipos)
        for p in puntos:
            self.assertIsNotNone(p["fecha"])
            self.assertTrue(p["usuario"])  # RF-M7-01: sin excepción
        self.assertIn("revisor", [p["usuario"] for p in puntos])
        self.assertIn("ia", [p["actor"] for p in puntos])

    def test_cada_punto_dice_que_cambio_antes_y_despues(self):
        puntos = trazabilidad.linea_de_tiempo(self.record)
        cambios = [c for p in puntos for c in p["cambios"]]
        self.assertTrue(any(c["antes"] == "Cabildo de Santafé" and c["despues"] == "Cabildo de Santa Fe" for c in cambios))
        resp = self.client.get(reverse("historial", args=[self.record.pk]))
        self.assertContains(resp, "Valor anterior")
        self.assertContains(resp, '<td class="antes">Cabildo de Santafé</td>')
        self.assertContains(resp, '<td class="despues">Cabildo de Santa Fe</td>')

    def test_historial_completo_no_solo_la_ultima_decision(self):
        self.client.post(reverse("revision_rechazar", args=[self.record.pk, self.relacion.pk]), {"motivo": "No es el productor."})
        puntos = trazabilidad.linea_de_tiempo(self.record)
        textos = json.dumps([p["datos"] + p["cambios"] for p in puntos], ensure_ascii=False)
        self.assertIn("Cabildo de Santa Fe", textos)  # la corrección sigue ahí
        self.assertIn("No es el productor.", textos)  # y el rechazo posterior también

    def test_ver_estado_en_un_punto_anterior_reconstruye_la_descripcion_completa(self):
        # antes de la revisión el nombre era el original y la ficha estaba pendiente de revisión
        estado = trazabilidad.descripcion_en(self.record, self.antes_de_corregir)
        self.assertEqual(estado["nombre"], "Acta")
        [fila] = estado["relaciones"]
        self.assertEqual(fila["entidad"], "Cabildo de Santafé")
        self.assertEqual(fila["revision"], "pendiente")
        # y el estado actual refleja la corrección
        [actual] = trazabilidad.descripcion_en(self.record, timezone.now())["relaciones"]
        self.assertEqual(actual["entidad"], "Cabildo de Santa Fe")
        self.assertEqual(actual["revision"], "corregida")

    def test_relacion_retirada_despues_sigue_en_el_estado_de_antes(self):
        momento = timezone.now()
        self.relacion.eliminar(self.archivista, motivo="prueba")
        self.assertEqual(len(trazabilidad.descripcion_en(self.record, momento)["relaciones"]), 1)
        self.assertEqual(len(trazabilidad.descripcion_en(self.record, timezone.now())["relaciones"]), 0)

    def test_pantalla_ver_estado_en_este_punto(self):
        resp = self.client.get(reverse("historial", args=[self.record.pk]), {"momento": self.antes_de_corregir.isoformat()})
        self.assertContains(resp, "solo lectura")
        self.assertContains(resp, "<strong>Cabildo de Santafé</strong>")
        self.assertContains(resp, "Ver estado en este punto")

    def test_eleccion_de_forma_documental_queda_en_la_bitacora(self):
        forma = FormaDocumental.objects.create(nombre="Acta")
        self.client.force_login(self.archivista)
        self.client.post(reverse("analisis_forma", args=[self.record.pk]), {"forma_id": forma.pk})
        self.assertTrue(EventoRiC.objects.filter(instanciacion=self.inst, detalle__forma_documental="Acta", agente="archivista").exists())

    def test_exportar_historial_csv_y_json_y_queda_auditado(self):
        resp = self.client.get(reverse("historial_exportar", args=[self.record.pk]), {"formato": "csv"})
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(f'historial-documento-{self.record.pk}.csv', resp["Content-Disposition"])
        texto = resp.content.decode("utf-8-sig")
        self.assertIn("cadena íntegra", texto)
        self.assertIn("Cabildo de Santafé", texto)
        resp = self.client.get(reverse("historial_exportar", args=[self.record.pk]), {"formato": "json"})
        datos = json.loads(resp.content)
        self.assertTrue(datos["cadena_de_eventos_integra"])
        self.assertTrue(any(e["hash_evento"] for e in datos["eventos"]))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="consultar", object_id=self.record.pk, detalle__has_key="exportacion_historial").count(), 2)

    def test_ver_historial_desde_la_ficha_del_catalogo(self):
        resp = self.client.get(reverse("catalogo_ficha", args=["record", self.record.pk]))
        self.assertContains(resp, reverse("historial", args=[self.record.pk]))

    def test_consulta_no_ve_el_historial(self):
        self.client.force_login(self.consulta)
        self.assertEqual(self.client.get(reverse("historial_exportar", args=[self.record.pk])).status_code, 302)
