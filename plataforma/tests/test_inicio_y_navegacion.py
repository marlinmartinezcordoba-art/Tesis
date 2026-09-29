"""Pantalla de inicio (contexto de la plataforma y tareas del día), menú
lateral a prueba de choques de estilos, paginación «1 de N» de listas
largas y estado de los módulos en Administración."""

from django.urls import reverse

from ric.models import FormaDocumental, Instantiation, Person

from ._ayudas import CasoModulos, candidato


class InicioTest(CasoModulos):
    def test_inicio_es_pantalla_de_trabajo_sin_textos_de_presentacion(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("inicio"))
        self.assertContains(resp, 'role="search"')
        self.assertContains(resp, reverse("catalogo"))
        self.assertContains(resp, "Mi trabajo de hoy")
        self.assertContains(resp, "Requieren atención")
        self.assertNotContains(resp, "Records in Contexts (RiC)")
        self.assertNotContains(resp, "El recorrido de un documento")

    def test_pendientes_con_cifras_y_enlaces(self):
        record, inst = self.documento()
        self.proponer(record, candidato())
        Instantiation.objects.filter(pk=inst.pk).update(estado_proceso=Instantiation.EstadoProceso.SIN_ENVIAR)
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("inicio"))
        self.assertContains(resp, "archivos sin enviar al OCR")
        self.assertContains(resp, reverse("analisis_lista"))
        self.assertContains(resp, reverse("revision_lista") + "?filtro=pendientes")

    def test_ultimos_documentos_con_estado_y_paso_siguiente(self):
        record, _ = self.documento(nombre="Acta del cabildo")
        self.proponer(record, candidato())
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("inicio"))
        self.assertContains(resp, "Acta del cabildo")
        self.assertContains(resp, '<span class="estado en_analisis">En análisis</span>')
        self.assertContains(resp, f'href="{reverse("analisis", args=[record.pk])}">Decidir →')

    def test_consulta_solo_ve_lo_publicado_sin_tareas_internas(self):
        self.documento(nombre="Borrador interno")
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("inicio"))
        self.assertContains(resp, "Últimos documentos publicados")
        self.assertNotContains(resp, "Borrador interno")
        self.assertNotContains(resp, "sin enviar al OCR")

    def test_sin_titulo_repetido_en_la_barra_superior(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ingesta"))
        self.assertNotContains(resp, 'class="topbar-modulo"')
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

    def test_sin_estado_de_los_modulos_en_el_sistema(self):
        self.client.force_login(self.superusuario)
        for resp in (self.client.get(reverse("admin_usuarios")), self.client.get(reverse("admin_usuarios"), {"pestana": "modulos"})):
            self.assertNotContains(resp, "Estado de los módulos")
            self.assertNotContains(resp, "<code>M11</code>")
