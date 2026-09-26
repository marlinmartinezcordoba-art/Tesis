import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from acceso import detector
from acceso.models import RevisionDatosPersonales as Revision
from acceso.servicios import aprobar_publicacion, requisitos_publicacion, revisar_datos_personales
from acervo.extraccion import extraer_texto
from acervo.models import Documento, EventoPreservacion, verificar_cadena
from lineamientos.verificacion import CUMPLE, MANUAL, NO_CUMPLE, evaluar_documento

MEDIA = tempfile.mkdtemp()

TEXTO = (
    "Certifico que el señor Juan Pérez, identificado con C.C. No. 79.456.123, "
    "residente en la Calle 10 # 5-32 de Bogotá, teléfono 310 555 1234, "
    "correo jperez@ejemplo.com, presenta diagnóstico de enfermedad pulmonar."
)


class DetectorTest(TestCase):
    def test_detecta_identificacion_contacto_y_sensibles(self):
        tipos = {h.tipo for h in detector.detectar(TEXTO)}
        self.assertTrue({
            "Cédula o documento de identidad", "Dirección", "Teléfono celular",
            "Correo electrónico", "Salud",
        } <= tipos)

    def test_texto_historico_sin_datos_personales(self):
        self.assertEqual(detector.detectar("Acta del Cabildo de Santafé, 20 de julio de 1810."), [])

    def test_anonimizar_oculta_datos_pero_no_el_tema(self):
        hallazgos = [h.como_dict() for h in detector.detectar(TEXTO)]
        publico = detector.anonimizar(TEXTO, hallazgos)
        for dato in ("79.456.123", "310 555 1234", "jperez@ejemplo.com", "Calle 10 # 5-32"):
            self.assertNotIn(dato, publico)
        self.assertIn(detector.MARCA, publico)
        self.assertIn("diagnóstico", publico)


@override_settings(MEDIA_ROOT=MEDIA)
class FlujoPublicacionTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.archivista = User.objects.create_user("archivista", password="x")
        self.doc = Documento.objects.create(
            titulo="Certificado médico",
            codigo_referencia="CO.AGN.01.02.003",
            productor="Hospital San Juan de Dios",
            fechas="1998",
            volumen_soporte="1 folio, papel",
            archivo=SimpleUploadedFile("certificado.txt", TEXTO.encode()),
        )
        extraer_texto(self.doc)

    def criterio(self, codigo):
        return next(r for r in evaluar_documento(self.doc) if r.criterio.codigo == codigo)

    def test_no_se_publica_sin_revision_de_datos_personales(self):
        self.assertEqual(self.criterio("ACC-01").estado, MANUAL)
        ok, faltantes = aprobar_publicacion(self.doc, self.archivista)
        self.assertFalse(ok)
        self.assertIn("Falta la revisión de datos personales.", faltantes)

    def test_revision_pendiente_bloquea_publicacion(self):
        revision = revisar_datos_personales(self.doc)
        self.assertGreater(len(revision.hallazgos), 0)
        self.assertEqual(self.criterio("ACC-01").estado, NO_CUMPLE)
        self.assertFalse(aprobar_publicacion(self.doc, self.archivista)[0])

    def test_decision_exige_motivo(self):
        revision = revisar_datos_personales(self.doc)
        with self.assertRaises(ValueError):
            revision.decidir(self.archivista, Revision.Decision.ANONIMIZAR)
        with self.assertRaises(ValueError):
            revision.decidir(self.archivista, Revision.Decision.PUBLICABLE)

    def test_flujo_completo_anonimizar_y_publicar(self):
        revision = revisar_datos_personales(self.doc)
        revision.decidir(self.archivista, Revision.Decision.ANONIMIZAR, "Persona posiblemente viva")
        self.doc.refresh_from_db()
        self.assertNotIn("79.456.123", self.doc.texto_publico)
        self.assertIn("79.456.123", self.doc.texto_extraido)  # el original no se altera
        self.assertEqual(self.criterio("ACC-01").estado, CUMPLE)

        ok, faltantes = aprobar_publicacion(self.doc, self.archivista)
        self.assertTrue(ok, faltantes)
        self.doc.refresh_from_db()
        self.assertTrue(self.doc.publicado)
        self.assertTrue(self.doc.eventos.filter(tipo=EventoPreservacion.Tipo.PUBLICACION).exists())
        self.assertTrue(verificar_cadena(self.doc)[0])
        self.assertEqual(self.criterio("ACC-03").estado, CUMPLE)

    def test_restringido_no_se_publica(self):
        revision = revisar_datos_personales(self.doc)
        revision.decidir(self.archivista, Revision.Decision.RESTRINGIDO, "Historia clínica")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.texto_publico, "")
        self.assertIn("El documento tiene acceso restringido.", requisitos_publicacion(self.doc))

    def test_nuevo_texto_retira_la_publicacion(self):
        revision = revisar_datos_personales(self.doc)
        revision.decidir(self.archivista, Revision.Decision.ANONIMIZAR, "Persona posiblemente viva")
        aprobar_publicacion(self.doc, self.archivista)
        with open(self.doc.archivo.path, "a") as f:
            f.write(" Nuevo dato: C.C. 1.020.304.050")
        extraer_texto(self.doc)
        self.doc.refresh_from_db()
        self.assertFalse(self.doc.publicado)
        self.assertEqual(self.doc.texto_publico, "")
        self.assertEqual(self.criterio("ACC-01").estado, NO_CUMPLE)

    def test_descripcion_incompleta_bloquea_publicacion(self):
        Documento.objects.filter(pk=self.doc.pk).update(productor="")
        self.doc.refresh_from_db()
        revision = revisar_datos_personales(self.doc)
        revision.decidir(self.archivista, Revision.Decision.RESTRINGIDO, "Prueba")
        faltantes = requisitos_publicacion(self.doc)
        self.assertTrue(any("productor" in f for f in faltantes))

    def test_admin_decide_con_formulario(self):
        revision = revisar_datos_personales(self.doc)
        admin_user = User.objects.create_superuser("admin", password="x")
        self.client.force_login(admin_user)
        url = f"/admin/acceso/revisiondatospersonales/{revision.pk}/change/"
        r = self.client.post(url, {"decision": "anonimizar", "motivo": ""})
        self.assertContains(r, "Indique el motivo")
        r = self.client.post(url, {"decision": "anonimizar", "motivo": "Persona viva"})
        self.assertEqual(r.status_code, 302)
        revision.refresh_from_db()
        self.assertEqual(revision.decidido_por, admin_user)
        self.assertEqual(self.client.get(url).status_code, 200)  # queda en solo lectura


@override_settings(MEDIA_ROOT=MEDIA)
class Acc04SugerenciasNubeTest(TestCase):
    """ACC-04: las sugerencias de un proveedor en la nube (que envía el texto
    a un servicio externo) solo deben existir sobre documentos con la
    revisión de datos personales ya decidida y sin restricción de acceso."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        from asistencia.models import SugerenciaIA

        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.SugerenciaIA = SugerenciaIA
        self.archivista = User.objects.create_user("archivista", password="x")
        self.doc = Documento.objects.create(
            titulo="Certificado médico", archivo=SimpleUploadedFile("cert.txt", TEXTO.encode())
        )
        extraer_texto(self.doc)

    def criterio(self, codigo):
        return next(r for r in evaluar_documento(self.doc) if r.criterio.codigo == codigo)

    def _sugerencia_nube(self):
        return self.SugerenciaIA.objects.create(
            documento=self.doc, proceso="descripcion", campo="titulo",
            valor_propuesto="x", confianza=0.9, modelo="claude", version_modelo="claude-x",
        )

    def _sugerencia_local(self):
        return self.SugerenciaIA.objects.create(
            documento=self.doc, proceso="descripcion", campo="titulo",
            valor_propuesto="x", confianza=0.9, modelo="local-reglas", version_modelo="0.1",
        )

    def test_sin_sugerencias_de_nube_es_manual(self):
        self.assertEqual(self.criterio("ACC-04").estado, MANUAL)

    def test_sugerencias_solo_locales_no_cuentan(self):
        self._sugerencia_local()
        self.assertEqual(self.criterio("ACC-04").estado, MANUAL)

    def test_nube_sin_revision_de_datos_personales_no_cumple(self):
        self._sugerencia_nube()
        self.assertEqual(self.criterio("ACC-04").estado, NO_CUMPLE)

    def test_nube_con_revision_pendiente_no_cumple(self):
        self._sugerencia_nube()
        revisar_datos_personales(self.doc)
        self.assertEqual(self.criterio("ACC-04").estado, NO_CUMPLE)

    def test_nube_sobre_documento_restringido_no_cumple(self):
        self._sugerencia_nube()
        revision = revisar_datos_personales(self.doc)
        revision.decidir(self.archivista, Revision.Decision.RESTRINGIDO, "Historia clínica")
        r = self.criterio("ACC-04")
        self.assertEqual(r.estado, NO_CUMPLE)
        self.assertIn("no debió salir de la entidad", r.evidencia)

    def test_nube_con_revision_decidida_y_no_restringida_cumple(self):
        self._sugerencia_nube()
        revision = revisar_datos_personales(self.doc)
        revision.decidir(self.archivista, Revision.Decision.ANONIMIZAR, "Persona posiblemente viva")
        self.assertEqual(self.criterio("ACC-04").estado, CUMPLE)
