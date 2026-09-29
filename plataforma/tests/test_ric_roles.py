"""RF-M11-03: cada acción del sistema restringida según el rol — archivista,
revisor y consulta — y el menú lateral muestra solo los módulos que la
persona puede usar."""

from django.urls import reverse

from ric.models import PropuestaRiC

from ._ayudas import CasoModulos, candidato


class RolesTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()
        [self.propuesta] = self.proponer(self.record, candidato())

    def _get(self, usuario, nombre, *args):
        self.client.force_login(usuario)
        return self.client.get(reverse(nombre, args=args), follow=True)

    def test_consulta_solo_catalogo_exportacion_panel_y_vocabularios(self):
        for nombre in ("catalogo", "exportar", "panel", "vocabularios", "ric_sparql", "ric_evaluacion"):
            self.assertEqual(self._get(self.consulta, nombre).status_code, 200, nombre)
        for nombre, args in (("ingesta", ()), ("preproceso", ()), ("analisis_lista", ()), ("analisis", (self.record.pk,)),
                             ("revision_lista", ()), ("historial", (self.record.pk,)), ("admin_usuarios", ())):
            resp = self._get(self.consulta, nombre, *args)
            self.assertContains(resp, "Esta acción requiere", msg_prefix=nombre)

    def test_consulta_no_decide_propuestas(self):
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("analisis_decidir", args=[self.propuesta.pk]), {"accion": "aceptar"}, follow=True)
        self.assertContains(resp, "requiere el rol archivista")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.PENDIENTE)

    def test_revisor_revisa_pero_no_ingesta(self):
        for nombre, args in (("analisis", (self.record.pk,)), ("analisis_grafo", (self.record.pk,)), ("revision", (self.record.pk,)),
                             ("historial", (self.record.pk,)), ("catalogo", ())):
            self.assertEqual(self._get(self.revisor, nombre, *args).status_code, 200, nombre)
        for nombre in ("ingesta", "preproceso"):
            self.assertContains(self._get(self.revisor, nombre), "requiere el rol archivista")
        self.assertContains(self._get(self.revisor, "admin_usuarios"), "Esta acción requiere")

    def test_archivista_hace_todo_menos_administrar(self):
        for nombre in ("ingesta", "preproceso", "analisis_lista", "revision_lista", "historial_lista", "vocabularios", "catalogo", "exportar", "panel"):
            self.assertEqual(self._get(self.archivista, nombre).status_code, 200, nombre)
        self.assertContains(self._get(self.archivista, "admin_usuarios"), "Esta acción requiere")

    def test_menu_lateral_por_rol(self):
        # Menú por proceso archivístico: seis entradas; Administración solo para el superusuario.
        resp = self._get(self.consulta, "panel")
        self.assertNotContains(resp, "Captura y clasificación")
        self.assertNotContains(resp, ">Descripción<")
        self.assertNotContains(resp, "Valoración y disposición")
        self.assertNotContains(resp, "Panel técnico")
        self.assertContains(resp, "Consulta y exportación")
        self.assertContains(resp, "Instrumentos archivísticos")
        self.assertContains(resp, "Consulta</span>")

        resp = self._get(self.revisor, "panel")
        self.assertNotContains(resp, "Captura y clasificación")
        self.assertContains(resp, ">Descripción<")
        self.assertContains(resp, "Valoración y disposición")

        resp = self._get(self.archivista, "panel")
        self.assertContains(resp, "Captura y clasificación")
        self.assertNotContains(resp, "Panel técnico")  # el menú ya no enlaza al admin de Django
        self.assertNotContains(resp, ">Administración<")

        resp = self._get(self.superusuario, "panel")
        self.assertContains(resp, ">Administración<")

    def test_pestanas_del_proceso(self):
        # Submódulos en el menú lateral, desplegados bajo su proceso, con su número de módulo.
        resp = self._get(self.archivista, "revision_lista")
        self.assertContains(resp, 'class="activo" aria-current="page"><span class="m">M6</span><span>Revisión archivística</span>')
        self.assertContains(resp, "<strong>Revisión archivística</strong>")  # encabezado: la pantalla actual
        self.assertContains(resp, 'class="menu-grupo abierto actual" data-grupo="3"')
        self.assertContains(resp, "<span>Análisis y relaciones</span>")
        self.assertContains(resp, "<span>Trazabilidad y auditoría</span>")
        self.assertNotContains(resp, 'class="pestanas"')
        resp = self._get(self.archivista, "preproceso")
        self.assertContains(resp, '<span class="m">M2</span><span>Preprocesamiento y OCR</span>')
        self.assertContains(resp, "<span>Cargar documentos</span>")
        self.assertNotContains(resp, 'class="estado-modulo')  # el estado de validación vive en Administración

    def test_administracion_en_el_menu_con_modulo_0(self):
        self.client.force_login(self.superusuario)
        resp = self.client.get("/admin/usuarios/?pestana=auditoria")
        self.assertContains(resp, "<strong>Auditoría</strong>")
        self.assertContains(resp, '?pestana=eliminados')
        resp = self.client.get("/admin/usuarios/")
        self.assertContains(resp, "<strong>Usuarios y roles</strong>")

    def test_el_archivo_original_respeta_la_visibilidad_del_rol(self):
        # Módulo 1: antes cualquier sesión descargaba cualquier archivo por su id (RF-M8-04 lo prohíbe).
        self.client.force_login(self.consulta)
        self.assertEqual(self.client.get(reverse("ric_archivo", args=[self.inst.pk])).status_code, 403)
        self.record.publicado = True
        self.record.save()
        self.assertEqual(self.client.get(reverse("ric_archivo", args=[self.inst.pk])).status_code, 200)
        self.client.force_login(self.revisor)
        self.assertEqual(self.client.get(reverse("ric_archivo", args=[self.inst.pk])).status_code, 200)
