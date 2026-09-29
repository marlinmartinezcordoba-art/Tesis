"""M3 · Motor de análisis RiC (/analisis/:id): RF-M3-01 a RF-M3-04 y los
criterios de calidad CC-01, CC-03, CC-04, CC-05, CC-06 aplicados a cada
propuesta antes de guardarla."""

from unittest.mock import patch

from django.urls import reverse

from ric import flujo
from ric.models import ConfiguracionSistema, CorporateBody, Date, EventoRiC, FormaDocumental, Place, PropuestaRiC, RelacionRiC

from ._ayudas import CasoModulos, ProveedorFalso, candidato


class AnalisisPantallaTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()
        [self.propuesta] = self.proponer(self.record, candidato())

    def test_roles(self):
        self.client.force_login(self.consulta)
        self.assertContains(self.client.get(reverse("analisis", args=[self.record.pk]), follow=True), "requiere el rol archivista o revisor")
        for usuario in (self.archivista, self.revisor):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse("analisis", args=[self.record.pk])).status_code, 200)

    def test_texto_con_fragmento_resaltado_y_ficha_agrupada_por_clase(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("analisis", args=[self.record.pk]))
        self.assertContains(resp, f'<mark id="ev-{self.propuesta.pk}" class="ev clase-agente"')  # RF-M3-02
        self.assertContains(resp, "Agente")  # RF-M3-01: agrupadas por clase
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertContains(resp, 'name="entidad_nombre_final"')  # RF-M3-04
        self.assertContains(resp, "Continuar a relaciones")
        self.assertContains(resp, "ver el documento original")

    def test_lista_de_documentos_con_su_paso(self):
        self.client.force_login(self.revisor)
        resp = self.client.get(reverse("analisis_lista"))
        self.assertContains(resp, "Acta")
        self.assertContains(resp, "En análisis")

    def test_el_revisor_ve_pero_no_decide(self):
        self.client.force_login(self.revisor)
        resp = self.client.get(reverse("analisis", args=[self.record.pk]))
        self.assertContains(resp, "Solo una cuenta archivista puede decidir")
        resp = self.client.post(reverse("analisis_decidir", args=[self.propuesta.pk]), {"accion": "aceptar"}, follow=True)
        self.assertContains(resp, "requiere el rol archivista")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.PENDIENTE)


class DecidirPropuestaTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()
        [self.propuesta] = self.proponer(self.record, candidato())
        self.client.force_login(self.archivista)

    def _decidir(self, **datos):
        return self.client.post(reverse("analisis_decidir", args=[self.propuesta.pk]), datos, follow=True)

    def test_aceptar_crea_entidad_y_relacion_con_el_usuario(self):
        resp = self._decidir(accion="aceptar")
        self.assertContains(resp, "aceptada y agregada al grafo")
        cabildo = CorporateBody.objects.get(nombre="Cabildo de Santafé")
        self.assertEqual(cabildo.creado_por, self.archivista)  # RF-M5-04
        rel = RelacionRiC.objects.get(relacion_id="R027")
        self.assertEqual(rel.destino, cabildo)
        self.assertEqual(rel.origen_decision, "propuesta_ia")  # CC-08
        self.assertRedirects(resp, reverse("analisis", args=[self.record.pk]), fetch_redirect_response=False)

    def test_corregir_el_nombre_antes_de_aceptar(self):
        resp = self._decidir(accion="aceptar", entidad_nombre_final="Cabildo de Santa Fe de Bogotá")
        self.assertContains(resp, "corregido de")
        self.assertTrue(CorporateBody.objects.filter(nombre="Cabildo de Santa Fe de Bogotá").exists())
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.MODIFICADA)

    def test_vincular_a_una_entrada_existente_no_duplica(self):
        existente = CorporateBody.objects.create(nombre="Cabildo de Santa Fe")
        resp = self._decidir(accion="vincular", entidad_existente=existente.pk)
        self.assertContains(resp, "sin crear un duplicado")
        self.assertEqual(CorporateBody.objects.count(), 1)
        self.assertEqual(RelacionRiC.objects.get(relacion_id="R027").destino, existente)

    def test_rechazar_exige_motivo(self):
        resp = self._decidir(accion="rechazar", motivo="")
        self.assertContains(resp, "Indique el motivo del rechazo")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.PENDIENTE)
        self._decidir(accion="rechazar", motivo="No es el productor.")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.RECHAZADA)
        self.assertEqual(self.propuesta.motivo_decision, "No es el productor.")
        self.assertFalse(RelacionRiC.objects.exists())  # CC-02: rechazada, pero conservada como registro


class CriteriosDeCalidadTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()

    def test_cc01_evidencia_inventada_se_descarta_pero_queda_registrada(self):
        [p] = self.proponer(self.record, candidato(evidencia="esto no está en el texto"))
        self.assertEqual(p.estado, PropuestaRiC.Estado.RECHAZADA)
        self.assertIn("no aparece en el texto", p.motivo_decision)
        self.assertFalse(p.evidencia.verificada)

    def test_cc06_mandato_sin_cita_textual_se_descarta(self):
        [p] = self.proponer(self.record, candidato(relacion_id="R019", entidad_tipo="E17", entidad_nombre="Ley 594", evidencia="Ley 594 de 2000"))
        self.assertIn("cita textual explícita", p.motivo_decision)

    def test_cc03_procedencia_con_rol_mencionado_se_descarta(self):
        [p] = self.proponer(self.record, candidato(datos_extra={"rol_en_el_documento": "mencionado"}))
        self.assertEqual(p.estado, PropuestaRiC.Estado.RECHAZADA)
        self.assertIn("agente productor o firmante", p.motivo_decision)
        [ok] = self.proponer(self.record, candidato(entidad_nombre="Cabildo", evidencia="Cabildo", datos_extra={"rol_en_el_documento": "firmante"}))
        self.assertEqual(ok.estado, PropuestaRiC.Estado.PENDIENTE)

    def test_cc04_baja_confianza_se_marca_en_la_ficha_y_va_primero(self):
        self.proponer(self.record, candidato(confianza=0.4), candidato(entidad_nombre="José Acevedo y Gómez", entidad_tipo="E08", evidencia="José Acevedo y Gómez", confianza=0.9))
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("analisis", args=[self.record.pk]))
        self.assertContains(resp, "baja confianza")
        contenido = resp.content.decode()
        self.assertLess(contenido.index("Cabildo de Santafé</h4>"), contenido.index("José Acevedo y Gómez</h4>"))

    def test_cc05_entrada_existente_se_sugiere_para_vincular(self):
        existente = CorporateBody.objects.create(nombre="Cabildo de Santafe")  # sin tilde: similar, no idéntica
        [p] = self.proponer(self.record, candidato())
        self.assertEqual(p.datos_extra["entidad_sugerida_id"], existente.pk)
        self.assertIn("reutilizar la entrada", p.justificacion)
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("analisis", args=[self.record.pk]))
        self.assertContains(resp, "Ya existe en vocabularios y autoridades")
        self.assertContains(resp, f'<option value="{existente.pk}" selected')

    def test_cc05_vocabulario_id_del_motor_manda(self):
        existente = CorporateBody.objects.create(nombre="Muy distinto")
        [p] = self.proponer(self.record, candidato(vocabulario_id=existente.pk))
        self.assertEqual(p.datos_extra["entidad_sugerida_id"], existente.pk)

    def test_cc07_fecha_aceptada_conserva_texto_original_normalizado_y_precision(self):
        # R080 "is creation date of" va de Date a Record Resource en RiC-CM:
        # el motor la propone desde el documento y al aceptar se guarda en
        # el sentido correcto (la fecha como origen).
        [p] = self.proponer(self.record, candidato(
            relacion_id="R080", entidad_tipo="E18", entidad_nombre="20 de julio de 1810", evidencia="20 de julio de 1810",
            datos_extra={"fecha_texto_original": "20 de julio de 1810", "fecha_normalizada": "1810-07-20", "precision_fecha": "exacta", "tipo_fecha": "creacion"},
        ))
        self.assertEqual(p.estado, PropuestaRiC.Estado.PENDIENTE)
        self.assertTrue(p.datos_extra["inversa"])
        p.validar(self.archivista, aceptar=True)
        fecha = Date.objects.get()
        self.assertEqual(fecha.expresion, "20 de julio de 1810")
        self.assertEqual(fecha.valor_normalizado, "1810-07-20")
        self.assertEqual(fecha.calificador, "exacta")
        rel = RelacionRiC.objects.get(relacion_id="R080")
        self.assertEqual(rel.origen, fecha)
        self.assertEqual(rel.destino, self.record)
        self.client.force_login(self.archivista)
        self.assertContains(self.client.get(reverse("revision", args=[self.record.pk])), "20 de julio de 1810")
        datos = self.client.get(reverse("analisis_grafo_datos", args=[self.record.pk])).json()
        self.assertTrue(any(e["data"]["relacion_id"] == "R080" for e in datos["edges"]))

    def test_cc02_descripcion_incompleta_se_senala_sin_bloquear(self):
        [p] = self.proponer(self.record, candidato())  # solo un agente: faltan forma documental y fecha
        self.assertEqual(flujo.clases_faltantes(self.record), ["forma documental", "fecha"])
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("analisis", args=[self.record.pk]))
        self.assertContains(resp, "⚠ Descripción incompleta")
        self.assertContains(resp, "forma documental, fecha")
        resp = self.client.get(reverse("panel"))
        self.assertContains(resp, "⚠ Descripción incompleta")
        self.client.post(reverse("analisis_forma", args=[self.record.pk]), {"forma_nombre": "Acta"})
        self.proponer(self.record, candidato(relacion_id="R080", entidad_tipo="E18", entidad_nombre="20 de julio de 1810", evidencia="20 de julio de 1810"))
        self.record.refresh_from_db()
        self.assertEqual(flujo.clases_faltantes(self.record), [])

    def test_cc07_fecha_de_creacion_posterior_a_la_ingesta_es_conflicto(self):
        [p] = self.proponer(self.record, candidato(
            relacion_id="R080", entidad_tipo="E18", entidad_nombre="2099", evidencia="1810",
            datos_extra={"fecha_normalizada": "2099-01-01", "tipo_fecha": "creacion"},
        ))
        self.assertIn("posterior a la ingesta", p.datos_extra["conflicto_temporal"])
        self.assertIn("Conflicto de fechas", p.justificacion)
        self.assertEqual(p.estado, PropuestaRiC.Estado.PENDIENTE)  # se marca, la persona decide
        [q] = self.proponer(self.record, candidato(
            relacion_id="R080", entidad_tipo="E18", entidad_nombre="fecha rara", evidencia="1810",
            datos_extra={"fecha_normalizada": "20 de julio", "tipo_fecha": "creacion"},
        ))
        self.assertIn("no es una fecha ISO 8601", q.datos_extra["conflicto_temporal"])
        self.client.force_login(self.archivista)
        self.assertContains(self.client.get(reverse("analisis", args=[self.record.pk])), "Conflicto temporal")

    def test_lugar_aceptado_guarda_tipo_y_codigo_dane(self):
        [p] = self.proponer(self.record, candidato(
            relacion_id="R019", entidad_tipo="E22", entidad_nombre="Bogotá", evidencia="Bogotá",
            datos_extra={"tipo_lugar": "municipio", "codigo_dane": "11001"},
        ))
        p.validar(self.archivista, aceptar=True)
        lugar = Place.objects.get()
        self.assertEqual(lugar.tipo_lugar, "municipio")
        self.assertEqual(lugar.identificador, "DANE:11001")

    def test_rol_del_agente_queda_como_descripcion_de_la_relacion(self):
        [p] = self.proponer(self.record, candidato(datos_extra={"rol_en_el_documento": "firmante"}))
        p.validar(self.archivista, aceptar=True)
        self.assertEqual(RelacionRiC.objects.get().descripcion_relacion, "Rol en el documento: firmante.")

    def test_umbral_de_confianza_configurable(self):
        config = ConfiguracionSistema.actual()
        config.umbral_confianza_revision = 0.95
        config.save()
        self.proponer(self.record, candidato(confianza=0.9))
        self.client.force_login(self.archivista)
        self.assertContains(self.client.get(reverse("analisis", args=[self.record.pk])), "baja confianza")


class GenerarPropuestaTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()
        self.client.force_login(self.archivista)

    def test_sin_proveedor_activo_lo_dice(self):
        resp = self.client.post(reverse("analisis_generar", args=[self.record.pk]), follow=True)
        self.assertContains(resp, "No hay un proveedor de IA activo")

    def test_con_proveedor_crea_propuestas_y_no_repite_las_ya_existentes(self):
        proveedor = ProveedorFalso([candidato()], advertencias=["No se encontró evidencia de lugar."], forma_documental={"nombre_tipo": "acta", "definicion": "", "fragmento_fuente": "Acta de la sesión", "confianza": 0.9, "vocabulario_id": None})
        with patch("ric.proveedores.proveedor_activo", return_value=proveedor):
            resp = self.client.post(reverse("analisis_generar", args=[self.record.pk]), follow=True)
            self.assertContains(resp, "1 propuesta(s) nueva(s)")
            self.assertContains(resp, "No se encontró evidencia de lugar.")  # advertencias del motor
            self.assertContains(resp, "El motor sugiere <strong>acta</strong>")
            resp = self.client.post(reverse("analisis_generar", args=[self.record.pk]), follow=True)
            self.assertContains(resp, "no propuso nada nuevo")
        self.assertEqual(PropuestaRiC.objects.count(), 1)
        self.assertTrue(EventoRiC.objects.filter(tipo=EventoRiC.Tipo.PROPUESTA_IA, detalle__resumen_analisis=True).exists())

    def test_asignar_forma_documental_crea_la_entrada_controlada(self):
        resp = self.client.post(reverse("analisis_forma", args=[self.record.pk]), {"forma_nombre": "Acta"}, follow=True)
        self.assertContains(resp, "Forma documental: Acta")
        self.record.refresh_from_db()
        forma = FormaDocumental.objects.get(nombre="Acta")
        self.assertEqual(self.record.forma_documental, forma)
        self.assertEqual(self.record.tipo_forma_documental, "Acta")
        self.assertEqual(forma.creado_por, self.archivista)
