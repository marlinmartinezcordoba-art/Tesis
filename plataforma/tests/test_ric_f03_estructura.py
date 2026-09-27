"""F03 (Comprensión documental): detección automática de encabezados,
títulos, campos (PARA/DE/ASUNTO), fechas, secciones, artículos, firmas y
tablas, sobre el texto ya extraído (F02).

Los textos de las pruebas son el contenido real (extraído con pypdf) de
los documentos del paquete RICORA_TEST_SUITE_1_0 que aportó la autora
(actas, oficios y resoluciones de la Alcaldía Municipal de San Pedro,
todos ficticios) — no son inventados para la prueba."""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ric.estructura import _detectar_lineas, detectar_y_guardar_estructura
from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import ComponenteEstructural, Instantiation, Record

MEDIA = tempfile.mkdtemp()

ACTA_001 = """ALCALDÍA MUNICIPAL DE SAN PEDRO
COMITÉ INSTITUCIONAL DE GESTIÓN Y DESEMPEÑO
ACTA DE REUNIÓN No. 001
Fecha: 15 de enero de 2025
Lugar: Sala de Juntas, San Pedro
ASISTENTES
María López — Secretaria General
Juan Pérez — Jefe de Archivo
Carlos Ruiz — Alcalde Municipal
ORDEN DEL DÍA
1. Organización del archivo central.
2. Actualización de instrumentos archivísticos.
3. Varios.
DECISIÓN
Se acuerda realizar una jornada de organización documental el 30 de enero de 2025.
Firma:
Carlos Ruiz
Alcalde Municipal"""

ACTA_002_SIN_FIRMA = """ALCALDÍA MUNICIPAL DE SAN PEDRO
ACTA DE REUNIÓN No. 002
Fecha: 01 de marzo de 2025
Lugar: Archivo Central
TEMA
Seguimiento a la organización documental.
DECISIÓN
Se aprueba una segunda jornada para el 15 de marzo de 2025."""

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

RESOLUCION_045 = """ALCALDÍA MUNICIPAL DE SAN PEDRO
RESOLUCIÓN No. 045 DE 2025
20 de enero de 2025
Por la cual se adopta la jornada institucional de organización documental.
EL ALCALDE MUNICIPAL
CONSIDERANDO:
Que la administración municipal debe garantizar la adecuada gestión de los documentos.
RESUELVE:
ARTÍCULO 1. Adoptar la jornada de organización documental.
ARTÍCULO 2. Designar a la Secretaría General como responsable de coordinación.
ARTÍCULO 3. La jornada se realizará el 30 de enero de 2025.
COMUNÍQUESE Y CÚMPLASE.
Carlos Ruiz
Alcalde Municipal"""


def _tipos(componentes):
    return [c["tipo"] for c in componentes]


class DeteccionSobreDocumentosRealesTest(TestCase):
    """Prueba unitaria del motor de reglas (`_detectar_lineas`), sin base
    de datos: rápida, y valida el diseño contra los 7 documentos reales
    del paquete de pruebas."""

    def _lineas(self, texto):
        return [l.strip() for l in texto.splitlines() if l.strip()]

    def test_acta_001_encabezado_titulo_campos_secciones_y_firma(self):
        c = _detectar_lineas(self._lineas(ACTA_001))
        por_tipo = {}
        for comp in c:
            por_tipo.setdefault(comp["tipo"], []).append(comp)

        self.assertEqual(por_tipo["encabezado"][0]["texto"], "ALCALDÍA MUNICIPAL DE SAN PEDRO")
        self.assertEqual(por_tipo["encabezado"][1]["texto"], "COMITÉ INSTITUCIONAL DE GESTIÓN Y DESEMPEÑO")
        self.assertEqual(por_tipo["titulo"][0]["texto"], "ACTA DE REUNIÓN No. 001")

        campos = {c["etiqueta"]: c["texto"] for c in por_tipo["campo"]}
        self.assertEqual(campos["FECHA"], "15 de enero de 2025")
        self.assertEqual(campos["LUGAR"], "Sala de Juntas, San Pedro")

        fechas = {c["texto"] for c in por_tipo["fecha"]}
        self.assertIn("15 de enero de 2025", fechas)
        self.assertIn("30 de enero de 2025", fechas)

        secciones = {c["texto"] for c in por_tipo["seccion"]}
        self.assertEqual(secciones, {"ASISTENTES", "ORDEN DEL DÍA", "DECISIÓN"})

        firmas = [c["texto"] for c in por_tipo["firma"]]
        self.assertEqual(firmas, ["Firma:", "Carlos Ruiz", "Alcalde Municipal"])

    def test_acta_002_sin_firma_no_inventa_una(self):
        c = _detectar_lineas(self._lineas(ACTA_002_SIN_FIRMA))
        self.assertNotIn("firma", _tipos(c))

    def test_oficio_112_campos_para_de_asunto_y_firma_por_atentamente(self):
        c = _detectar_lineas(self._lineas(OFICIO_112))
        por_tipo = {}
        for comp in c:
            por_tipo.setdefault(comp["tipo"], []).append(comp)

        campos = {c["etiqueta"]: c["texto"] for c in por_tipo["campo"]}
        self.assertEqual(campos["PARA"], "María López, Secretaria General")
        self.assertEqual(campos["DE"], "Juan Pérez, Jefe de Archivo")
        self.assertEqual(campos["ASUNTO"], "Jornada de organización documental")

        firmas = [c["texto"] for c in por_tipo["firma"]]
        self.assertEqual(firmas, ["Atentamente,", "Juan Pérez", "Jefe de Archivo"])

        # "Resolución No. 045 de 2025" es una referencia dentro de un párrafo,
        # no un título del documento (el título solo se busca al comienzo).
        self.assertNotIn("RESOLUCIÓN", [c["texto"] for c in por_tipo.get("titulo", [])])

    def test_resolucion_045_articulos_y_firma_sin_disparador_explicito(self):
        c = _detectar_lineas(self._lineas(RESOLUCION_045))
        por_tipo = {}
        for comp in c:
            por_tipo.setdefault(comp["tipo"], []).append(comp)

        self.assertEqual(por_tipo["titulo"][0]["texto"], "RESOLUCIÓN No. 045 DE 2025")
        self.assertEqual(por_tipo["fecha"][0]["texto"], "20 de enero de 2025")

        articulos = [(c["etiqueta"], c["texto"]) for c in por_tipo["articulo"]]
        self.assertEqual(articulos[0][0], "ARTÍCULO 1")
        self.assertEqual(len(articulos), 3)

        # Sin la palabra "Firma:" ni "Atentamente": el cierre "Carlos Ruiz" /
        # "Alcalde Municipal" se reconoce igual por su forma (nombre/cargo
        # corto sin punto final), no por descarte silencioso.
        firmas = [c["texto"] for c in por_tipo["firma"]]
        self.assertEqual(firmas, ["Carlos Ruiz", "Alcalde Municipal"])

    def test_orden_de_lectura_es_creciente(self):
        c = _detectar_lineas(self._lineas(ACTA_001))
        self.assertEqual([comp["orden"] for comp in c], list(range(len(c))))


@override_settings(MEDIA_ROOT=MEDIA)
class DeteccionIntegradaConIngestaTest(TestCase):
    """F03 enganchado a la ingesta real (F01/F02): al extraer el texto de
    una Instantiation, `detectar_y_guardar_estructura` persiste sus
    componentes en la base de datos."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_detectar_y_guardar_persiste_componentes_por_pagina(self):
        record = Record.objects.create(nombre="Acta 001")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("acta_001.txt", ACTA_001.encode()),
        )
        extraer_texto_de_instanciacion(inst)
        detectar_y_guardar_estructura(inst)

        componentes = ComponenteEstructural.objects.filter(instanciacion=inst)
        self.assertGreater(componentes.count(), 0)
        self.assertTrue(all(c.pagina == 1 for c in componentes))
        self.assertEqual(
            list(componentes.order_by("orden").values_list("orden", flat=True)),
            list(range(componentes.count())),
        )

    def test_reprocesar_reemplaza_los_componentes_anteriores(self):
        record = Record.objects.create(nombre="Acta 001")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("acta_001.txt", ACTA_001.encode()),
        )
        extraer_texto_de_instanciacion(inst)
        detectar_y_guardar_estructura(inst)
        primero = ComponenteEstructural.objects.filter(instanciacion=inst).count()
        detectar_y_guardar_estructura(inst)  # segunda vez: no debe duplicar
        segundo = ComponenteEstructural.objects.filter(instanciacion=inst).count()
        self.assertEqual(primero, segundo)


@override_settings(MEDIA_ROOT=MEDIA)
class TablasDeDocxTest(TestCase):
    """F03: tablas reales cuando el original es un .docx (filas/columnas
    exactas, no una suposición sobre texto plano)."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def _docx_con_tabla(self):
        import io

        import docx

        documento = docx.Document()
        documento.add_paragraph("ALCALDÍA MUNICIPAL DE SAN PEDRO")
        documento.add_paragraph("INFORME DE INVENTARIO")
        tabla = documento.add_table(rows=2, cols=2)
        tabla.rows[0].cells[0].text = "Caja"
        tabla.rows[0].cells[1].text = "Estado"
        tabla.rows[1].cells[0].text = "001"
        tabla.rows[1].cells[1].text = "Completa"
        buffer = io.BytesIO()
        documento.save(buffer)
        return buffer.getvalue()

    def test_tabla_real_del_docx_se_detecta_con_sus_filas(self):
        record = Record.objects.create(nombre="Informe con tabla")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("informe.docx", self._docx_con_tabla()),
        )
        extraer_texto_de_instanciacion(inst)
        componentes = detectar_y_guardar_estructura(inst)

        tablas = [c for c in componentes if c["tipo"] == "tabla"]
        self.assertEqual(len(tablas), 1)
        self.assertEqual(
            tablas[0]["datos"]["filas"],
            [["Caja", "Estado"], ["001", "Completa"]],
        )

    def test_docx_sin_tabla_no_produce_componentes_tabla(self):
        import io

        import docx

        documento = docx.Document()
        documento.add_paragraph("ALCALDÍA MUNICIPAL DE SAN PEDRO")
        documento.add_paragraph("INFORME DE ORGANIZACIÓN")
        buffer = io.BytesIO()
        documento.save(buffer)

        record = Record.objects.create(nombre="Informe sin tabla")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("informe.docx", buffer.getvalue()),
        )
        extraer_texto_de_instanciacion(inst)
        componentes = detectar_y_guardar_estructura(inst)
        self.assertFalse([c for c in componentes if c["tipo"] == "tabla"])
