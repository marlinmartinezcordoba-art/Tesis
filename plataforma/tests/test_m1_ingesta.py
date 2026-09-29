"""M1 · Ingesta de documentos (/ingesta): RF-M1-01 a RF-M1-04."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from ric.models import EventoRiC, Instantiation, Record

from ._ayudas import TEXTO, CasoModulos


class IngestaTest(CasoModulos):
    def _archivo(self, nombre="acta.txt", contenido=None):
        return SimpleUploadedFile(nombre, (contenido or TEXTO).encode())

    def test_requiere_sesion(self):
        self.assertEqual(self.client.get(reverse("ingesta")).status_code, 302)

    def test_solo_el_rol_archivista_ingesta(self):
        for usuario in (self.revisor, self.consulta):
            self.client.force_login(usuario)
            resp = self.client.get(reverse("ingesta"), follow=True)
            self.assertContains(resp, "requiere el rol archivista")
            self.assertNotContains(resp, "Arrastra archivos")

    def test_la_pantalla_muestra_la_zona_de_arrastre_y_los_expedientes(self):
        Record.objects.create(nombre="Expediente ya cargado")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ingesta"))
        self.assertContains(resp, "Arrastra archivos o selecciona una carpeta")
        self.assertContains(resp, "Expediente ya cargado")

    def test_cargar_calcula_la_huella_y_registra_usuario_fecha_y_hora(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("ingesta"), {"nombre_nuevo": "Acta del comité", "archivos": [self._archivo()]})
        self.assertEqual(resp.status_code, 200)
        inst = Instantiation.objects.get(record_resource__nombre="Acta del comité")
        self.assertEqual(len(inst.sha256), 64)  # RF-M1-02
        self.assertEqual(inst.formato, "txt")  # RF-M1-03
        self.assertEqual(inst.tamano_bytes, len(TEXTO.encode()))
        self.assertEqual(inst.creado_por, self.archivista)
        evento = EventoRiC.objects.get(instanciacion=inst, tipo=EventoRiC.Tipo.INGESTA)  # RF-M1-04
        self.assertEqual(evento.agente, "archivista")
        self.assertEqual(evento.detalle["sha256"], inst.sha256)
        self.assertContains(resp, "SHA-256 ✓")
        self.assertContains(resp, "Enviar a preprocesamiento")
        # la carga no extrae texto todavía: eso es el paso 2
        self.assertEqual(inst.paginas.count(), 0)

    def test_cargar_por_lote_a_un_expediente_existente(self):
        record = Record.objects.create(nombre="Lote")
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("ingesta"), {"record_id": record.pk, "archivos": [self._archivo("a.txt"), self._archivo("b.txt")]})
        self.assertEqual(Instantiation.objects.filter(record_resource=record).count(), 2)
        self.assertEqual(Record.objects.filter(nombre="Lote").count(), 1)
        self.assertContains(resp, "a.txt")
        self.assertContains(resp, "Enviar todos a preprocesamiento")

    def test_formato_no_soportado_se_rechaza_antes_de_guardar(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("ingesta"), {"nombre_nuevo": "Audio", "archivos": [self._archivo("nota.mp3", "ID3")]})
        self.assertContains(resp, "no soportado")
        self.assertFalse(Instantiation.objects.exists())
        self.assertFalse(Record.objects.filter(nombre="Audio").exists())

    @override_settings(RICORA_TAMANO_MAXIMO_MB=0)
    def test_archivo_demasiado_grande_se_rechaza(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("ingesta"), {"nombre_nuevo": "Grande", "archivos": [self._archivo()]})
        self.assertContains(resp, "el máximo es 0 MB")
        self.assertFalse(Instantiation.objects.exists())

    def test_sin_expediente_ni_archivo_avisa(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("ingesta"), {"archivos": [self._archivo()]})
        self.assertContains(resp, "Indique a qué expediente pertenece")
        resp = self.client.post(reverse("ingesta"), {"nombre_nuevo": "Algo"})
        self.assertContains(resp, "Seleccione al menos un archivo")
        self.assertFalse(Instantiation.objects.exists())

    def test_los_archivos_en_cola_siguen_visibles_al_volver(self):
        self.client.force_login(self.archivista)
        self.client.post(reverse("ingesta"), {"nombre_nuevo": "Acta", "archivos": [self._archivo("pendiente.txt")]})
        resp = self.client.get(reverse("ingesta"))
        self.assertContains(resp, "pendiente.txt")
        self.assertContains(resp, "en cola")

    def test_reescaneo_preselecciona_el_expediente(self):
        record, inst = self.documento()
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ingesta"), {"reemplaza": inst.pk})
        self.assertContains(resp, "Reescaneo pedido para")
        self.assertContains(resp, f'<option value="{record.pk}" selected')
