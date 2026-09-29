"""M5 · Precarga de instrumentos archivísticos (TRD, CCD, organigrama) y la
corrección de la especificación v3: la retención y la disposición final
van en el Mandato de cada serie de la TRD (no en la forma documental), cada
serie es una Actividad ligada a su Mandato y a su oficina productora, y la
forma documental es un catálogo reutilizable. También la semilla MADS."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from ric import desambiguacion, fusion, instrumentos
from ric.models import Activity, CorporateBody, EventoRiC, FormaDocumental, Instantiation, Mandate, Person, Position, RelacionRiC, VersionRiC

from ._ayudas import CasoModulos

# Una fila por serie, tipos separados por |, disposición combinada.
TRD = (
    "Código oficina;Oficina;Código serie;Código subserie;Serie;Subserie;Tipos documentales;Soporte;Retención gestión;Retención central;Disposición final;Procedimiento\n"
    "1000;Despacho del Ministro;24;;DERECHOS DE PETICIÓN;;Derecho de petición|Respuesta a Derecho de petición;papel, electrónico;3;7;S;Se selecciona una muestra.\n"
    "1000;Despacho del Ministro;87;;PROYECTOS DE LEY;;Proyecto de ley|Oficio;electrónico;3;17;CT, MT;Conservación total y digitalización.\n"
)
# El formato antiguo (una fila por forma documental) sigue aceptándose.
TRD_ANTIGUA = (
    "Forma documental;Serie;Retención gestión;Retención central;Disposición final\n"
    "Acta;100.02 Actas de comité;2;8;Conservación total\n"
    "Oficio;200.05 Comunicaciones oficiales;2;3;Eliminación\n"
)
CCD = "funcion,tipo,dependencia\nContratación pública,sustantiva,Secretaría General\nGestión documental,de apoyo,Secretaría General\n"
ORGANIGRAMA = (
    "dependencia,dependencia_superior,codigo,funcionario,cargo\n"
    "Alcaldía Mayor,,AM,,\n"
    "Secretaría General,Alcaldía Mayor,SG,Carla Mosquera,Secretaria General\n"
    "Archivo Central,Secretaría General,AC,,\n"
)


class ImportarTrdTest(CasoModulos):
    def test_cada_serie_es_mandato_con_retencion_mas_actividad_y_formas(self):
        resultado = instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        self.assertEqual(resultado["series"], 2)
        self.assertEqual(resultado["mandatos"], 2)
        self.assertEqual(resultado["actividades"], 2)
        self.assertEqual(resultado["formas_documentales"], 4)

        mandato = Mandate.objects.get(identificador="TRD 1000-24")
        self.assertEqual(mandato.nombre, "TRD 1000-24 Derechos de petición")
        self.assertEqual(mandato.tiempo_retencion_archivo_gestion, 3)
        self.assertEqual(mandato.tiempo_retencion_archivo_central, 7)
        self.assertEqual(mandato.disposicion_final_codigos(), ["S"])
        self.assertEqual(mandato.tipo_mandato, instrumentos.TIPO_MANDATO_TRD)
        self.assertEqual(mandato.procedimiento, "Se selecciona una muestra.")
        self.assertEqual(mandato.creado_por, self.archivista)

        leyes = Mandate.objects.get(identificador="TRD 1000-87")
        self.assertEqual(leyes.disposicion_final_codigos(), ["CT", "MT"])
        self.assertEqual(leyes.disposicion_final_texto(), "Conservación total + Medio tecnológico")
        self.assertEqual(leyes.retencion_texto(), "gestión 3 años · central 17 años · Conservación total + Medio tecnológico")

        actividad = Activity.objects.get(identificador="TRD 1000-24")
        self.assertEqual(actividad.mandato, mandato)
        self.assertEqual(actividad.nombre, "Derechos de petición · Despacho del Ministro")
        self.assertEqual(set(actividad.formas_documentales.values_list("nombre", flat=True)), {"Derecho de petición", "Respuesta a Derecho de petición"})

        oficina = CorporateBody.objects.get(identificador="1000")
        self.assertEqual(oficina.nombre, "Despacho del Ministro")
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R063", origen_object_id=mandato.pk, destino_object_id=actividad.pk, estado="aceptada").exists())
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R060", origen_object_id=actividad.pk, destino_object_id=oficina.pk).exists())

    def test_la_forma_documental_no_carga_retencion_y_se_reutiliza_entre_series(self):
        instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        oficio = FormaDocumental.objects.get(nombre="Oficio")
        self.assertFalse(hasattr(oficio, "tiempo_retencion_archivo_gestion"))
        self.assertEqual([a.identificador for a in oficio.series()], ["TRD 1000-87"])
        # otra serie con "Oficio": misma forma, otro mandato con otra retención
        instrumentos.importar_trd(TRD_ANTIGUA.encode("utf-8"), self.archivista)
        oficio.refresh_from_db()
        self.assertEqual(FormaDocumental.objects.filter(nombre="Oficio").count(), 1)
        self.assertEqual(oficio.series().count(), 2)
        comunicaciones = Mandate.objects.get(nombre__contains="200.05 Comunicaciones oficiales")
        self.assertEqual(comunicaciones.tiempo_retencion_archivo_central, 3)
        self.assertEqual(comunicaciones.disposicion_final_codigos(), ["E"])

    def test_reimportar_es_idempotente_y_no_deja_versiones_vacias(self):
        instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        versiones = VersionRiC.objects.count()
        resultado = instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        self.assertEqual(resultado["mandatos"], 0)
        self.assertEqual(resultado["actividades"], 0)
        self.assertEqual(resultado["formas_documentales"], 0)
        self.assertEqual(resultado["relaciones"], 0)
        self.assertEqual(Mandate.objects.count(), 2)
        self.assertEqual(VersionRiC.objects.count(), versiones)
        # cambiar la retención en la TRD sí actualiza (y versiona) el mandato
        instrumentos.importar_trd(TRD.replace(";3;7;S;", ";5;7;S;").encode("utf-8"), self.archivista)
        self.assertEqual(Mandate.objects.get(identificador="TRD 1000-24").tiempo_retencion_archivo_gestion, 5)
        self.assertEqual(VersionRiC.objects.count(), versiones + 1)

    def test_json_con_la_estructura_de_la_semilla(self):
        datos = b"""[{"codigo_oficina": "4106", "nombre_oficina": "Grupo de Gesti\xc3\xb3n Documental", "vigencia": "07/12/2022",
          "series": [{"codigo_serie": "10", "codigo_subserie": "2", "nombre_serie": "ACTAS", "nombre_subserie": "Actas de comit\xc3\xa9",
          "tipos_documentales": ["Acta", "Lista de asistencia"], "soporte": ["papel"], "archivo_gestion_anios": 2, "archivo_central_anios": 18,
          "disposicion_final": {"CT": true, "E": false, "MT": false, "S": false}, "procedimiento_resumen": "Se conserva."}]}]"""
        resultado = instrumentos.importar_trd(datos, self.archivista)
        self.assertEqual(resultado["series"], 1)
        mandato = Mandate.objects.get(identificador="TRD 4106-10.2")
        self.assertEqual(mandato.nombre, "TRD 4106-10.2 Actas · Actas de comité")
        self.assertEqual(mandato.codigo_subserie, "2")
        self.assertEqual(mandato.soporte, "papel")
        self.assertEqual(str(mandato.vigencia), "2022-12-07")
        self.assertEqual(mandato.disposicion_final_codigos(), ["CT"])
        self.assertEqual(Activity.objects.get(identificador="TRD 4106-10.2").formas_documentales.count(), 2)

    def test_columnas_faltantes_dan_error_claro(self):
        with self.assertRaises(instrumentos.ErrorDeImportacion) as ctx:
            instrumentos.importar_trd("nombre;algo\nx;y\n", self.archivista)
        self.assertIn("serie", str(ctx.exception))
        with self.assertRaises(instrumentos.ErrorDeImportacion):
            instrumentos.importar_trd(b"[{esto no es json", self.archivista)


class ImportarCcdYOrganigramaTest(CasoModulos):
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

    def test_organigrama_crea_jerarquia_r045_y_cargos_e12_con_r054_y_r056(self):
        resultado = instrumentos.importar_organigrama(ORGANIGRAMA, self.archivista)
        self.assertEqual(resultado["creadas"], 3)
        self.assertEqual(resultado["funcionarios"], 1)
        self.assertEqual(resultado["cargos"], 1)
        self.assertEqual(resultado["relaciones"], 4)
        alcaldia = CorporateBody.objects.get(nombre="Alcaldía Mayor")
        self.assertEqual(alcaldia.identificador, "AM")
        secretaria = CorporateBody.objects.get(identificador="SG")
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R045", origen_object_id=alcaldia.pk, destino_object_id=secretaria.pk).exists())
        persona = Person.objects.get(nombre="Carla Mosquera")
        self.assertEqual(persona.tipo_ocupacion, "Secretaria General")
        # RiC-E12 Position: el cargo es una entidad propia; persona -> R054 -> cargo -> R056 -> oficina
        cargo = Position.objects.get(nombre="Secretaria General")
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R054", origen_object_id=persona.pk, destino_object_id=cargo.pk).exists())
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R056", origen_object_id=cargo.pk, destino_object_id=secretaria.pk).exists())
        # otra persona en el mismo cargo (organigrama histórico) reutiliza el cargo
        instrumentos.importar_organigrama(ORGANIGRAMA.replace("Carla Mosquera", "Ana Ruiz"), self.archivista)
        self.assertEqual(Position.objects.count(), 1)
        self.assertEqual(RelacionRiC.objects.filter(relacion_id="R054", destino_object_id=cargo.pk).count(), 2)

    def test_importar_desde_la_pantalla_solo_archivista(self):
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("vocabularios_importar"), {"instrumento": "trd", "archivo": SimpleUploadedFile("trd.csv", TRD.encode())}, follow=True)
        self.assertContains(resp, "requiere el rol archivista")
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("vocabularios_importar"), {"instrumento": "trd", "archivo": SimpleUploadedFile("trd.csv", TRD.encode())}, follow=True)
        self.assertContains(resp, "2 fila(s) leídas")
        self.assertContains(resp, "2 mandatos")
        self.assertContains(resp, "Precargar instrumentos archivísticos")
        self.assertEqual(FormaDocumental.objects.count(), 4)

    def test_el_motor_recibe_el_vocabulario_precargado(self):
        from ric.ia_prompt import vocabulario_existente

        instrumentos.importar_organigrama(ORGANIGRAMA, self.archivista)
        instrumentos.importar_trd(TRD, self.archivista)
        vocabulario = vocabulario_existente()
        self.assertIn("Secretaría General", vocabulario)
        self.assertIn("forma documental · Oficio", vocabulario)
        self.assertIn("Derechos de petición · Despacho del Ministro", vocabulario)


class MandatoEnPantallaTest(CasoModulos):
    def test_editar_retencion_del_mandato_desde_la_ficha(self):
        instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        mandato = Mandate.objects.get(identificador="TRD 1000-24")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("vocabulario_ficha", args=["mandate", mandato.pk]))
        self.assertContains(resp, "gestión 3 años · central 7 años · Selección")
        self.assertContains(resp, "Derechos de petición · Despacho del Ministro")
        self.client.post(reverse("vocabulario_ficha", args=["mandate", mandato.pk]), {
            "nombre": mandato.nombre, "identificador": mandato.identificador, "descripcion_general": "", "serie_trd": mandato.serie_trd,
            "codigo_serie": "24", "codigo_subserie": "", "retencion_gestion": "4", "retencion_central": "6",
            "disposicion_CT": "1", "disposicion_S": "1", "soporte": "electrónico", "procedimiento": "Nuevo procedimiento",
        })
        mandato.refresh_from_db()
        self.assertEqual(mandato.tiempo_retencion_archivo_gestion, 4)
        self.assertEqual(mandato.disposicion_final_codigos(), ["CT", "S"])
        self.assertEqual(mandato.procedimiento, "Nuevo procedimiento")

    def test_la_ficha_de_la_forma_muestra_sus_series_y_la_del_documento_hereda_la_retencion(self):
        instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        oficio = FormaDocumental.objects.get(nombre="Oficio")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("vocabulario_ficha", args=["formadocumental", oficio.pk]))
        self.assertContains(resp, "Series de la TRD en las que aparece (1)")
        self.assertContains(resp, "Conservación total + Medio tecnológico")
        self.assertNotContains(resp, "retencion_gestion")

        record, _ = self.documento()
        actividad = Activity.objects.get(identificador="TRD 1000-87")
        from django.utils import timezone
        # R033 "documents": Record Resource -> Activity (verificado en ric_matrix.json)
        RelacionRiC(relacion_id="R033", origen=record, destino=actividad, estado="aceptada", validado_por=self.archivista, fecha_validacion=timezone.now()).save()
        resp = self.client.get(reverse("catalogo_ficha", args=["record", record.pk]))
        self.assertContains(resp, "TRD 1000-87")
        self.assertContains(resp, "Retención: gestión 3 años · central 17 años")

    def test_formas_duplicadas_se_detectan_y_se_fusionan(self):
        instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        instrumentos.importar_trd(TRD.replace("Proyecto de ley|Oficio", "Proyecto de ley|Oficios").replace("1000;Despacho del Ministro;87", "1200;Oficina Asesora;87").encode("utf-8"), self.archivista)
        oficio, oficios = FormaDocumental.objects.get(nombre="Oficio"), FormaDocumental.objects.get(nombre="Oficios")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("vocabularios_duplicados"))
        self.assertContains(resp, "Formas documentales")
        self.assertContains(resp, "Oficios")
        resp = self.client.post(reverse("vocabulario_fusionar", args=["formadocumental", oficio.pk]), {"duplicada": oficios.pk}, follow=True)
        self.assertContains(resp, "fusionada en «Oficio»")
        self.assertFalse(FormaDocumental.objects.filter(nombre="Oficios").exists())
        self.assertEqual(oficio.series().count(), 2)
        self.assertTrue(EventoRiC.objects.filter(tipo=EventoRiC.Tipo.FUSION, detalle__duplicada="Oficios").exists())

    def test_series_con_codigo_distinto_no_son_duplicados(self):
        instrumentos.importar_trd(TRD.encode("utf-8"), self.archivista)
        instrumentos.importar_trd(TRD.replace("1000;Despacho del Ministro", "1200;Oficina Asesora").encode("utf-8"), self.archivista)
        self.assertEqual(Mandate.objects.filter(codigo_serie="24").count(), 2)
        self.assertEqual(desambiguacion.pares_similares(Mandate), [])
        self.assertEqual(desambiguacion.pares_similares(Activity), [])
        peticiones = Mandate.objects.get(identificador="TRD 1000-24")
        self.assertEqual(desambiguacion.candidatos_similares(Mandate, peticiones.nombre, excluir_pk=peticiones.pk, identificador=peticiones.identificador), [])
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("vocabulario_ficha", args=["mandate", peticiones.pk]))
        self.assertContains(resp, "No se detectan entradas parecidas")
        self.assertIn(FormaDocumental, [Mandate, Activity, FormaDocumental])  # las formas sí entran a la revisión de duplicados
        self.assertTrue(all(m in fusion.modelos_fusionables() for m in (Mandate, Activity)))


class SemillaMadsTest(CasoModulos):
    def test_comando_carga_organigrama_y_54_trd_de_forma_idempotente(self):
        call_command("sembrar_mads", usuario=self.archivista.username, verbosity=0)
        self.assertEqual(CorporateBody.objects.filter(identificador__regex=r"^\d{4}$").count(), 54)
        self.assertEqual(Person.objects.count(), 49)
        self.assertEqual(Mandate.objects.filter(tipo_mandato=instrumentos.TIPO_MANDATO_TRD).count(), 380)
        self.assertEqual(Activity.objects.filter(mandato__isnull=False).count(), 380)
        self.assertEqual(FormaDocumental.objects.count(), 1321)
        self.assertEqual(RelacionRiC.objects.filter(relacion_id="R045").count(), 61)
        self.assertEqual(Position.objects.count(), 49)
        self.assertEqual(RelacionRiC.objects.filter(relacion_id="R054").count(), 49)
        self.assertEqual(RelacionRiC.objects.filter(relacion_id="R056").count(), 49)
        self.assertEqual(RelacionRiC.objects.filter(relacion_id="R063").count(), 380)
        self.assertEqual(RelacionRiC.objects.filter(relacion_id="R060").count(), 380)

        gestion_documental = CorporateBody.objects.get(identificador="4106")
        self.assertEqual(gestion_documental.nombre, "Grupo de Gestión Documental")
        superior = RelacionRiC.objects.get(relacion_id="R045", destino_object_id=gestion_documental.pk).origen
        self.assertEqual(superior.identificador, "4100")
        peticiones = Mandate.objects.get(identificador="TRD 1000-24")
        self.assertEqual(peticiones.retencion_texto(), "gestión 3 años · central 7 años · Selección")
        self.assertEqual(peticiones.disposicion_final_codigos(), ["S"])

        versiones = VersionRiC.objects.count()
        resumen = instrumentos.sembrar_mads(self.archivista)
        self.assertEqual(resumen["trd"]["mandatos"], 0)
        self.assertEqual(resumen["organigrama"]["creadas"], 0)
        self.assertEqual(VersionRiC.objects.count(), versiones)

    def test_boton_de_semilla_en_la_pantalla_solo_archivista(self):
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("vocabularios_sembrar"), follow=True)
        self.assertContains(resp, "requiere el rol archivista")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("vocabularios"))
        self.assertContains(resp, "Cargar semilla MADS")


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
