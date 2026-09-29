"""Pantalla de inicio (contexto de la plataforma y tareas del día), menú
lateral a prueba de choques de estilos, paginación «1 de N» de listas
largas y estado de los módulos en Administración."""

from django.urls import reverse

from ric.models import FormaDocumental, Instantiation, Person

from ._ayudas import CasoModulos, candidato


class InicioTest(CasoModulos):
    def test_inicio_explica_la_plataforma_y_el_recorrido(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("inicio"))
        self.assertContains(resp, "Records in Contexts (RiC)")
        for paso in ("Instrumentos", "Captura", "Descripción", "Revisión", "Consulta", "Intercambio"):
            self.assertContains(resp, f"<strong>{paso}</strong>")
        self.assertContains(resp, "La IA propone, la persona decide")

    def test_tareas_del_dia_con_cifras_y_enlaces(self):
        record, inst = self.documento()
        self.proponer(record, candidato())
        Instantiation.objects.filter(pk=inst.pk).update(estado_proceso=Instantiation.EstadoProceso.SIN_ENVIAR)
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("inicio"))
        self.assertContains(resp, "archivo(s) cargados sin enviar al OCR")
        self.assertContains(resp, reverse("analisis_lista"))
        self.assertContains(resp, reverse("revision_lista") + "?filtro=pendientes")

    def test_consulta_ve_el_contexto_sin_tareas_internas(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("inicio"))
        self.assertContains(resp, "Buscar en el catálogo")
        self.assertNotContains(resp, "sin enviar al OCR")
        self.assertNotContains(resp, "relaciones RiC validadas")

    def test_encabezado_sin_codigos_ni_estado_de_validacion(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ingesta"))
        self.assertContains(resp, "<strong>Cargar documentos</strong>")
        self.assertNotContains(resp, "Pendiente de rehacer")
        self.assertNotContains(resp, 'class="estado-modulo')


class NavegacionTest(CasoModulos):
    def test_menu_con_clases_propias_no_choca_con_las_paginas(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("vocabularios_duplicados"))
        self.assertContains(resp, 'class="menu-grupo')
        self.assertNotContains(resp, '<div class="grupo')

    def test_vocabularios_paginados_1_de_n(self):
        for i in range(30):
            FormaDocumental.objects.create(nombre=f"Forma {i:02d}")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("vocabularios"), {"tipo": "formadocumental"})
        self.assertContains(resp, "<strong>1</strong> de 2")
        self.assertContains(resp, "tipo=formadocumental&pagina=2")
        resp = self.client.get(reverse("vocabularios"), {"tipo": "formadocumental", "pagina": 2})
        self.assertContains(resp, "Forma 29")

    def test_panel_por_paginas(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("panel"))
        for titulo in ("Resumen del periodo", "Trabajo en curso", "Actividad y contenido del grafo"):
            self.assertContains(resp, f'data-pagina="{titulo}"')

    def test_estado_de_los_modulos_en_administracion(self):
        self.client.force_login(self.superusuario)
        resp = self.client.get(reverse("admin_usuarios"), {"pestana": "modulos"})
        self.assertContains(resp, "Estado de los módulos")
        self.assertContains(resp, "<code>M11</code>")
        self.assertContains(resp, "Validado")
