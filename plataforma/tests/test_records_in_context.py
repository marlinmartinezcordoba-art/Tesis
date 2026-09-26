"""Pruebas de la alineación del modelo de datos con RiC-CM 1.0 (ICA-EGAD, 2023):
la entidad de tipo Actividad, el vocabulario ampliado de relaciones, y la
validación de que la combinación tipo de entidad / tipo de relación tenga
sentido (RELACIONES_VALIDAS_POR_TIPO).
"""
import shutil
import tempfile
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from acceso.models import RevisionDatosPersonales as Revision
from acceso.servicios import revisar_datos_personales
from acervo import exportacion
from acervo.extraccion import extraer_texto
from acervo.models import Documento, Entidad, RelacionEntidadDocumento, RelacionEntidadUnidad
from asistencia.proveedor_claude import (
    BorradorDescripcion,
    CampoPropuesto,
    EntidadPropuesta,
    EntidadRelacionada,
    IndicioPropuesto,
    ProveedorClaude,
    ProveedorValoracionClaude,
    ValoracionPropuesta,
)
from asistencia.proveedores import generar_sugerencias

MEDIA = tempfile.mkdtemp()

TEXTO = (
    "Acta de la sesión del Cabildo de Santafé, 20 de julio de 1810, en la que "
    "José Acevedo y Gómez presidió la reunión sobre el levantamiento popular."
)


@override_settings(MEDIA_ROOT=MEDIA)
class RicModeloTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.archivista = User.objects.create_user("archivista", password="x")
        self.doc = Documento.objects.create(
            titulo="Acta", archivo=SimpleUploadedFile("acta.txt", TEXTO.encode())
        )
        extraer_texto(self.doc)

    def _borrador_con_entidades(self, entidades):
        return BorradorDescripcion(
            titulo=CampoPropuesto(valor="", evidencia="", confianza="baja", justificacion=""),
            fechas=CampoPropuesto(valor="", evidencia="", confianza="baja", justificacion=""),
            productor=CampoPropuesto(valor="", evidencia="", confianza="baja", justificacion=""),
            alcance_contenido=CampoPropuesto(valor="", evidencia="", confianza="baja", justificacion=""),
            entidades=entidades,
        )

    def _mock_cliente(self, borrador):
        respuesta = MagicMock(stop_reason="end_turn", model="claude-opus-5", parsed_output=borrador)
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta
        return cliente

    def _publicable(self):
        revisar_datos_personales(self.doc).decidir(self.archivista, Revision.Decision.PUBLICABLE, "")

    def test_no_existe_tipo_concepto(self):
        # RiC-CM no tiene una entidad "concepto"; verificamos que el modelo
        # tampoco la ofrezca como opción.
        self.assertNotIn("concepto", dict(Entidad.Tipo.choices))
        self.assertIn("actividad", dict(Entidad.Tipo.choices))

    def test_proponer_actividad_con_relacion_documenta(self):
        self._publicable()
        borrador = self._borrador_con_entidades([
            EntidadPropuesta(
                tipo="actividad", nombre="Sesión del Cabildo del 20 de julio de 1810",
                relacion="documenta", evidencia="sesión del Cabildo de Santafé", confianza="alta",
            ),
        ])
        [s] = generar_sugerencias(self.doc, ProveedorClaude(cliente=self._mock_cliente(borrador)))
        self.assertEqual(s.campo, "actividad")
        self.assertEqual(s.relacion, "documenta")
        self.assertTrue(s.evidencia_verificada)

        s.validar(self.archivista, aceptar=True)
        relacion = RelacionEntidadDocumento.objects.get(documento=self.doc)
        self.assertEqual(relacion.entidad.tipo, "actividad")
        self.assertEqual(relacion.tipo_relacion, "documenta")

    def test_combinacion_invalida_se_descarta_al_proponer(self):
        # "productor" no tiene sentido para una actividad: MAZUCA lo descarta
        # antes de crear la sugerencia, sin confiar ciegamente en el modelo.
        self._publicable()
        borrador = self._borrador_con_entidades([
            EntidadPropuesta(
                tipo="actividad", nombre="Sesión del Cabildo",
                relacion="productor", evidencia="sesión del Cabildo", confianza="alta",
            ),
        ])
        sugerencias = generar_sugerencias(self.doc, ProveedorClaude(cliente=self._mock_cliente(borrador)))
        self.assertEqual(sugerencias, [])

    def test_combinacion_invalida_se_rechaza_al_validar(self):
        # Defensa en profundidad: aunque alguien fuerce una sugerencia con una
        # combinación inválida (por ejemplo, corrigiendo el campo a mano),
        # validar() la rechaza igual.
        from asistencia.models import SugerenciaIA
        from lineamientos.models import Proceso

        s = SugerenciaIA.objects.create(
            documento=self.doc, proceso=Proceso.DESCRIPCION, campo="lugar",
            valor_propuesto="Santafé", relacion="productor",
            confianza=0.9, modelo="prueba", version_modelo="0",
        )
        with self.assertRaises(ValueError):
            s.validar(self.archivista, aceptar=True)

    def test_relacion_trata_sobre_valida_para_persona(self):
        self._publicable()
        borrador = self._borrador_con_entidades([
            EntidadPropuesta(
                tipo="persona", nombre="José Acevedo y Gómez",
                relacion="trata_sobre", evidencia="José Acevedo y Gómez", confianza="media",
            ),
        ])
        [s] = generar_sugerencias(self.doc, ProveedorClaude(cliente=self._mock_cliente(borrador)))
        s.validar(self.archivista, aceptar=True)
        relacion = RelacionEntidadDocumento.objects.get(documento=self.doc)
        self.assertEqual(relacion.tipo_relacion, "trata_sobre")

    def test_proveedor_local_no_propone_actividades(self):
        from asistencia.proveedor_local import ProveedorLocal

        sugerencias = generar_sugerencias(self.doc, ProveedorLocal())
        self.assertNotIn("actividad", {s.campo for s in sugerencias})

    def test_dublin_core_usa_el_grafo_de_entidades(self):
        # MET-04 (exportación) debe reflejar el grafo RiC construido en
        # descripción, no solo los campos planos de la ficha ISAD(G).
        productor = Entidad.objects.create(tipo="institucion", nombre="Cabildo de Santafé")
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=productor, tipo_relacion="productor"
        )
        tema = Entidad.objects.create(tipo="persona", nombre="José Acevedo y Gómez")
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=tema, tipo_relacion="trata_sobre"
        )
        lugar = Entidad.objects.create(tipo="lugar", nombre="Santafé")
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=lugar, tipo_relacion="lugar_produccion"
        )
        actividad = Entidad.objects.create(tipo="actividad", nombre="Sesión del Cabildo")
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=actividad, tipo_relacion="documenta"
        )

        xml = exportacion.dublin_core_xml(self.doc)
        self.assertIn("<dc:creator>Cabildo de Santafé</dc:creator>", xml)
        self.assertIn("<dc:subject>José Acevedo y Gómez</dc:subject>", xml)
        self.assertIn("<dc:coverage>Santafé</dc:coverage>", xml)
        self.assertIn("Documenta: Sesión del Cabildo", xml)

    def test_dublin_core_sin_entidades_no_falla(self):
        # Documento sin ninguna entidad vinculada: la exportación no debe
        # romperse, solo omitir los campos derivados del grafo.
        xml = exportacion.dublin_core_xml(self.doc)
        self.assertNotIn("dc:subject", xml)
        self.assertNotIn("dc:coverage", xml)

    def _mock_cliente_valoracion(self, indicios):
        respuesta = MagicMock(
            stop_reason="end_turn", model="claude-opus-5",
            parsed_output=ValoracionPropuesta(indicios=indicios),
        )
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta
        return cliente

    def test_valoracion_conecta_indicio_con_entidad_del_grafo(self):
        self._publicable()
        indicio = IndicioPropuesto(
            tipo="historico", evidencia="levantamiento popular", confianza="alta",
            justificacion="Documenta el levantamiento popular de 1810.",
            entidad_relacionada=EntidadRelacionada(
                tipo="actividad", nombre="Levantamiento popular de 1810"
            ),
        )
        cliente = self._mock_cliente_valoracion([indicio])
        [s] = generar_sugerencias(self.doc, ProveedorValoracionClaude(cliente=cliente))
        self.assertEqual(s.entidad_tipo, "actividad")
        self.assertEqual(s.entidad_nombre, "Levantamiento popular de 1810")

        s.validar(self.archivista, aceptar=True)
        relacion = RelacionEntidadDocumento.objects.get(documento=self.doc)
        self.assertEqual(relacion.entidad.nombre, "Levantamiento popular de 1810")
        self.assertEqual(relacion.tipo_relacion, "trata_sobre")

    def test_valoracion_sin_entidad_relacionada_no_crea_relacion(self):
        self._publicable()
        indicio = IndicioPropuesto(
            tipo="cultural", evidencia="fiesta tradicional", confianza="media",
            justificacion="Valor cultural general, sin una entidad concreta.",
            entidad_relacionada=None,
        )
        cliente = self._mock_cliente_valoracion([indicio])
        [s] = generar_sugerencias(self.doc, ProveedorValoracionClaude(cliente=cliente))
        self.assertEqual(s.entidad_tipo, "")
        s.validar(self.archivista, aceptar=True)
        self.assertEqual(RelacionEntidadDocumento.objects.count(), 0)

    def test_valoracion_reutiliza_entidad_ya_creada_en_descripcion(self):
        # La misma actividad identificada en descripción es la que justifica
        # el valor histórico: no debe crear una entidad duplicada.
        self._publicable()
        existente = Entidad.objects.create(tipo="actividad", nombre="Sesión del Cabildo")
        indicio = IndicioPropuesto(
            tipo="historico", evidencia="sesión del Cabildo", confianza="alta",
            justificacion="Documenta la sesión del Cabildo.",
            entidad_relacionada=EntidadRelacionada(tipo="actividad", nombre="Sesión del Cabildo"),
        )
        cliente = self._mock_cliente_valoracion([indicio])
        [s] = generar_sugerencias(self.doc, ProveedorValoracionClaude(cliente=cliente))
        s.validar(self.archivista, aceptar=True)
        self.assertEqual(Entidad.objects.filter(tipo="actividad").count(), 1)
        self.assertEqual(
            RelacionEntidadDocumento.objects.get().entidad_id, existente.pk
        )


@override_settings(MEDIA_ROOT=MEDIA)
class Cla02ProcedenciaTest(TestCase):
    """CLA-02: MAZUCA verifica el principio de procedencia comparando, en
    el grafo RiC, el productor del documento contra el productor
    declarado para la unidad del cuadro de clasificación (Record Set)."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        from acervo.models import UnidadClasificacion

        self.doc = Documento.objects.create(
            titulo="Acta", archivo=SimpleUploadedFile("acta.txt", TEXTO.encode())
        )
        self.serie = UnidadClasificacion.objects.create(
            codigo="F.01.S01", nombre="Actas del Cabildo", tipo="serie"
        )

    def criterio(self, codigo):
        from lineamientos.verificacion import evaluar_documento

        return next(r for r in evaluar_documento(self.doc) if r.criterio.codigo == codigo)

    def test_sin_clasificar_es_manual(self):
        self.assertEqual(self.criterio("CLA-02").estado, "revision_manual")

    def test_serie_sin_productor_declarado_es_manual(self):
        self.doc.unidad_clasificacion = self.serie
        self.doc.save()
        r = self.criterio("CLA-02")
        self.assertEqual(r.estado, "revision_manual")
        self.assertIn("no tiene un productor declarado", r.evidencia)

    def test_productores_coinciden_cumple(self):
        cabildo = Entidad.objects.create(tipo="institucion", nombre="Cabildo de Santafé")
        RelacionEntidadUnidad.objects.create(unidad=self.serie, entidad=cabildo, tipo_relacion="productor")
        self.doc.unidad_clasificacion = self.serie
        self.doc.productor = "Cabildo de Santafé"
        self.doc.save()
        self.assertEqual(self.criterio("CLA-02").estado, "cumple")

    def test_productores_distintos_no_cumple(self):
        cabildo = Entidad.objects.create(tipo="institucion", nombre="Cabildo de Santafé")
        RelacionEntidadUnidad.objects.create(unidad=self.serie, entidad=cabildo, tipo_relacion="productor")
        self.doc.unidad_clasificacion = self.serie
        self.doc.productor = "Real Audiencia"
        self.doc.save()
        r = self.criterio("CLA-02")
        self.assertEqual(r.estado, "no_cumple")
        self.assertIn("mezcla de procedencias", r.evidencia)

    def test_usa_el_grafo_en_vez_del_texto_si_existe(self):
        # Si el documento tiene un productor distinto en el grafo (más
        # confiable) que en el campo de texto, se usa el del grafo.
        cabildo = Entidad.objects.create(tipo="institucion", nombre="Cabildo de Santafé")
        RelacionEntidadUnidad.objects.create(unidad=self.serie, entidad=cabildo, tipo_relacion="productor")
        self.doc.unidad_clasificacion = self.serie
        self.doc.productor = "texto desactualizado"
        self.doc.save()
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=cabildo, tipo_relacion="productor"
        )
        self.assertEqual(self.criterio("CLA-02").estado, "cumple")

    def test_solo_persona_o_institucion_pueden_ser_productoras(self):
        from acervo.models import RELACIONES_VALIDAS_UNIDAD_POR_TIPO

        self.assertEqual(RELACIONES_VALIDAS_UNIDAD_POR_TIPO.get("lugar"), None)
        self.assertEqual(RELACIONES_VALIDAS_UNIDAD_POR_TIPO["institucion"], {"productor"})

    def test_admin_muestra_productor_en_la_lista(self):
        cabildo = Entidad.objects.create(tipo="institucion", nombre="Cabildo de Santafé")
        RelacionEntidadUnidad.objects.create(unidad=self.serie, entidad=cabildo, tipo_relacion="productor")
        admin_user = User.objects.create_superuser("admin", password="x")
        self.client.force_login(admin_user)
        r = self.client.get("/admin/acervo/unidadclasificacion/")
        self.assertContains(r, "Cabildo de Santafé")


@override_settings(MEDIA_ROOT=MEDIA)
class SugerirProductorUnidadTest(TestCase):
    """La procedencia de una unidad del cuadro (CLA-02) no se escribe a mano
    sin más: 'la IA propone, la persona decide' también aplica aquí.
    sugerir_productor_unidad() propone a partir de los documentos ya
    clasificados; la persona archivista sigue confirmando a mano en el
    inline del admin."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        from acervo.models import UnidadClasificacion

        self.serie = UnidadClasificacion.objects.create(
            codigo="F.01.S01", nombre="Actas del Cabildo", tipo="serie"
        )

    def _documento(self, productor_entidad=None):
        doc = Documento.objects.create(
            titulo="Acta", archivo=SimpleUploadedFile("acta.txt", TEXTO.encode()),
            unidad_clasificacion=self.serie,
        )
        if productor_entidad:
            RelacionEntidadDocumento.objects.create(
                documento=doc, entidad=productor_entidad, tipo_relacion="productor"
            )
        return doc

    def test_sin_documentos_clasificados_no_hay_sugerencia(self):
        from acervo.procedencia import sugerir_productor_unidad

        self.assertIsNone(sugerir_productor_unidad(self.serie))

    def test_documentos_sin_productor_identificado_no_hay_sugerencia(self):
        from acervo.procedencia import sugerir_productor_unidad

        self._documento()
        self.assertIsNone(sugerir_productor_unidad(self.serie))

    def test_productor_consistente_se_sugiere_con_conteo(self):
        from acervo.procedencia import sugerir_productor_unidad

        cabildo = Entidad.objects.create(tipo="institucion", nombre="Cabildo de Santafé")
        self._documento(cabildo)
        self._documento(cabildo)
        otro = Entidad.objects.create(tipo="persona", nombre="José Acevedo y Gómez")
        self._documento(otro)

        entidad, coincidencias, total = sugerir_productor_unidad(self.serie)
        self.assertEqual(entidad, cabildo)
        self.assertEqual(coincidencias, 2)
        self.assertEqual(total, 3)

    def test_accion_de_admin_no_escribe_la_relacion(self):
        # La acción del admin solo debe proponer (mensaje), nunca crear la
        # RelacionEntidadUnidad automáticamente.
        cabildo = Entidad.objects.create(tipo="institucion", nombre="Cabildo de Santafé")
        self._documento(cabildo)
        admin_user = User.objects.create_superuser("admin", password="x")
        self.client.force_login(admin_user)

        r = self.client.post(
            "/admin/acervo/unidadclasificacion/",
            {
                "action": "sugerir_productor",
                "_selected_action": [str(self.serie.pk)],
            },
            follow=True,
        )
        self.assertContains(r, "Cabildo de Santafé")
        self.assertFalse(
            RelacionEntidadUnidad.objects.filter(unidad=self.serie).exists()
        )

    def test_accion_de_admin_avisa_si_ya_tiene_productor(self):
        cabildo = Entidad.objects.create(tipo="institucion", nombre="Cabildo de Santafé")
        RelacionEntidadUnidad.objects.create(unidad=self.serie, entidad=cabildo, tipo_relacion="productor")
        admin_user = User.objects.create_superuser("admin", password="x")
        self.client.force_login(admin_user)

        r = self.client.post(
            "/admin/acervo/unidadclasificacion/",
            {
                "action": "sugerir_productor",
                "_selected_action": [str(self.serie.pk)],
            },
            follow=True,
        )
        self.assertContains(r, "ya tiene un productor declarado")
