"""Módulo 1 · Ingesta (sección 8 del prompt de desarrollo y auditoría de
arquitectura, preguntas 11 y 17): carga de archivos pesados archivo por
archivo, validación de contenido contra la extensión, límite de tamaño,
deduplicación por SHA-256, y visor documental con contexto RiC y control de
acceso por rol."""

import hashlib
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from ric import carga, instrumentos
from ric.models import Activity, EventoRiC, Instantiation, Record, RecordSet, RegistroAuditoria

from ._ayudas import CasoModulos, candidato
from .test_m1_ingesta import ORGANIGRAMA, TRD


def pdf_de_prueba(paginas=2):
    imagenes = [Image.new("RGB", (400, 300), (255, 255, 255 - i * 40)) for i in range(paginas)]
    salida = io.BytesIO()
    imagenes[0].save(salida, format="PDF", save_all=True, append_images=imagenes[1:])
    return salida.getvalue()


def tiff_de_prueba(paginas=2):
    imagenes = [Image.new("RGB", (300, 200), (200, 10 * i, 10)) for i in range(paginas)]
    salida = io.BytesIO()
    imagenes[0].save(salida, format="TIFF", save_all=True, append_images=imagenes[1:])
    return salida.getvalue()


class CasoCarga(CasoModulos):
    def setUp(self):
        super().setUp()
        instrumentos.importar_organigrama(ORGANIGRAMA, self.archivista)
        instrumentos.importar_trd(TRD, self.archivista)
        self.serie = Activity.objects.get(identificador="TRD 1000-24")

    def subir(self, nombre, contenido, **datos):
        base = {"serie_id": self.serie.pk, "expediente_nuevo": "Petición 0412", "archivo": SimpleUploadedFile(nombre, contenido)}
        base.update(datos)
        return self.client.post(reverse("ingesta_archivo"), base)


class CargaPorArchivoTest(CasoCarga):
    def test_un_archivo_valido_devuelve_su_fila_con_huella(self):
        self.client.force_login(self.archivista)
        contenido = pdf_de_prueba()
        resp = self.subir("oficio.pdf", contenido)
        self.assertEqual(resp.status_code, 201)
        fila = resp.json()
        self.assertTrue(fila["ok"])
        self.assertEqual(fila["sha256"], hashlib.sha256(contenido).hexdigest())
        self.assertEqual(fila["tipo_mime"], "application/pdf")
        self.assertEqual(fila["expediente"], "Petición 0412")
        self.assertTrue(fila["expediente_creado"])
        inst = Instantiation.objects.get(pk=fila["instanciacion_id"])
        self.assertEqual(inst.creado_por, self.archivista)
        self.assertEqual(inst.paginas.count(), 0)  # no preprocesa: lo pide el archivista
        self.assertTrue(EventoRiC.objects.filter(instanciacion=inst, tipo="ingesta", detalle__tipo_mime="application/pdf").exists())
        self.assertIn(reverse("visor_documento", args=[fila["documento_id"]]), fila["visor_url"])
        # el segundo archivo reutiliza el expediente por su id (la pantalla lo envía así)
        resp = self.subir("anexo.txt", b"Anexo del oficio", expediente_nuevo="", expediente_id=fila["expediente_id"])
        self.assertEqual(resp.json()["expediente_id"], fila["expediente_id"])
        self.assertEqual(RecordSet.objects.filter(tipo_conjunto="expediente").count(), 1)

    def test_extension_que_no_coincide_con_el_contenido_se_rechaza_sin_guardar(self):
        self.client.force_login(self.archivista)
        resp = self.subir("falso.pdf", b"esto no es un PDF")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("el contenido no corresponde a un archivo .pdf", resp.json()["error"])
        for nombre, contenido in (("foto.png", b"GIF89a..."), ("hoja.docx", b"PK\x03\x04no-es-zip"), ("datos.txt", b"\x00\x01binario"), ("vacio.txt", b"")):
            self.assertEqual(self.subir(nombre, contenido).status_code, 400, nombre)
        self.assertFalse(Instantiation.objects.exists())
        self.assertFalse(RecordSet.objects.filter(tipo_conjunto="expediente").exists())

    def test_formato_no_soportado_y_tamano_maximo(self):
        self.client.force_login(self.archivista)
        resp = self.subir("nota.mp3", b"ID3...")
        self.assertIn("formato .mp3 no soportado", resp.json()["error"])
        with override_settings(RICORA_TAMANO_MAXIMO_MB=0):
            resp = self.subir("acta.txt", b"Acta")
        self.assertIn("el máximo es 0 MB", resp.json()["error"])
        self.assertFalse(Instantiation.objects.exists())

    def test_duplicado_por_huella_se_rechaza_y_dice_cual_es(self):
        self.client.force_login(self.archivista)
        self.subir("acta.txt", b"Acta del comite 12")
        resp = self.subir("acta-copia.txt", b"Acta del comite 12")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("ya fue ingerido antes (misma huella SHA-256) como «acta.txt»", resp.json()["error"])
        self.assertEqual(Instantiation.objects.count(), 1)

    def test_partes_de_un_mismo_documento_y_carpeta_como_expediente(self):
        self.client.force_login(self.archivista)
        r1 = self.subir("p1.txt", b"parte uno", un_solo_documento="1", nombre_documento="Oficio escaneado").json()
        self.subir("p2.txt", b"parte dos", un_solo_documento="1", documento_id=r1["documento_id"])
        documento = Record.objects.get(nombre="Oficio escaneado")
        self.assertEqual(documento.instanciaciones.count(), 2)
        r3 = self.subir("x.txt", b"equis", expediente_nuevo="", ruta="Peticiones/Exp 0009/x.txt").json()
        self.assertEqual(r3["expediente"], "Exp 0009")

    def test_imagen_docx_y_tiff_validos(self):
        self.client.force_login(self.archivista)
        png = io.BytesIO(); Image.new("RGB", (10, 10)).save(png, format="PNG")
        self.assertEqual(self.subir("f.png", png.getvalue()).status_code, 201)
        self.assertEqual(self.subir("f.tif", tiff_de_prueba()).status_code, 201)
        from docx import Document
        d = io.BytesIO(); doc = Document(); doc.add_paragraph("Oficio"); doc.save(d)
        self.assertEqual(self.subir("f.docx", d.getvalue()).status_code, 201)

    def test_solo_archivista_y_con_sesion(self):
        resp = self.subir("a.txt", b"a")
        self.assertEqual(resp.status_code, 401)
        self.client.force_login(self.revisor)
        resp = self.subir("a.txt", b"a")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(RegistroAuditoria.objects.filter(accion="acceso_denegado", usuario=self.revisor, detalle__ruta=reverse("ingesta_archivo")).exists())
        self.assertFalse(Instantiation.objects.exists())

    def test_pantalla_con_boton_de_preprocesamiento_y_limites(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ingesta"), {"serie": self.serie.pk})
        self.assertContains(resp, 'data-url="%s"' % reverse("ingesta_archivo"))
        self.assertContains(resp, 'data-max-mb="200"')
        self.assertContains(resp, 'id="enviar-preproceso"')
        self.subir("a.txt", b"texto a")
        inst = Instantiation.objects.get()
        resp = self.client.post(reverse("preproceso_enviar"), {"instanciacion": [inst.pk]}, follow=True)
        self.assertGreater(inst.paginas.count(), 0)


class VisorTest(CasoCarga):
    def _documento_pdf(self):
        self.client.force_login(self.archivista)
        fila = self.subir("oficio.pdf", pdf_de_prueba(3)).json()
        return Record.objects.get(pk=fila["documento_id"]), Instantiation.objects.get(pk=fila["instanciacion_id"])

    def test_pdf_con_pdfjs_y_contexto_rico(self):
        record, inst = self._documento_pdf()
        resp = self.client.get(reverse("visor_documento", args=[record.pk]))
        self.assertContains(resp, "ric/js/pdfjs/pdf.min.js")
        self.assertContains(resp, 'id="lienzo-pdf"')
        self.assertContains(resp, "Derechos de petición")  # ruta: serie
        self.assertContains(resp, "Petición 0412")  # ruta: expediente
        self.assertContains(resp, "gestión 3 años · central 7 años · Selección")  # retención heredada
        self.assertContains(resp, inst.sha256[:20])
        self.assertContains(resp, "application/pdf")
        registro = RegistroAuditoria.objects.get(accion="consultar", object_id=record.pk)
        self.assertEqual(registro.usuario, self.archivista)
        self.assertEqual(registro.detalle["instanciacion"], inst.pk)

    def test_relaciones_y_evidencia_por_pagina(self):
        record, _ = self.documento(texto="Acta del Cabildo de Santafé, firmada en Bogotá.")
        [p] = self.proponer(record, candidato())
        p.validar(self.archivista, aceptar=True)
        self.client.force_login(self.revisor)
        resp = self.client.get(reverse("visor_documento", args=[record.pk]))
        self.assertContains(resp, "Procedencia")
        self.assertContains(resp, "R027 has creator")
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertContains(resp, "Acta del Cabildo de Santafé")  # texto extraído de la página 1
        self.assertContains(resp, "datos-evidencias")

    def test_tiff_se_convierte_a_png_por_pagina(self):
        self.client.force_login(self.archivista)
        fila = self.subir("escaneo.tif", tiff_de_prueba(2)).json()
        resp = self.client.get(reverse("visor_documento", args=[fila["documento_id"]]))
        self.assertContains(resp, reverse("ric_archivo_pagina", args=[fila["instanciacion_id"], 1]))
        resp = self.client.get(reverse("ric_archivo_pagina", args=[fila["instanciacion_id"], 2]))
        self.assertEqual(resp["Content-Type"], "image/png")
        self.assertEqual(Image.open(io.BytesIO(resp.content)).format, "PNG")
        self.assertEqual(self.client.get(reverse("ric_archivo_pagina", args=[fila["instanciacion_id"], 3])).status_code, 404)

    def test_consulta_solo_ve_lo_publicado_y_abierto(self):
        record, inst = self._documento_pdf()
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("visor_documento", args=[record.pk]), follow=True)
        self.assertContains(resp, "no está disponible para consulta")
        self.assertEqual(self.client.get(reverse("ric_archivo", args=[inst.pk])).status_code, 403)
        self.assertTrue(RegistroAuditoria.objects.filter(accion="acceso_denegado", usuario=self.consulta).exists())
        record.publicado = True
        record.save()
        self.assertEqual(self.client.get(reverse("visor_documento", args=[record.pk])).status_code, 200)
        respuesta = self.client.get(reverse("ric_archivo", args=[inst.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["X-Content-Type-Options"], "nosniff")
        inst.condicion_acceso = Instantiation.CondicionAcceso.RESERVADO
        inst.save()
        self.assertEqual(self.client.get(reverse("ric_archivo", args=[inst.pk])).status_code, 403)

    def test_texto_se_muestra_como_texto(self):
        self.client.force_login(self.archivista)
        fila = self.subir("nota.txt", b"Nota interna sobre el expediente").json()
        inst = Instantiation.objects.get(pk=fila["instanciacion_id"])
        self.client.post(reverse("preproceso_enviar"), {"instanciacion": [inst.pk]})
        resp = self.client.get(reverse("visor_documento", args=[fila["documento_id"]]))
        self.assertNotContains(resp, 'id="lienzo-pdf"')
        self.assertContains(resp, "Nota interna sobre el expediente")


class ValidacionUnitariaTest(CasoModulos):
    def test_firma_de_cada_formato(self):
        casos = {
            "a.pdf": (pdf_de_prueba(1), True), "a.xml": (b"<?xml version='1.0'?><a/>", True), "b.xml": (b"no es xml", False),
            "a.jpg": (b"\xff\xd8\xff\xe0resto", True), "a.bmp": (b"BMxx", True), "a.tiff": (b"MM\x00*xx", True),
        }
        for nombre, (contenido, valido) in casos.items():
            archivo = SimpleUploadedFile(nombre, contenido)
            if valido:
                carga.validar(archivo)
            else:
                with self.assertRaises(carga.ArchivoRechazado):
                    carga.validar(archivo)


class VisorPaginasTest(CasoCarga):
    def test_tiff_sin_preprocesar_se_hojea_completo(self):
        self.client.force_login(self.archivista)
        fila = self.subir("escaneo.tif", tiff_de_prueba(3)).json()
        resp = self.client.get(reverse("visor_documento", args=[fila["documento_id"]]))
        self.assertEqual(resp.context["total_paginas"], 3)
        self.assertContains(resp, 'id="total-paginas">3<')
