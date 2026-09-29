"""M2 · Preprocesamiento y OCR (/ingesta/preproceso): RF-M2-01 a RF-M2-04 y
la ruta alterna de calidad baja."""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ric.idioma import detectar_idioma
from ric.models import ConfiguracionSistema, EventoRiC, Instantiation, PaginaTexto, PropuestaRiC, Record

from ._ayudas import TEXTO, CasoModulos, ProveedorFalso, candidato


class DetectarIdiomaTest(CasoModulos):
    def test_espanol_ingles_y_texto_corto(self):
        self.assertEqual(detectar_idioma(TEXTO), "es")
        self.assertEqual(detectar_idioma("The council of the city met on the twentieth of July and the members agreed to the proposal."), "en")
        self.assertEqual(detectar_idioma("hola"), "")


class PreprocesoTest(CasoModulos):
    def _cargado(self, nombre="acta.txt", texto=TEXTO):
        record = Record.objects.create(nombre="Acta")
        return Instantiation.objects.create(nombre=nombre, record_resource=record, archivo=SimpleUploadedFile(nombre, texto.encode()))

    def test_solo_archivista(self):
        self.client.force_login(self.revisor)
        self.assertContains(self.client.get(reverse("preproceso"), follow=True), "requiere el rol archivista")

    def test_archivo_recien_cargado_aparece_sin_enviar(self):
        inst = self._cargado()
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("preproceso"))
        self.assertContains(resp, inst.nombre)
        self.assertContains(resp, "sin enviar")
        self.assertContains(resp, "Procesar (OCR)")

    def test_enviar_extrae_texto_detecta_idioma_y_avisa_que_falta_proveedor(self):
        inst = self._cargado()
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("preproceso_enviar"), {"instanciacion": [inst.pk]}, follow=True)
        inst.refresh_from_db()
        self.assertEqual(inst.paginas.count(), 1)  # RF-M2-02: texto nativo
        self.assertEqual(inst.idioma_detectado, "es")  # RF-M2-03
        self.assertEqual(inst.record_resource.idioma, "Español")
        self.assertTrue(EventoRiC.objects.filter(instanciacion=inst, tipo=EventoRiC.Tipo.EXTRACCION).exists())
        self.assertContains(resp, "listo")
        self.assertContains(resp, "no hay un proveedor de IA activo")
        self.assertContains(resp, "Enviar al motor de análisis")

    def test_con_proveedor_activo_entrega_automaticamente_al_motor_de_analisis(self):
        inst = self._cargado()
        self.client.force_login(self.archivista)
        with patch("ric.proveedores.proveedor_activo", return_value=ProveedorFalso([candidato()])):
            resp = self.client.post(reverse("preproceso_enviar"), {"instanciacion": [inst.pk]}, follow=True)
        self.assertEqual(PropuestaRiC.objects.filter(origen_object_id=inst.record_resource_id).count(), 1)
        self.assertContains(resp, "Enviado al motor de análisis: 1 propuesta")
        self.assertContains(resp, "Ver propuesta de entidades")
        self.assertContains(resp, reverse("analisis", args=[inst.record_resource_id]))

    def test_pagina_de_calidad_baja_queda_marcada_y_no_pasa_al_motor(self):
        record, inst = self.documento()
        PaginaTexto.objects.filter(instanciacion=inst).update(uso_ocr=True, confianza_ocr=25.0)
        Instantiation.objects.filter(pk=inst.pk).update(estado_proceso=Instantiation.EstadoProceso.LISTO)
        self.assertEqual(inst.paginas_calidad_baja().count(), 1)  # RF-M2-04
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("preproceso"))
        self.assertContains(resp, "calidad baja")
        self.assertContains(resp, reverse("preproceso_pagina", args=[inst.pk, 1]))

    def test_el_umbral_de_calidad_es_configurable(self):
        record, inst = self.documento()
        PaginaTexto.objects.filter(instanciacion=inst).update(uso_ocr=True, confianza_ocr=65.0)
        self.assertEqual(inst.paginas_calidad_baja().count(), 0)
        config = ConfiguracionSistema.actual()
        config.umbral_calidad_ocr = 70
        config.save()
        self.assertEqual(inst.paginas_calidad_baja().count(), 1)

    def test_visor_de_pagina_muestra_texto_confianza_y_botones(self):
        record, inst = self.documento()
        PaginaTexto.objects.filter(instanciacion=inst).update(uso_ocr=True, confianza_ocr=25.0)
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("preproceso_pagina", args=[inst.pk, 1]))
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertContains(resp, "25%")
        self.assertContains(resp, "Reescanear")
        self.assertContains(resp, "Aceptar igual")

    def test_aceptar_igual_deja_avanzar_y_envia_al_motor(self):
        record, inst = self.documento()
        PaginaTexto.objects.filter(instanciacion=inst).update(uso_ocr=True, confianza_ocr=25.0)
        self.client.force_login(self.archivista)
        with patch("ric.proveedores.proveedor_activo", return_value=ProveedorFalso([candidato()])):
            resp = self.client.post(reverse("preproceso_pagina_decidir", args=[inst.pk, 1]), {"decision": "aceptar"}, follow=True)
        pagina = inst.paginas.get(numero=1)
        self.assertIs(pagina.calidad_aceptada, True)
        self.assertEqual(inst.paginas_calidad_baja().count(), 0)
        self.assertContains(resp, "Enviado al motor de análisis: 1 propuesta")

    def test_reescanear_devuelve_la_pagina_a_ingesta_y_conserva_el_original(self):
        record, inst = self.documento()
        PaginaTexto.objects.filter(instanciacion=inst).update(uso_ocr=True, confianza_ocr=25.0)
        hash_original = inst.sha256
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("preproceso_pagina_decidir", args=[inst.pk, 1]), {"decision": "reescanear"})
        self.assertRedirects(resp, f"/ingesta/?reemplaza={inst.pk}", fetch_redirect_response=False)
        pagina = inst.paginas.get(numero=1)
        self.assertIs(pagina.calidad_aceptada, False)
        inst.refresh_from_db()
        self.assertEqual(inst.sha256, hash_original)
        self.assertTrue(Instantiation.objects.filter(pk=inst.pk).exists())
