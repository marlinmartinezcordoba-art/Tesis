"""Módulo 2 · Preprocesamiento en segundo plano (Celery/Redis): estados del
trabajo, avance por página, cola sin duplicados, broker caído, trabajos
perdidos, reintento y permisos. Las tareas corren en modo inmediato
(CELERY_TASK_ALWAYS_EAGER, sin REDIS_URL) salvo donde se simula lo contrario."""

from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ric import cola, tasks
from ric.models import EventoRiC, Instantiation, PaginaTexto, Record, RegistroAuditoria

from ._ayudas import TEXTO, CasoModulos, ProveedorFalso, candidato
from .test_modulo1_ingesta import pdf_de_prueba

Estado = Instantiation.EstadoProceso


class CasoCola(CasoModulos):
    def cargado(self, nombre="acta.txt", contenido=None):
        record = Record.objects.create(nombre=nombre)
        contenido = contenido if contenido is not None else f"{TEXTO} {nombre}".encode()
        return Instantiation.objects.create(nombre=nombre, record_resource=record, archivo=SimpleUploadedFile(nombre, contenido))


class EstadosTest(CasoCola):
    def test_archivo_nuevo_queda_sin_enviar(self):
        inst = self.cargado()
        self.assertEqual(inst.estado_proceso, Estado.SIN_ENVIAR)
        self.assertEqual(inst.progreso, 0)

    def test_procesar_recorre_los_estados_y_termina_listo_con_mensaje(self):
        inst = self.cargado()
        vistos = []
        original = tasks._poner

        def espiar(inst_id, **campos):
            if "estado_proceso" in campos:
                vistos.append(campos["estado_proceso"])
            original(inst_id, **campos)

        with patch("ric.tasks._poner", side_effect=espiar):
            self.assertTrue(cola.encolar(inst, self.archivista))
        self.assertEqual(vistos, [Estado.PROCESANDO, Estado.LISTO])
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.LISTO)
        self.assertEqual(inst.progreso, 100)
        self.assertEqual(inst.intentos, 1)
        self.assertIsNotNone(inst.proceso_encolado)
        self.assertIsNotNone(inst.proceso_iniciado)
        self.assertIsNotNone(inst.proceso_terminado)
        self.assertIn("Preprocesado: 1 página(s)", inst.mensaje_proceso)
        self.assertEqual(inst.resultado_proceso["paginas"], 1)

    def test_avance_por_pagina_en_un_pdf(self):
        inst = self.cargado("oficio.pdf", pdf_de_prueba(3))
        etapas = []
        original = tasks._poner

        def espiar(inst_id, **campos):
            if "etapa" in campos:
                etapas.append((campos.get("progreso"), campos["etapa"]))
            original(inst_id, **campos)

        with patch("ric.tasks._poner", side_effect=espiar):
            cola.encolar(inst, self.archivista)
        textos = [e for _p, e in etapas]
        for n in (1, 2, 3):
            self.assertIn(f"Leyendo página {n} de 3", textos)
        progresos = [p for p, _e in etapas if p is not None]
        self.assertEqual(progresos, sorted(progresos))  # la barra nunca retrocede
        self.assertEqual(Instantiation.objects.get(pk=inst.pk).paginas.count(), 3)

    def test_calidad_baja_queda_marcada_y_no_va_al_motor(self):
        inst = self.cargado()

        def ocr_malo(instanciacion, agente="sistema", al_avanzar=None):
            PaginaTexto.objects.create(instanciacion=instanciacion, numero=1, texto=TEXTO, uso_ocr=True, confianza_ocr=20.0)
            return None, {"paginas": 1, "caracteres": len(TEXTO), "confianza_ocr": 20.0}

        with patch("ric.extraccion.extraer_texto_de_instanciacion", side_effect=ocr_malo), \
                patch("ric.motor.enviar_al_motor") as motor:
            cola.encolar(inst, self.archivista)
        motor.assert_not_called()
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.CALIDAD_BAJA)
        self.assertIn("calidad de lectura baja", inst.mensaje_proceso)


class ErroresTest(CasoCola):
    def test_una_falla_deja_error_explicado_evento_fallido_y_el_original_intacto(self):
        inst = self.cargado()
        huella = inst.sha256
        with patch("ric.ingesta.ingerir", side_effect=RuntimeError("Tesseract no respondió")):
            cola.encolar(inst, self.archivista)
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.ERROR)
        self.assertIn("Tesseract no respondió", inst.mensaje_proceso)
        self.assertIn("puede reintentar", inst.mensaje_proceso)
        self.assertEqual(inst.sha256, huella)
        self.assertTrue(EventoRiC.objects.filter(instanciacion=inst, tipo=EventoRiC.Tipo.EXTRACCION, exitoso=False).exists())

    def test_tiempo_limite_superado(self):
        from celery.exceptions import SoftTimeLimitExceeded

        inst = self.cargado()
        with patch("ric.ingesta.ingerir", side_effect=SoftTimeLimitExceeded()):
            cola.encolar(inst, self.archivista)
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.ERROR)
        self.assertIn("tiempo máximo", inst.mensaje_proceso)

    def test_broker_caido_no_deja_el_archivo_en_cola_para_siempre(self):
        inst = self.cargado()
        with patch("ric.tasks.preprocesar_instanciacion.delay", side_effect=ConnectionError("redis caído")):
            with self.assertRaises(cola.ColaNoDisponible):
                cola.encolar(inst, self.archivista)
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.ERROR)
        self.assertIn("no está disponible", inst.mensaje_proceso)

    def test_broker_caido_desde_la_pantalla_avisa_sin_error_500(self):
        inst = self.cargado()
        self.client.force_login(self.archivista)
        with patch("ric.tasks.preprocesar_instanciacion.delay", side_effect=ConnectionError("redis caído")):
            resp = self.client.post(reverse("preproceso_enviar"), {"instanciacion": [inst.pk]}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "La cola de procesamiento no está disponible")
        self.assertContains(resp, "Reintentar")

    def test_reintentar_tras_error_procesa_de_nuevo(self):
        inst = self.cargado()
        with patch("ric.ingesta.ingerir", side_effect=RuntimeError("falla")):
            cola.encolar(inst, self.archivista)
        inst.refresh_from_db()
        self.assertTrue(cola.encolar(inst, self.archivista))
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.LISTO)
        self.assertEqual(inst.intentos, 2)


class ColaSinDuplicadosTest(CasoCola):
    def test_no_se_encola_dos_veces_un_trabajo_vivo(self):
        inst = self.cargado()
        Instantiation.objects.filter(pk=inst.pk).update(estado_proceso=Estado.EN_COLA, proceso_encolado=timezone.now())
        inst.refresh_from_db()
        with patch("ric.tasks.preprocesar_instanciacion.delay") as delay:
            self.assertFalse(cola.encolar(inst, self.archivista))
        delay.assert_not_called()

    def test_trabajo_perdido_se_puede_reintentar(self):
        inst = self.cargado()
        viejo = timezone.now() - timedelta(hours=2)
        Instantiation.objects.filter(pk=inst.pk).update(estado_proceso=Estado.PROCESANDO, proceso_encolado=viejo, proceso_iniciado=viejo)
        inst.refresh_from_db()
        self.assertTrue(cola.perdido(inst))
        self.assertTrue(cola.encolar(inst, self.archivista))
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.LISTO)

    def test_trabajo_reemplazado_por_un_reintento_se_descarta(self):
        inst = self.cargado()
        Instantiation.objects.filter(pk=inst.pk).update(intentos=3)
        tasks.preprocesar_instanciacion(inst.pk, self.archivista.pk, 2)  # entrega vieja del broker
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.SIN_ENVIAR)
        self.assertEqual(inst.paginas.count(), 0)

    def test_el_envio_queda_en_la_auditoria(self):
        inst = self.cargado()
        cola.encolar(inst, self.archivista)
        registro = RegistroAuditoria.objects.filter(accion="modificar", object_id=inst.pk, usuario=self.archivista).last()
        self.assertIsNotNone(registro)
        self.assertEqual(registro.detalle["cola"], "preprocesar")


class PantallaTest(CasoCola):
    def test_enviar_varios_vuelve_de_inmediato_y_avisa(self):
        a, b = self.cargado("a.txt"), self.cargado("b.txt")
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("preproceso_enviar"), {"instanciacion": [a.pk, b.pk]}, follow=True)
        self.assertContains(resp, "2 archivo(s) enviados a preprocesamiento")
        self.assertEqual(Instantiation.objects.filter(estado_proceso=Estado.LISTO).count(), 2)

    def test_estado_json_para_la_barra_de_avance(self):
        inst = self.cargado()
        Instantiation.objects.filter(pk=inst.pk).update(
            estado_proceso=Estado.PROCESANDO, progreso=45, etapa="Leyendo página 9 de 20", proceso_iniciado=timezone.now())
        self.client.force_login(self.archivista)
        datos = self.client.get(reverse("preproceso_estado"), {"ids": str(inst.pk)}).json()
        fila = datos["archivos"][0]
        self.assertEqual((fila["estado"], fila["progreso"], fila["etapa"]), ("procesando", 45, "Leyendo página 9 de 20"))
        self.assertFalse(fila["reintentar"])
        self.assertEqual(datos["trabajadores"], 1)

    def test_listo_ofrece_ver_propuestas(self):
        inst = self.cargado()
        self.client.force_login(self.archivista)
        with patch("ric.proveedores.proveedor_activo", return_value=ProveedorFalso([candidato()])):
            self.client.post(reverse("preproceso_enviar"), {"instanciacion": [inst.pk]})
        fila = self.client.get(reverse("preproceso_estado"), {"ids": str(inst.pk)}).json()["archivos"][0]
        self.assertEqual(fila["accion"]["tipo"], "propuestas")
        self.assertEqual(fila["accion"]["url"], reverse("analisis", args=[inst.record_resource_id]))

    def test_estado_json_exige_rol_archivista(self):
        inst = self.cargado()
        self.client.force_login(self.revisor)
        resp = self.client.get(reverse("preproceso_estado"), {"ids": str(inst.pk)})
        self.assertEqual(resp.status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("preproceso_estado")).status_code, 401)

    def test_revisor_no_puede_enviar_a_la_cola(self):
        inst = self.cargado()
        self.client.force_login(self.revisor)
        self.client.post(reverse("preproceso_enviar"), {"instanciacion": [inst.pk]})
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.SIN_ENVIAR)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_aviso_cuando_ningun_trabajador_responde(self):
        inst = self.cargado()
        Instantiation.objects.filter(pk=inst.pk).update(estado_proceso=Estado.EN_COLA, proceso_encolado=timezone.now())
        self.client.force_login(self.archivista)
        with patch("ric.cola.trabajadores_activos", return_value=0):
            resp = self.client.get(reverse("preproceso"))
        self.assertContains(resp, 'id="aviso-trabajador" >')
        self.assertContains(resp, "ningún trabajador de procesamiento está respondiendo")

    def test_aceptar_igual_envia_al_motor_por_la_cola(self):
        record, inst = self.documento()
        PaginaTexto.objects.filter(instanciacion=inst).update(uso_ocr=True, confianza_ocr=25.0)
        Instantiation.objects.filter(pk=inst.pk).update(estado_proceso=Estado.CALIDAD_BAJA)
        self.client.force_login(self.archivista)
        with patch("ric.proveedores.proveedor_activo", return_value=ProveedorFalso([candidato()])):
            self.client.post(reverse("preproceso_pagina_decidir", args=[inst.pk, 1]), {"decision": "aceptar"})
        inst.refresh_from_db()
        self.assertEqual(inst.estado_proceso, Estado.LISTO)
        self.assertIn("1 propuesta", inst.mensaje_proceso)
        self.assertEqual(inst.resultado_proceso["analisis"]["propuestas"], 1)
