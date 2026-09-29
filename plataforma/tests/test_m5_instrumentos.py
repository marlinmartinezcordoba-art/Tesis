"""M5 · Precarga de instrumentos archivísticos (TRD, CCD, organigrama) y
los ajustes de la especificación v2: retención y disposición en la forma
documental, nota de autenticidad e instanciación de origen."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ric import instrumentos
from ric.models import Activity, CorporateBody, FormaDocumental, Instantiation, RelacionRiC

from ._ayudas import CasoModulos

TRD = (
    "Forma documental;Serie;Retención gestión;Retención central;Disposición final\n"
    "Acta;100.02 Actas de comité;2;8;Conservación total\n"
    "Oficio;200.05 Comunicaciones oficiales;2;3;Eliminación\n"
)
CCD = "funcion,tipo,dependencia\nContratación pública,sustantiva,Secretaría General\nGestión documental,de apoyo,Secretaría General\n"
ORGANIGRAMA = "dependencia,dependencia_superior,sigla\nAlcaldía Mayor,,AM\nSecretaría General,Alcaldía Mayor,SG\nArchivo Central,Secretaría General,AC\n"


class ImportarInstrumentosTest(CasoModulos):
    def test_trd_crea_formas_documentales_con_retencion_y_disposicion(self):
        resultado = instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        self.assertEqual(resultado["creadas"], 2)
        acta = FormaDocumental.objects.get(nombre="Acta")
        self.assertEqual(acta.serie_trd, "100.02 Actas de comité")
        self.assertEqual(acta.tiempo_retencion_archivo_gestion, 2)
        self.assertEqual(acta.tiempo_retencion_archivo_central, 8)
        self.assertEqual(acta.disposicion_final, "conservacion_total")
        self.assertEqual(acta.creado_por, self.archivista)
        # idempotente: volver a importar actualiza, no duplica
        resultado = instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        self.assertEqual(resultado["creadas"], 0)
        self.assertEqual(FormaDocumental.objects.count(), 2)

    def test_ccd_crea_actividades_y_su_dependencia_con_relacion_verificada(self):
        resultado = instrumentos.importar_ccd(CCD, self.archivista)
        self.assertEqual(resultado["creadas"], 2)
        self.assertEqual(resultado["relaciones"], 2)
        actividad = Activity.objects.get(nombre="Contratación pública")
        self.assertEqual(actividad.tipo_actividad, "sustantiva")
        secretaria = CorporateBody.objects.get(nombre="Secretaría General")
        rel = RelacionRiC.objects.get(relacion_id="R060", origen_object_id=actividad.pk)
        self.assertEqual(rel.destino, secretaria)
        self.assertEqual(rel.estado, RelacionRiC.Estado.ACEPTADA)
        self.assertEqual(rel.origen_decision, "correccion_manual")

    def test_organigrama_crea_jerarquia_con_r045(self):
        resultado = instrumentos.importar_organigrama(ORGANIGRAMA, self.archivista)
        self.assertEqual(resultado["creadas"], 3)
        self.assertEqual(resultado["relaciones"], 2)
        alcaldia = CorporateBody.objects.get(nombre="Alcaldía Mayor")
        self.assertEqual(alcaldia.identificador, "AM")
        secretaria = CorporateBody.objects.get(nombre="Secretaría General")
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R045", origen_object_id=alcaldia.pk, destino_object_id=secretaria.pk).exists())

    def test_columnas_faltantes_dan_error_claro(self):
        with self.assertRaises(instrumentos.ErrorDeImportacion) as ctx:
            instrumentos.importar_trd("nombre;algo\nx;y\n", self.archivista)
        self.assertIn("forma_documental", str(ctx.exception))

    def test_importar_desde_la_pantalla_solo_archivista(self):
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("vocabularios_importar"), {"instrumento": "trd", "archivo": SimpleUploadedFile("trd.csv", TRD.encode())}, follow=True)
        self.assertContains(resp, "requiere el rol archivista")
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("vocabularios_importar"), {"instrumento": "trd", "archivo": SimpleUploadedFile("trd.csv", TRD.encode())}, follow=True)
        self.assertContains(resp, "2 fila(s) leídas")
        self.assertContains(resp, "Precargar instrumentos archivísticos")
        self.assertEqual(FormaDocumental.objects.count(), 2)

    def test_el_motor_recibe_el_vocabulario_precargado(self):
        from ric.ia_prompt import vocabulario_existente

        instrumentos.importar_organigrama(ORGANIGRAMA, self.archivista)
        instrumentos.importar_trd(TRD, self.archivista)
        vocabulario = vocabulario_existente()
        self.assertIn("Secretaría General", vocabulario)
        self.assertIn("forma documental · Acta", vocabulario)


class FormaDocumentalRetencionTest(CasoModulos):
    def test_crear_y_editar_con_retencion_desde_la_pantalla(self):
        self.client.force_login(self.archivista)
        self.client.post(reverse("vocabularios"), {"nombre": "Acta", "serie_trd": "100.02", "retencion_gestion": "2", "retencion_central": "8", "disposicion_final": "conservacion_total"})
        acta = FormaDocumental.objects.get(nombre="Acta")
        self.assertEqual(acta.tiempo_retencion_archivo_central, 8)
        resp = self.client.get(reverse("vocabulario_ficha", args=["formadocumental", acta.pk]))
        self.assertContains(resp, "Conservación total")
        self.client.post(reverse("vocabulario_ficha", args=["formadocumental", acta.pk]), {"nombre": "Acta", "definicion": "", "serie_trd": "100.02", "retencion_gestion": "3", "retencion_central": "8", "disposicion_final": "seleccion"})
        acta.refresh_from_db()
        self.assertEqual(acta.tiempo_retencion_archivo_gestion, 3)
        self.assertEqual(acta.disposicion_final, "seleccion")


class AutenticidadInstanciacionTest(CasoModulos):
    def test_nota_de_autenticidad_e_instanciacion_de_origen(self):
        record, inst = self.documento()
        derivada = Instantiation.objects.create(
            nombre="copia PDF/A", record_resource=record, archivo=SimpleUploadedFile("copia.txt", b"x"),
            instanciacion_origen=inst, tipo_copia=Instantiation.TipoCopia.MASTER,
        )
        self.assertNotEqual(derivada.sha256, inst.sha256)
        self.assertIn(derivada, inst.derivadas.all())
        self.client.force_login(self.archivista)
        self.client.post(reverse("catalogo_ficha", args=["record", record.pk]), {f"autenticidad_{inst.pk}": "Sello de tiempo TSA 2026-09-28", f"acceso_{inst.pk}": "abierto"})
        inst.refresh_from_db()
        self.assertEqual(inst.nota_autenticidad, "Sello de tiempo TSA 2026-09-28")
        resp = self.client.get(reverse("catalogo_ficha", args=["record", record.pk]))
        self.assertContains(resp, "derivada de «acta.txt» (R015)")
