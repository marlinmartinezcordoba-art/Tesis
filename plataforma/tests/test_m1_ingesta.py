"""Captura y clasificación (/ingesta): opción A — serie de la TRD, expediente
existente o nuevo (o carpeta), archivos como documentos del expediente,
huella, bitácora y preprocesamiento automático. RF-M1-01 a RF-M1-04."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from ric import clasificacion, instrumentos
from ric.models import Activity, CorporateBody, EventoRiC, Instantiation, Record, RecordSet, RelacionRiC

from ._ayudas import TEXTO, CasoModulos

TRD = (
    "Código oficina;Oficina;Código serie;Serie;Tipos documentales;Retención gestión;Retención central;Disposición final\n"
    "1000;Despacho del Ministro;24;DERECHOS DE PETICIÓN;Derecho de petición|Respuesta;3;7;S\n"
    "4106;Grupo de Gestión Documental;10;ACTAS;Acta;2;18;CT\n"
)
ORGANIGRAMA = '{"entidades": [["MADS", "Ministerio de Ambiente", null], ["1000", "Despacho del Ministro", "MADS"], ["4106", "Grupo de Gestión Documental", "1000"]]}'


class CasoCaptura(CasoModulos):
    def setUp(self):
        super().setUp()
        instrumentos.importar_organigrama(ORGANIGRAMA, self.archivista)
        instrumentos.importar_trd(TRD, self.archivista)
        self.serie = Activity.objects.get(identificador="TRD 1000-24")

    def _archivo(self, nombre="acta.txt", contenido=None):
        return SimpleUploadedFile(nombre, (contenido or TEXTO).encode())

    def _cargar(self, **datos):
        base = {"serie_id": self.serie.pk, "archivos": [self._archivo()]}
        base.update(datos)
        return self.client.post(reverse("ingesta"), base)


class IngestaTest(CasoCaptura):
    def test_requiere_sesion(self):
        self.assertEqual(self.client.get(reverse("ingesta")).status_code, 302)

    def test_solo_el_rol_archivista_ingesta(self):
        for usuario in (self.revisor, self.consulta):
            self.client.force_login(usuario)
            resp = self.client.get(reverse("ingesta"), follow=True)
            self.assertContains(resp, "requiere el rol archivista")
            self.assertNotContains(resp, "Serie o subserie de la TRD")

    def test_paso_1_busca_la_serie_por_nombre_codigo_u_oficina(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ingesta"), {"q": "petici"})
        self.assertContains(resp, "Derechos de petición · Despacho del Ministro")
        self.assertNotContains(resp, "Actas · Grupo")
        resp = self.client.get(reverse("ingesta"), {"q": "4106-10"})
        self.assertContains(resp, "Actas · Grupo de Gestión Documental")
        resp = self.client.get(reverse("ingesta"), {"serie": self.serie.pk})
        self.assertContains(resp, "oficina productora: Despacho del Ministro")
        self.assertContains(resp, "gestión 3 años · central 7 años · Selección")
        self.assertContains(resp, "Expediente al que pertenece")
        self.assertContains(resp, "Arrastra archivos")

    def test_sin_series_cargadas_lo_dice(self):
        Activity.objects.all().delete()
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ingesta"))
        self.assertContains(resp, "Todavía no hay series de la TRD cargadas")

    def test_cargar_crea_expediente_en_la_cadena_fondo_seccion_serie_y_documentos(self):
        self.client.force_login(self.archivista)
        resp = self._cargar(expediente_nuevo="Petición 2026-0412", expediente_codigo="1000-24-0412", fecha_apertura="2026-03-01",
                            archivos=[self._archivo("a.txt"), self._archivo("b.txt")])
        self.assertEqual(resp.status_code, 200)
        expediente = RecordSet.objects.get(nombre="Petición 2026-0412")
        self.assertEqual(expediente.tipo_conjunto, "expediente")
        self.assertEqual(expediente.identificador, "1000-24-0412")
        self.assertEqual(str(expediente.fecha_apertura), "2026-03-01")
        self.assertEqual(expediente.ruta_texto(), "Ministerio de Ambiente > Despacho del Ministro > Derechos de petición > Petición 2026-0412")
        serie = expediente.padre
        self.assertEqual(serie.tipo_conjunto, "serie")
        self.assertEqual(serie.actividad, self.serie)
        self.assertEqual(expediente.mandato().identificador, "TRD 1000-24")
        # relaciones RiC verificadas: R024 en la cadena, R033 serie -> actividad, R026 procedencia
        ct = lambda m: __import__("django.contrib.contenttypes.models", fromlist=["ContentType"]).ContentType.objects.get_for_model(m)
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R024", origen_object_id=serie.pk, destino_object_id=expediente.pk).exists())
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R033", origen_object_id=serie.pk, destino_object_id=self.serie.pk).exists())
        oficina = CorporateBody.objects.get(identificador="1000")
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R026", origen_object_id=serie.pk, destino_object_id=oficina.pk, destino_content_type=ct(CorporateBody)).exists())
        # cada archivo es un documento del expediente, con su huella y su evento
        documentos = Record.objects.filter(record_set=expediente).order_by("nombre")
        self.assertEqual([d.nombre for d in documentos], ["a", "b"])
        inst = Instantiation.objects.get(nombre="a.txt")
        self.assertEqual(len(inst.sha256), 64)  # RF-M1-02
        self.assertEqual(inst.formato, "txt")  # RF-M1-03
        self.assertEqual(inst.creado_por, self.archivista)
        evento = EventoRiC.objects.get(instanciacion=inst, tipo=EventoRiC.Tipo.INGESTA)  # RF-M1-04
        self.assertEqual(evento.agente, "archivista")
        self.assertEqual(evento.detalle["expediente"], "Petición 2026-0412")
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R024", origen_object_id=expediente.pk, destino_object_id=documentos[0].pk).exists())
        # el preprocesamiento corre solo al cargar
        self.assertGreater(inst.paginas.count(), 0)
        self.assertContains(resp, "SHA-256 ✓")
        self.assertContains(resp, "texto listo")
        self.assertContains(resp, "Expediente «Petición 2026-0412» creado")

    def test_cargar_a_un_expediente_existente_y_partes_de_un_mismo_documento(self):
        expediente, _ = clasificacion.crear_expediente(self.serie, "Lote", self.archivista)
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ingesta"), {"serie": self.serie.pk})
        self.assertContains(resp, "<option value=\"%d\"" % expediente.pk)
        self._cargar(expediente_id=expediente.pk, un_solo_documento="1", nombre_documento="Oficio escaneado",
                     archivos=[self._archivo("p1.txt"), self._archivo("p2.txt")])
        self.assertEqual(Record.objects.filter(record_set=expediente).count(), 1)
        documento = Record.objects.get(nombre="Oficio escaneado")
        self.assertEqual(documento.instanciaciones.count(), 2)
        self.assertEqual(RecordSet.objects.filter(tipo_conjunto="expediente").count(), 1)

    def test_carpeta_cargada_es_el_expediente(self):
        self.client.force_login(self.archivista)
        self._cargar(archivos=[self._archivo("x.txt"), self._archivo("y.txt"), self._archivo("z.txt")],
                     rutas=["Peticiones/Exp 0001/x.txt", "Peticiones/Exp 0001/y.txt", "Peticiones/Exp 0002/z.txt"])
        self.assertEqual(set(RecordSet.objects.filter(tipo_conjunto="expediente").values_list("nombre", flat=True)), {"Exp 0001", "Exp 0002"})
        self.assertEqual(Record.objects.get(nombre="z").record_set.nombre, "Exp 0002")

    def test_formato_no_soportado_se_rechaza_antes_de_guardar(self):
        self.client.force_login(self.archivista)
        resp = self._cargar(expediente_nuevo="Audio", archivos=[self._archivo("nota.mp3", "ID3")])
        self.assertContains(resp, "no soportado")
        self.assertFalse(Instantiation.objects.exists())
        self.assertFalse(RecordSet.objects.filter(nombre="Audio").exists())

    @override_settings(RICORA_TAMANO_MAXIMO_MB=0)
    def test_archivo_demasiado_grande_se_rechaza(self):
        self.client.force_login(self.archivista)
        resp = self._cargar(expediente_nuevo="Grande")
        self.assertContains(resp, "el máximo es 0 MB")
        self.assertFalse(Instantiation.objects.exists())

    def test_sin_serie_expediente_o_archivo_avisa(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("ingesta"), {"archivos": [self._archivo()]})
        self.assertContains(resp, "Elija primero la serie")
        resp = self._cargar()
        self.assertContains(resp, "Indique a qué expediente pertenece")
        resp = self._cargar(expediente_nuevo="Algo", archivos=[])
        self.assertContains(resp, "Seleccione al menos un archivo")
        self.assertFalse(Instantiation.objects.exists())

    def test_reescaneo_se_carga_sobre_el_mismo_documento(self):
        record, inst = self.documento()
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ingesta"), {"reemplaza": inst.pk})
        self.assertContains(resp, "Reescaneo pedido para")
        self.client.post(reverse("ingesta"), {"reemplaza_id": inst.pk, "archivos": [self._archivo("acta_v2.txt")]})
        nueva = Instantiation.objects.get(nombre="acta_v2.txt")
        self.assertEqual(nueva.record_resource_id, record.pk)
        self.assertEqual(nueva.instanciacion_origen, inst)


class ClasificacionTest(CasoCaptura):
    def test_fondo_seccion_y_serie_se_crean_una_sola_vez(self):
        a, _ = clasificacion.crear_expediente(self.serie, "Uno", self.archivista)
        b, _ = clasificacion.crear_expediente(self.serie, "Dos", self.archivista)
        self.assertEqual(a.padre, b.padre)
        self.assertEqual(RecordSet.objects.filter(tipo_conjunto="fondo").count(), 1)
        self.assertEqual(RecordSet.objects.filter(tipo_conjunto="seccion").count(), 1)
        self.assertEqual(RecordSet.objects.filter(tipo_conjunto="serie").count(), 1)
        otra = Activity.objects.get(identificador="TRD 4106-10")
        c, _ = clasificacion.crear_expediente(otra, "Tres", self.archivista)
        self.assertEqual(c.padre.padre.nombre, "Grupo de Gestión Documental")
        self.assertEqual(c.padre.padre.padre, a.padre.padre.padre)  # mismo fondo
        mismo, creado = clasificacion.crear_expediente(self.serie, "Uno", self.archivista)
        self.assertEqual(mismo, a)
        self.assertFalse(creado)

    def test_subserie_toma_su_tipo_del_mandato(self):
        instrumentos.importar_trd("Código oficina;Oficina;Código serie;Código subserie;Serie;Subserie;Tipos documentales;Retención gestión;Retención central;Disposición final\n1000;Despacho del Ministro;10;2;ACTAS;Actas de comité;Acta;2;8;CT\n", self.archivista)
        sub = Activity.objects.get(identificador="TRD 1000-10.2")
        e, _ = clasificacion.crear_expediente(sub, "Comité 1", self.archivista)
        self.assertEqual(e.padre.tipo_conjunto, "subserie")
        self.assertEqual(e.serie(), e.padre)

    def test_expediente_de_documento_por_fk_o_por_r024(self):
        e, _ = clasificacion.crear_expediente(self.serie, "Uno", self.archivista)
        [inst] = clasificacion.registrar_documentos(e, [SimpleUploadedFile("d.txt", b"x")], self.archivista)
        record = Record.objects.get(pk=inst.record_resource_id)
        self.assertEqual(clasificacion.expediente_de(record), e)
        record.record_set = None
        record.save()
        self.assertEqual(clasificacion.expediente_de(record), e)  # queda la R024
