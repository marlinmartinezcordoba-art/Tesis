"""
Cierre de la auditoría de conformidad RiC del 3 de octubre de 2026 en el
panel de hallazgos del módulo de auditoría.

- Siembra: los 69 hallazgos no conformes de la auditoría entran al panel
  como «abiertos», con su identificador (`referencia`, p. ej. «INS-02»),
  su título y su descripción originales, que no se editan después
  (app/recursos/auditoria-ric/hallazgos.json).
- Cierre: CIERRES dice qué hallazgo se corrigió, cuándo, con qué evidencia
  y qué pruebas automatizadas lo cubren. Al desplegar, `sincronizar()` lo
  aplica: el hallazgo pasa a «cerrado» con su fecha y su acción, y el
  cambio queda en la auditoría como cualquier otro. Una prueba exige que
  cada prueba citada exista de verdad (tests/test_cierre_auditoria.py).

Se ejecuta en el arranque del contenedor, después de las migraciones:
`python -m app.servicios.cierre_auditoria`.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.hallazgo import HallazgoConformidad
from app.servicios.auditoria import registrar

DATOS = Path(__file__).resolve().parent.parent / "recursos" / "auditoria-ric" / "hallazgos.json"
ABIERTO_EN = date(2026, 10, 3)


@dataclass(frozen=True)
class Cierre:
    fecha: date
    evidencia: str  # qué se cambió y dónde (archivo), en una o dos frases
    pruebas: tuple[str, ...]  # «tests/archivo.py::funcion» que lo cubren
    # Lo que el código no puede resolver solo (infraestructura, una decisión
    # de la autora). Con pendiente, el hallazgo queda «en corrección», no
    # «cerrado»: el panel no declara más de lo que se hizo.
    pendiente: str | None = None


CIERRES: dict[str, Cierre] = {
    "INS-02": Cierre(
        date(2026, 10, 3),
        "La reserva se aplica en todos los caminos laterales: el RDF y /id/ excluyen los archivos con declaración "
        "propia o heredada y las entidades que solo citan documentos no exportados (exportacion_rico."
        "_entidades_vedadas); la ficha de consulta solo nombra partes, secuencia y archivos visibles (consulta."
        "ficha_publica); el grafo oculta el archivo reservado; la reserva con plazo vencido se levanta sola (Ley "
        "1712, art. 22: derechos.restringe). Se retiró el vocabulario muerto CONDICION_ACCESO.",
        ("tests/test_cierre_ins02.py::test_archivo_reservado_no_sale_en_rdf_ni_en_uri_ni_en_la_ficha",
         "tests/test_cierre_ins02.py::test_parte_y_documento_hermano_reservados_no_se_nombran_en_la_ficha",
         "tests/test_cierre_ins02.py::test_agente_citado_solo_en_un_documento_reservado_no_se_exporta_por_un_vinculo",
         "tests/test_cierre_ins02.py::test_agente_de_contexto_sin_documentos_se_sigue_exportando",
         "tests/test_cierre_ins02.py::test_la_reserva_vencida_se_levanta_sola",
         "tests/test_cierre_ins02.py::test_archivo_reservado_tampoco_aparece_en_el_grafo")),
    "PRE-10": Cierre(
        date(2026, 10, 3),
        "Respaldo periódico de la base (pg_dump -Fc sobre una instantánea exportada, con su SHA-256) y simulacro "
        "automático: cada volcado se restaura en una base efímera y se comparan los conteos de once tablas clave y "
        "la huella de las huellas de fijeza (servicios/respaldo.py, trabajador cada 24 h). Alertas si falla, si se "
        "atrasa o si nadie lo descarga fuera del servidor en 7 días; descarga solo del administrador y registrada. "
        "El evento aparece en la línea de tiempo de Preservación.",
        ("tests/test_cierre_pre10.py::test_respaldo_con_simulacro_correcto_y_huella",
         "tests/test_cierre_pre10.py::test_un_volcado_alterado_hace_fallar_el_simulacro_con_alerta",
         "tests/test_cierre_pre10.py::test_pg_dump_ausente_deja_respaldo_fallido_y_alerta",
         "tests/test_cierre_pre10.py::test_el_periodico_respeta_la_frecuencia_y_avisa_el_atraso",
         "tests/test_cierre_pre10.py::test_descarga_fuera_del_servidor_solo_administrador_y_queda_registrada",
         "tests/test_cierre_pre10.py::test_la_linea_de_tiempo_muestra_el_ultimo_simulacro",
         "tests/test_cierre_pre10.py::test_la_retencion_retira_archivos_viejos_pero_conserva_el_registro")),
    "O-28": Cierre(
        date(2026, 10, 3),
        "Una sola fuente para todo «rico:…» que se muestra: ric_o.uri() y ric_o.uri_inversa() (grafo, descripción, "
        "vocabularios); el grafo y su hoja Excel muestran rico:hasDocumentaryFormType; la ficha del mandato muestra "
        "rico:hasOrHadMandateType; se retiraron URI_RICO e INVERSA_RICO de enums.py. Una prueba escanea app/ y "
        "frontend/src y falla si aparece un nombre ajeno al OWL.",
        ("tests/test_ric_o.py::test_ningun_nombre_rico_escrito_en_el_codigo_o_la_interfaz_es_ajeno_al_owl",
         "tests/test_ric_o.py::test_uri_de_la_forma_documental_es_la_del_owl")),
    "CM-11": Cierre(
        date(2026, 10, 3),
        "Política decidida: el mecanismo que actuó sobre un archivo exportado sale en el RDF como rico:Mechanism con "
        "su versión (technicalCharacteristics), y su acción técnica (identificación de formato, migración) como "
        "rico:Activity que ejerce (performsOrPerformed) y que afecta al archivo (affectsOrAffected, R059, "
        "verificado contra el OWL en ric_o.ACCION_TECNICA). El motor de análisis sigue fuera (procedencia del "
        "dato). Anexo de verificación corregido.",
        ("tests/test_cierre_cm11.py::test_el_mecanismo_sale_con_su_version_y_su_accion_tecnica",
         "tests/test_cierre_cm11.py::test_la_exportacion_con_mecanismos_es_conforme_al_owl_y_al_perfil_shacl",
         "tests/test_cierre_cm11.py::test_la_accion_tecnica_resuelve_su_uri")),
    "O-19": Cierre(
        date(2026, 10, 3),
        "rico:technicalCharacteristics ya se exporta (exportacion_rico._entidad y _acciones_tecnicas); la forma "
        "SHACL pr:Mechanism tiene focos y pasa; la fila 6 del anexo de verificación y la pista de la ficha del "
        "mecanismo dicen ahora exactamente lo que el código hace.",
        ("tests/test_cierre_cm11.py::test_el_mecanismo_sale_con_su_version_y_su_accion_tecnica",
         "tests/test_cierre_cm11.py::test_la_exportacion_con_mecanismos_es_conforme_al_owl_y_al_perfil_shacl")),
    "PRE-07": Cierre(
        date(2026, 10, 3),
        "Referencia independiente de la base: cada lugar de segunda copia lleva por fondo un manifiesto de solo "
        "anexar (manifest-sha256.txt) y la verificación alerta «huella de referencia alterada» si la base no "
        "coincide con él, distinguiendo un archivo dañado de una base dañada. La web monta la segunda copia en "
        "solo lectura (docker-compose) y no escribe en ella; la reposición la hace el trabajador.",
        ("tests/test_cierre_pre07.py::test_cada_copia_queda_en_un_manifiesto_de_solo_anexar_fuera_de_la_base",
         "tests/test_cierre_pre07.py::test_si_cambia_la_huella_de_la_base_el_manifiesto_lo_delata",
         "tests/test_cierre_pre07.py::test_la_web_en_solo_lectura_no_escribe_y_el_trabajador_repone"),
        pendiente="la independencia física. La segunda copia sigue en el mismo disco del mismo servidor. Para "
                  "cerrarlo, montar RICORA_SEGUNDA_COPIA en otro disco u otro equipo; es infraestructura y la "
                  "decide la autora. El código ya admite cualquier ruta montada."),
    "PRE-08": Cierre(
        date(2026, 10, 3),
        "La verificación periódica va por antigüedad de cada archivo y en lotes (las más viejas primero): un "
        "reinicio del trabajador a mitad de camino ya no salta nada. Alerta alta «verificación atrasada» si "
        "algún archivo supera la frecuencia más dos días; se resuelve sola al ponerse al día.",
        ("tests/test_cierre_pre08.py::test_un_reinicio_a_mitad_de_pasada_no_salta_ningun_archivo",
         "tests/test_cierre_pre08.py::test_los_mas_viejos_se_verifican_primero",
         "tests/test_cierre_pre08.py::test_la_verificacion_atrasada_genera_alerta_y_se_resuelve_sola",
         "tests/test_preservacion.py::test_verificacion_periodica_respeta_la_frecuencia")),
    # --- Bloque 1 · RiC-CM -----------------------------------------------------------------------
    "CM-01": Cierre(
        date(2026, 10, 3),
        "Fechas extremas en EDTF validado (columna fechas_extremas_edtf; fechas.extremas rechaza lo que no se "
        "interpreta) y exportadas desde el EDTF, sin expresión regular. El soporte del original es atributo de su "
        "Instantiation física (CM-04); la columna soporte del Record Resource queda solo para la columna del FUID. "
        "Se retiraron NIVEL_DOCUMENTO y SOPORTE_DOCUMENTO.",
        ("tests/test_cierre_cm02.py::test_cuadro_de_clasificacion_sin_archivos_propios",
         "tests/test_cierre_cm02.py::test_fondo_registra_sus_fechas_extremas_en_edtf")),
    "CM-02": Cierre(
        date(2026, 10, 3),
        "Ruta POST /api/descripcion/agrupaciones: sección, subsección, serie, subserie o expediente sin archivos "
        "propios, con productor, código y fechas. Inclusión orgánica única (incluido_en_id) más inclusiones "
        "adicionales con rol «adicional» (POST …/inclusiones), sin ciclos.",
        ("tests/test_cierre_cm02.py::test_cuadro_de_clasificacion_sin_archivos_propios",
         "tests/test_cierre_cm02.py::test_inclusion_adicional_sin_tocar_la_organica")),
    "CM-03": Cierre(
        date(2026, 10, 3),
        "POST …/individualizar: un documento del conjunto pasa a ser su propio Record incluido en él; su archivo deja "
        "de ser instanciación del conjunto (la fila queda anulada, no borrada) y se describe al reabrirlo.",
        ("tests/test_cierre_cm03_cm04.py::test_un_oficio_del_expediente_pasa_a_ser_su_propio_record",)),
    "CM-04": Cierre(
        date(2026, 10, 3),
        "El original físico es una Instantiation sin archivo (estado registro_fisico, soporte como rico:CarrierType); "
        "la digitalización y el recorte derivan de su origen con hasOrHadDerivedInstantiation (R014). Se retiró "
        "TIPO_COPIA. has_copy e is_original_of quedan reservados con su motivo (relacionan Records, no archivos).",
        ("tests/test_cierre_cm03_cm04.py::test_original_fisico_con_soporte_y_digitalizacion_derivada",)),
    "CM-05": Cierre(
        date(2026, 10, 3),
        "Restricción de la base ck_subtipo_agente; un subtipo desconocido se rechaza (el motor ya no lo fuerza a "
        "«persona»; al reutilizar una entidad se toma el suyo). Se retiró el enumerado duplicado TIPO_AGENTE.",
        ("tests/test_cierre_bloque1.py::test_un_subtipo_de_agente_desconocido_se_rechaza_en_la_base",)),
    "CM-06": Cierre(
        date(2026, 10, 3),
        "Vínculos «ocupa_cargo» (R054, con vigencia) y «miembro» / «dirige» (R055, R042), validados por subtipo "
        "(«agente:persona»).",
        ("tests/test_cierre_bloque1.py::test_persona_ocupa_un_cargo_con_vigencia_y_el_cargo_existe_en_la_alcaldia",
         "tests/test_cierre_bloque1.py::test_grupo_y_familia_con_miembros_subdivision_y_direccion")),
    "CM-07": Cierre(
        date(2026, 10, 3),
        "Miembros (R055) y subdivisiones (R005, sin ciclos) de un grupo, declarables y exportados.",
        ("tests/test_cierre_bloque1.py::test_grupo_y_familia_con_miembros_subdivision_y_direccion",)),
    "CM-09": Cierre(
        date(2026, 10, 3),
        "La familia tiene miembros (R055) y se exporta como rico:Family con sus relaciones.",
        ("tests/test_cierre_bloque1.py::test_la_familia_y_el_cargo_se_exportan_con_su_clase_y_relaciones",)),
    "CM-10": Cierre(
        date(2026, 10, 3),
        "El cargo se une a quien lo ocupa (R054, con vigencia) y al grupo donde existe (R056 existsOrExistedIn / "
        "hasOrHadPosition), validado por subtipo.",
        ("tests/test_cierre_bloque1.py::test_persona_ocupa_un_cargo_con_vigencia_y_el_cargo_existe_en_la_alcaldia",
         "tests/test_cierre_bloque1.py::test_la_familia_y_el_cargo_se_exportan_con_su_clase_y_relaciones")),
    "CM-12": Cierre(
        date(2026, 10, 3),
        "Varios lugares superiores con vigencia, sin solaparse; lugar de expedición (R075 isOrWasLocationOf, desde el "
        "lugar) distinto del tema; un solo vocabulario de tipos de lugar, con restricción de la base.",
        ("tests/test_cierre_bloque1.py::test_lugar_con_dos_superiores_en_el_tiempo_sin_solape",
         "tests/test_cierre_cm12.py::test_lugar_de_expedicion_distinto_del_tema")),
    "CM-13": Cierre(
        date(2026, 10, 3),
        "Un hito afecta a varios agentes o descripciones (filas affects_or_affected con origen «hito»), tiene lugar "
        "(isOrWasLocationOf) y se dibuja en el grafo como Event.",
        ("tests/test_cierre_cm13.py::test_fusion_que_afecta_a_dos_entidades_con_su_lugar",)),
    "CM-14": Cierre(
        date(2026, 10, 3),
        "La verificación de actividades parecidas advierte que una actividad es un ejercicio concreto; el periodo de "
        "la actividad tiene una sola fuente (su nodo Fecha); ningún código lee ya la tabla «actividades».",
        ("tests/test_cierre_cm13.py::test_verificar_una_actividad_advierte_que_es_un_ejercicio_concreto",)),
    "CM-16": Cierre(
        date(2026, 10, 3),
        "Fechas extremas validadas como EDTF; se retiraron TIPO_FECHA y PRECISION_FECHA. Qué fecha es entidad y cuál "
        "atributo queda documentado en cierre-auditoria-ric.md.",
        ("tests/test_cierre_cm02.py::test_fondo_registra_sus_fechas_extremas_en_edtf",)),
    "CM-18": Cierre(
        date(2026, 10, 3),
        "Clase «regla» del vocabulario (rico:Rule, RiC-E16): la regla de retención de la TRD, unida a su serie con "
        "regulatesOrRegulated (rol «retencion»), heredada por expedientes y documentos y exportada con su tipo.",
        ("tests/test_cierre_cm18_des09.py::test_regla_de_retencion_regula_la_serie_y_se_hereda",
         "tests/test_cierre_cm18_des09.py::test_la_ficha_de_la_regla_se_edita_y_valida")),
    "CM-19": Cierre(
        date(2026, 10, 3),
        "Guardián before_flush (servicios/integridad_ric.py): ninguna fila de relaciones se escribe si su código no "
        "tiene propiedad en el mapeo o su origen o destino no son de una clase que la propiedad admite. Encontró y "
        "corrigió dos casos reales (expedición del mandato con R080; remitente o destinatario de un conjunto).",
        ("tests/test_cierre_bloque1.py::test_el_guardian_rechaza_una_relacion_que_ric_o_no_admite",)),
    "CM-20": Cierre(
        date(2026, 10, 3),
        "Cada código del catálogo está mapeado y escrito, o reservado con su motivo (ric_o.CODIGOS_RESERVADOS); se "
        "retiraron los enumerados muertos de enums.py.",
        ("tests/test_ric_o.py::test_cada_codigo_del_catalogo_esta_mapeado_y_escrito_o_reservado_con_motivo",)),
    "CM-21": Cierre(
        date(2026, 10, 3),
        "Decisión de la autora: un superior orgánico más inclusiones adicionales; custodia como cadena con fechas. "
        "Perfil de cardinalidades escrito en el código (ric_o.PERFIL_CARDINALIDAD) y en el anexo de verificación; "
        "relajadas las de lugar, hito y custodia.",
        ("tests/test_ric_o.py::test_el_perfil_de_cardinalidades_esta_escrito_y_documentado",
         "tests/test_cierre_cm02.py::test_inclusion_adicional_sin_tocar_la_organica",
         "tests/test_cierre_des05_des06.py::test_cadena_de_custodia_con_fechas_e_historia_archivistica")),
    "CM-22": Cierre(
        date(2026, 10, 3),
        "Identificación de formato y migración se exportan como rico:Activity con su tipo (SKOS), ejercida por el "
        "Mechanism y documentada por la instanciación resultante; en la base siguen siendo eventos PREMIS que "
        "apuntan al mecanismo.",
        ("tests/test_cierre_cm11.py::test_el_mecanismo_sale_con_su_version_y_su_accion_tecnica",)),
    # --- Bloque 3 (resueltos junto con el bloque 1) ------------------------------------------------
    "DES-02": Cierre(
        date(2026, 10, 3),
        "Fechas extremas de fondo y conjuntos en EDTF validado, con su expresión original al lado; migración que "
        "normaliza las existentes.",
        ("tests/test_cierre_cm02.py::test_fondo_registra_sus_fechas_extremas_en_edtf",)),
    "DES-05": Cierre(
        date(2026, 10, 3),
        "Custodia como cadena: cada tramo con periodo EDTF y nota, desde la descripción y también sobre una "
        "instanciación (archivo u original físico).",
        ("tests/test_cierre_des05_des06.py::test_cadena_de_custodia_con_fechas_e_historia_archivistica",)),
    "DES-06": Cierre(
        date(2026, 10, 3),
        "Campo historia_archivistica (con su origen) en la descripción, el catálogo, la ficha pública y la "
        "exportación (rico:history).",
        ("tests/test_cierre_des05_des06.py::test_cadena_de_custodia_con_fechas_e_historia_archivistica",)),
    "DES-08": Cierre(
        date(2026, 10, 3),
        "Nivel subsección; el cuadro de clasificación se crea sin documentos; código único en el fondo y, para serie "
        "y subserie, compuesto desde el de su superior.",
        ("tests/test_cierre_cm02.py::test_cuadro_de_clasificacion_sin_archivos_propios",
         "tests/test_cierre_cm02.py::test_el_codigo_de_la_serie_se_compone_desde_su_superior")),
    "DES-09": Cierre(
        date(2026, 10, 3),
        "Regla de retención (gestión, central, disposición final, procedimiento) unida a la serie, heredada hacia "
        "abajo y mostrada en la ficha del catálogo.",
        ("tests/test_cierre_cm18_des09.py::test_regla_de_retencion_regula_la_serie_y_se_hereda",)),
    # --- Bloque 2 (resueltos junto con el bloque 1) ------------------------------------------------
    "O-29": Cierre(
        date(2026, 10, 3),
        "La expedición del mandato pasa a isDateAssociatedWith (R068) con rol «expedicion»; migración 0018 de los "
        "datos existentes. El guardián CM-19 impide volver a escribir R080 hacia un mandato.",
        ("tests/test_cierre_bloque1.py::test_el_guardian_rechaza_una_relacion_que_ric_o_no_admite",
         "tests/test_descripcion_contexto.py::test_la_actividad_queda_conectada_a_su_tipo_agente_y_mandato_y_se_ve_en_el_catalogo")),
    "O-33": Cierre(
        date(2026, 10, 3),
        "Códigos sin mapeo declarados como reservados con su motivo; la exportación distingue «sin mapeo en el "
        "sistema» de «sin propiedad en RiC-O».",
        ("tests/test_ric_o.py::test_cada_codigo_del_catalogo_esta_mapeado_y_escrito_o_reservado_con_motivo",)),
    "O-12": Cierre(
        date(2026, 10, 3),
        "La exportación ya no escribe nombres de RiC-O sueltos: toda clase y propiedad sale del mapeo único "
        "(ric_o.APOYO, CLASE_NODO, CLASE_VOCABULARIO). Las fechas extremas de una agrupación salen como "
        "hasOrHadAllMembersWithCreationDate; la de un documento, como hasCreationDate.",
        ("tests/test_ric_o.py::test_la_exportacion_no_escribe_nombres_rico_sueltos",
         "tests/test_cierre_bloque2.py::test_fechas_extremas_de_una_agrupacion_son_las_de_sus_miembros")),
    "O-26": Cierre(
        date(2026, 10, 3),
        "Una agrupación con un solo idioma declara hasOrHadAllMembersWithLanguage; con varios, "
        "hasOrHadSomeMembersWithLanguage (no todos sus documentos están en cada idioma).",
        ("tests/test_cierre_bloque2.py::test_agrupacion_con_un_idioma_dice_todos_sus_miembros",
         "tests/test_cierre_bloque2.py::test_agrupacion_con_varios_idiomas_dice_algunos_miembros")),
    "O-30": Cierre(
        date(2026, 10, 3),
        "owl:sameAs apunta a la URI canónica de cada autoridad (http para Wikidata, VIAF y LC). El idioma de una "
        "forma del nombre se valida contra ISO 639-3 y se serializa en BCP 47 («spa» → @es).",
        ("tests/test_cierre_bloque2.py::test_uri_externa_es_la_canonica_de_cada_autoridad",
         "tests/test_cierre_bloque2.py::test_idioma_iso_639_3_se_convierte_a_bcp47",
         "tests/test_cierre_bloque2.py::test_nombre_con_idioma_invalido_se_rechaza",
         "tests/test_cierre_bloque2.py::test_nombre_en_espanol_sale_con_etiqueta_es")),
    "O-31": Cierre(
        date(2026, 10, 3),
        "Las 15 relaciones sin aserción propia tienen su tripleta comprobada en el RDF, creadas con los servicios "
        "del sistema (incluida occupiesOrOccupied, que ahora crea el vínculo «ocupa cargo»). La base de pruebas "
        "dejó de ser autouse: el mapeo RiC-O se prueba sin PostgreSQL; el requisito quedó en el README.",
        ("tests/test_cierre_o31.py::test_las_quince_relaciones_tienen_tripleta_propia",
         "tests/test_cierre_o31.py::test_las_propiedades_de_cada_relacion_estan_en_el_owl",
         "tests/test_cierre_o31.py::test_la_exportacion_del_fondo_completo_sigue_conforme",
         "tests/test_cierre_o31.py::test_las_pruebas_del_mapeo_corren_sin_postgresql")),
    "O-32": Cierre(
        date(2026, 10, 3),
        "Formas SHACL nuevas: Event, Identifier, AgentName, PlaceName y el título de Instantiation; pr:Mechanism "
        "tiene focos. Cada descarga completa se valida (OWL y SHACL), el resultado queda en la auditoría y en la "
        "cabecera X-RICORA-Conformidad, y si no es conforme se crea una alerta y la interfaz lo avisa.",
        ("tests/test_cierre_o32.py::test_cada_clase_emitida_tiene_su_forma",
         "tests/test_cierre_o32.py::test_nombre_de_lugar_sin_valor_no_es_conforme",
         "tests/test_cierre_o32.py::test_el_mecanismo_tiene_focos_en_la_exportacion",
         "tests/test_cierre_o32.py::test_cada_descarga_completa_valida_y_lo_deja_en_la_auditoria",
         "tests/test_cierre_o32.py::test_una_descarga_no_conforme_se_sirve_marcada_y_con_alerta")),
}


def hallazgos_auditoria() -> list[dict]:
    return json.loads(DATOS.read_text(encoding="utf-8"))


def _accion(c: Cierre) -> str:
    prefijo = "Corregido en parte" if c.pendiente else "Corregido"
    texto = (f"{prefijo} el {c.fecha.isoformat()}. {c.evidencia} Pruebas: "
             + "; ".join(p.split("::")[-1] for p in c.pruebas) + ".")
    return texto + (f" Falta: {c.pendiente}" if c.pendiente else "")


def sincronizar(db: Session) -> dict:
    """Siembra lo que falte y aplica los cierres pendientes. Idempotente."""
    existentes = {h.referencia: h for h in db.scalars(select(HallazgoConformidad).where(
        HallazgoConformidad.referencia.is_not(None))).all()}
    sembrados = cerrados = 0
    numero = db.scalar(select(func.max(HallazgoConformidad.numero))) or 0
    for x in hallazgos_auditoria():
        if x["referencia"] in existentes:
            continue
        numero += 1
        h = HallazgoConformidad(id=uuid.uuid4(), numero=numero, referencia=x["referencia"], titulo=x["titulo"],
                                descripcion=x["descripcion"], componentes=x["componentes"], estado="abierto",
                                abierto_en=ABIERTO_EN, accion=x["accion"])
        db.add(h)
        db.flush()
        registrar(db, modulo="auditoria", accion="hallazgo_creado", entidad_tipo="hallazgo", entidad_id=h.id,
                  detalle=f"Hallazgo {numero} ({h.referencia}), de la auditoría de conformidad RiC del "
                          f"{ABIERTO_EN.isoformat()}",
                  nuevo={"numero": numero, "referencia": h.referencia, "titulo": h.titulo, "estado": h.estado,
                         "componentes": h.componentes})
        existentes[h.referencia] = h
        sembrados += 1
    for ref, c in CIERRES.items():
        h = existentes.get(ref)
        estado = "en_correccion" if c.pendiente else "cerrado"
        if h is None or h.estado == "cerrado" or (h.estado == estado and h.accion == _accion(c)):
            continue
        antes = {"estado": h.estado, "cerrado_en": None, "accion": h.accion}
        h.estado, h.cerrado_en, h.accion = estado, (None if c.pendiente else c.fecha), _accion(c)
        registrar(db, modulo="auditoria", accion="hallazgo_actualizado", entidad_tipo="hallazgo", entidad_id=h.id,
                  detalle=f"Hallazgo {h.numero} ({ref}): {'en corrección' if c.pendiente else 'corregido'} en el "
                          "cierre de la auditoría RiC",
                  anterior=antes, nuevo={"estado": h.estado,
                                         "cerrado_en": h.cerrado_en.isoformat() if h.cerrado_en else None,
                                         "accion": h.accion})
        cerrados += 1
    db.flush()
    return {"sembrados": sembrados, "cerrados": cerrados}


if __name__ == "__main__":
    from app.db.session import SessionLocal

    with SessionLocal() as sesion:
        resultado = sincronizar(sesion)
        sesion.commit()
    print(f"Hallazgos de la auditoría RiC: {resultado['sembrados']} sembrados, {resultado['cerrados']} cerrados.")
