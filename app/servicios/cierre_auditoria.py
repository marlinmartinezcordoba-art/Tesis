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
