import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from acervo.models import Documento, EventoPreservacion, verificar_cadena
from asistencia.models import SugerenciaIA
from asistencia.proveedores import ProveedorReglas, generar_sugerencias
from lineamientos.verificacion import CUMPLE, NO_CUMPLE, evaluar_documento

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class FlujoAsistidoTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.archivista = User.objects.create_user("archivista", password="x")
        self.doc = Documento.objects.create(
            titulo="Carta del virrey",
            archivo=SimpleUploadedFile("carta.txt", b"contenido original"),
            texto_extraido="Santafe, 1781. Respuesta recibida en 1783.",
        )

    def resultado(self, codigo):
        return next(r for r in evaluar_documento(self.doc) if r.criterio.codigo == codigo)

    def test_ingreso_registra_hash_y_evento(self):
        self.assertEqual(len(self.doc.sha256), 64)
        self.assertEqual(self.doc.eventos.first().tipo, EventoPreservacion.Tipo.INGRESO)
        self.assertEqual(self.resultado("MET-01").estado, CUMPLE)

    def test_fijeza_detecta_alteracion_del_archivo(self):
        self.assertTrue(self.doc.verificar_fijeza())
        with open(self.doc.archivo.path, "wb") as f:
            f.write(b"contenido alterado")
        self.assertFalse(self.doc.verificar_fijeza())
        self.assertEqual(self.resultado("MET-01").estado, NO_CUMPLE)

    def test_bitacora_detecta_manipulacion(self):
        evento = self.doc.eventos.first()
        EventoPreservacion.objects.filter(pk=evento.pk).update(agente="otra persona")
        ok, roto = verificar_cadena(self.doc)
        self.assertFalse(ok)
        self.assertEqual(roto.pk, evento.pk)
        self.assertEqual(self.resultado("MET-02").estado, NO_CUMPLE)

    def test_sugerencia_no_modifica_documento_sin_validacion(self):
        [s] = generar_sugerencias(self.doc, ProveedorReglas())
        self.doc.refresh_from_db()
        self.assertEqual(s.valor_propuesto, "1781-1783")
        self.assertEqual(self.doc.fechas, "")
        self.assertEqual(self.resultado("DES-02").estado, NO_CUMPLE)

    def test_validacion_humana_aplica_cambio_y_queda_en_bitacora(self):
        [s] = generar_sugerencias(self.doc, ProveedorReglas())
        s.validar(self.archivista, aceptar=True, valor_final="1781-1784")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.fechas, "1781-1784")
        self.assertEqual(s.estado, SugerenciaIA.Estado.MODIFICADA)
        tipos = list(self.doc.eventos.values_list("tipo", flat=True))
        self.assertIn(EventoPreservacion.Tipo.VALIDACION, tipos)
        self.assertTrue(verificar_cadena(self.doc)[0])
        self.assertEqual(self.resultado("DES-02").estado, CUMPLE)

    def test_rechazo_exige_motivo(self):
        [s] = generar_sugerencias(self.doc, ProveedorReglas())
        with self.assertRaises(ValueError):
            s.validar(self.archivista, aceptar=False)
        s.validar(self.archivista, aceptar=False, motivo="Fecha de la copia, no del original")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.fechas, "")

    def test_informe_requiere_sesion_y_muestra_fuentes(self):
        url = f"/documentos/{self.doc.pk}/informe/"
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.archivista)
        r = self.client.get(url)
        self.assertContains(r, "ISO 14721")
        self.assertContains(r, "Revisión manual")
