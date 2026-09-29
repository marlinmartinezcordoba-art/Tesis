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
        resp = self._get(self.consulta, "panel")
        self.assertNotContains(resp, "Ingesta de documentos")
        self.assertNotContains(resp, "Revisión archivística")
        self.assertNotContains(resp, "Panel técnico")
        self.assertContains(resp, "Catálogo y consulta")
        self.assertContains(resp, "Consulta</span>")

        resp = self._get(self.revisor, "panel")
        self.assertNotContains(resp, "Ingesta de documentos")
        self.assertContains(resp, "Revisión archivística")
        self.assertContains(resp, "Motor de análisis RiC")

        resp = self._get(self.archivista, "panel")
        self.assertContains(resp, "Ingesta de documentos")
        self.assertNotContains(resp, "Panel técnico")  # el menú ya no enlaza al admin de Django
        self.assertNotContains(resp, "Administración y seguridad")

        resp = self._get(self.superusuario, "panel")
        self.assertContains(resp, "Administración y seguridad")

    def test_el_archivo_original_exige_sesion_pero_no_rol(self):
        self.client.force_login(self.consulta)
        self.assertEqual(self.client.get(reverse("ric_archivo", args=[self.inst.pk])).status_code, 200)
