"""F04 (Segmentación): un único archivo ingerido puede contener, además de
su documento principal, otro documento distinto (por ejemplo dos oficios
escaneados juntos en un solo PDF). El sistema PROPONE dónde empieza cada
uno — nunca separa el archivo solo — y solo al validar la propuesta se
crea el documento segmentado.

Los textos usados son el contenido real (extraído con pypdf) de dos
oficios distintos del paquete RICORA_TEST_SUITE_1_0 que aportó la
autora, tratados aquí como si fueran dos páginas de un mismo archivo
escaneado — el caso exacto que F04 debe resolver."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ric.estructura import detectar_y_guardar_estructura
from ric.models import Instantiation, PaginaTexto, PropuestaSegmentacion, Record, RelacionRiC
from ric.segmentacion import detectar_segmentos, detectar_y_proponer_segmentos

MEDIA = tempfile.mkdtemp()

OFICIO_112 = """ALCALDÍA MUNICIPAL DE SAN PEDRO
OFICIO No. 112-2025
San Pedro, 23 de enero de 2025
PARA: María López, Secretaria General
DE: Juan Pérez, Jefe de Archivo
ASUNTO: Jornada de organización documental
En atención a la Resolución No. 045 de 2025, se informa que la jornada se realizará
el 30 de enero de 2025 en el Archivo Central.
Atentamente,
Juan Pérez
Jefe de Archivo"""

OFICIO_113 = """ALCALDÍA MUNICIPAL DE SAN PEDRO
OFICIO No. 113-2025
PARA: Juan Pérez, Jefe de Archivo
DE: María López, Secretaria General
ASUNTO: Seguimiento
Se solicita presentar el informe de la segunda jornada el 20 de marzo de 2025."""


@override_settings(MEDIA_ROOT=MEDIA)
class DeteccionDeSegmentosTest(TestCase):
    """Dos oficios distintos "escaneados" como dos páginas de un mismo
    archivo — el caso real que F04 debe reconocer."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def _instanciacion_con_dos_oficios(self):
        record = Record.objects.create(nombre="Lote escaneado de oficios")
        inst = Instantiation.objects.create(
            nombre="Lote escaneado", record_resource=record,
            archivo=SimpleUploadedFile("lote.txt", OFICIO_112.encode()),
        )
        # Dos páginas reales (no pasa por extraccion.py: aquí se simula
        # directamente el resultado ya extraído, como si fuera un PDF de
        # dos páginas con un oficio distinto en cada una).
        PaginaTexto.objects.all().filter(instanciacion=inst).delete()
        PaginaTexto.objects.create(instanciacion=inst, numero=1, texto=OFICIO_112)
        PaginaTexto.objects.create(instanciacion=inst, numero=2, texto=OFICIO_113)
        detectar_y_guardar_estructura(inst)
        return inst

    def test_detecta_un_segmento_a_partir_del_segundo_titulo(self):
        inst = self._instanciacion_con_dos_oficios()
        propuestas = detectar_segmentos(inst)
        self.assertEqual(len(propuestas), 1)
        self.assertEqual(propuestas[0]["pagina_inicio"], 2)
        self.assertEqual(propuestas[0]["pagina_fin"], 2)
        self.assertEqual(propuestas[0]["titulo_detectado"], "OFICIO No. 113-2025")

    def test_un_solo_titulo_no_propone_ninguna_segmentacion(self):
        record = Record.objects.create(nombre="Un solo oficio")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("oficio.txt", OFICIO_112.encode()),
        )
        PaginaTexto.objects.create(instanciacion=inst, numero=1, texto=OFICIO_112)
        detectar_y_guardar_estructura(inst)
        self.assertEqual(detectar_segmentos(inst), [])

    def test_detectar_y_proponer_persiste_la_propuesta_pendiente(self):
        inst = self._instanciacion_con_dos_oficios()
        nuevas = detectar_y_proponer_segmentos(inst)
        self.assertEqual(len(nuevas), 1)
        propuesta = PropuestaSegmentacion.objects.get(instanciacion=inst)
        self.assertEqual(propuesta.estado, PropuestaSegmentacion.Estado.PENDIENTE)

    def test_reprocesar_no_duplica_una_propuesta_existente(self):
        inst = self._instanciacion_con_dos_oficios()
        detectar_y_proponer_segmentos(inst)
        detectar_y_proponer_segmentos(inst)  # segunda vez: no debe duplicar
        self.assertEqual(PropuestaSegmentacion.objects.filter(instanciacion=inst).count(), 1)

    def test_reprocesar_no_toca_una_propuesta_ya_decidida(self):
        """A diferencia de F02/F03, una decisión humana nunca se
        sobrescribe al reprocesar."""
        inst = self._instanciacion_con_dos_oficios()
        detectar_y_proponer_segmentos(inst)
        propuesta = PropuestaSegmentacion.objects.get(instanciacion=inst)
        usuario = User.objects.create_user("archivista", password="x")
        propuesta.validar(usuario, aceptar=False, motivo="Es el mismo trámite, no un documento aparte.")

        detectar_y_proponer_segmentos(inst)
        propuesta.refresh_from_db()
        self.assertEqual(propuesta.estado, PropuestaSegmentacion.Estado.RECHAZADA)
        self.assertEqual(PropuestaSegmentacion.objects.filter(instanciacion=inst).count(), 1)


@override_settings(MEDIA_ROOT=MEDIA)
class ValidarSegmentacionTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.usuario = User.objects.create_user("archivista", password="x")
        self.contenedor = Record.objects.create(nombre="Lote escaneado de oficios")
        self.inst = Instantiation.objects.create(
            nombre="Lote escaneado", record_resource=self.contenedor,
            archivo=SimpleUploadedFile("lote.txt", OFICIO_112.encode()),
        )
        PaginaTexto.objects.create(instanciacion=self.inst, numero=1, texto=OFICIO_112)
        PaginaTexto.objects.create(instanciacion=self.inst, numero=2, texto=OFICIO_113)
        detectar_y_guardar_estructura(self.inst)
        detectar_y_proponer_segmentos(self.inst)
        self.propuesta = PropuestaSegmentacion.objects.get(instanciacion=self.inst)

    def test_aceptar_crea_record_e_instantiation_nuevos(self):
        self.propuesta.validar(self.usuario, aceptar=True)
        self.propuesta.refresh_from_db()

        self.assertEqual(self.propuesta.estado, PropuestaSegmentacion.Estado.ACEPTADA)
        self.assertIsNotNone(self.propuesta.record_creado)
        self.assertIsNotNone(self.propuesta.instanciacion_creada)
        self.assertEqual(self.propuesta.record_creado.nombre, "OFICIO No. 113-2025")

    def test_la_instanciacion_nueva_tiene_el_mismo_hash_del_original(self):
        """Es un recorte lógico del mismo objeto digital, no una copia
        distinta: el hash tiene que coincidir."""
        self.propuesta.validar(self.usuario, aceptar=True)
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.instanciacion_creada.sha256, self.inst.sha256)

    def test_la_instanciacion_nueva_solo_tiene_las_paginas_del_segmento(self):
        self.propuesta.validar(self.usuario, aceptar=True)
        self.propuesta.refresh_from_db()
        nueva = self.propuesta.instanciacion_creada
        self.assertEqual(nueva.paginas.count(), 1)
        self.assertEqual(nueva.paginas.first().numero, 1)
        self.assertIn("OFICIO No. 113-2025", nueva.paginas.first().texto)

    def test_la_instanciacion_nueva_tiene_su_propia_estructura_detectada(self):
        self.propuesta.validar(self.usuario, aceptar=True)
        self.propuesta.refresh_from_db()
        nueva = self.propuesta.instanciacion_creada
        tipos = set(nueva.componentes.values_list("tipo", flat=True))
        self.assertIn("titulo", tipos)
        self.assertIn("campo", tipos)

    def test_aceptar_crea_relacion_ric_r002_entre_contenedor_y_segmento(self):
        self.propuesta.validar(self.usuario, aceptar=True)
        self.propuesta.refresh_from_db()
        relacion = RelacionRiC.objects.get(
            relacion_id="R002", origen_object_id=self.contenedor.pk,
            destino_object_id=self.propuesta.record_creado.pk,
        )
        self.assertEqual(relacion.estado, RelacionRiC.Estado.ACEPTADA)

    def test_rechazar_no_crea_ningun_documento_nuevo(self):
        total_records_antes = Record.objects.count()
        self.propuesta.validar(self.usuario, aceptar=False, motivo="Es el mismo trámite.")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaSegmentacion.Estado.RECHAZADA)
        self.assertIsNone(self.propuesta.record_creado)
        self.assertEqual(Record.objects.count(), total_records_antes)

    def test_no_se_puede_validar_dos_veces(self):
        self.propuesta.validar(self.usuario, aceptar=True)
        with self.assertRaises(ValueError):
            self.propuesta.validar(self.usuario, aceptar=True)

    def test_rechazar_sin_motivo_falla(self):
        with self.assertRaises(ValueError):
            self.propuesta.validar(self.usuario, aceptar=False)
