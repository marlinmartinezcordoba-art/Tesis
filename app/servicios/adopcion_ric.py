"""
Adopción de RiC: el sistema se evalúa a sí mismo contra los siete criterios
de un sistema nativo en RiC y contra la escala de niveles de adopción
(documentacion/ric-nativo.md). Es la demostración, con datos reales y no con
afirmaciones, de que RICORA adopta el lineamiento.

Cada criterio dice si se cumple, con qué evidencia medida en la base y en el
almacén del grafo, cómo se verifica y qué prueba automática lo sostiene.
Un criterio se cumple por diseño (el sistema lo hace) y la evidencia muestra
cuánto se ha usado; si los datos lo contradicen (un mecanismo sin versión, un
grafo no conforme), el criterio queda parcial y dice por qué.
"""

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.grafo_rdf import GrafoRdf
from app.models.recurso_documental import RecursoDocumental
from app.servicios import cobertura_ric, vocabulario

NIVELES = [
    {"codigo": 0, "nombre": "Descripción multinivel", "que": "Se describe con ISAD(G) y la NTC 4095; RiC no interviene."},
    {"codigo": 1, "nombre": "Migración a RiC", "que": "Se describe con ISAD(G) y al final un programa convierte las fichas a RiC-O."},
    {"codigo": 2, "nombre": "Descripción conforme con RiC",
     "que": "Lo publicado nace en RiC y se valida contra la ontología oficial antes de publicarse."},
    {"codigo": 3, "nombre": "Sistema nativo en RiC",
     "que": "Las entidades son de la institución, el acervo se consulta como un solo grafo y la historia de la "
            "descripción también es RiC."},
]
TOTAL_CLASES_RICO = 107


def _n(db: Session, consulta) -> int:
    return int(db.scalar(consulta) or 0)


def _criterio(n, nombre, cumple, evidencia, verificacion, prueba, motivo=None, en_uso=True):
    """«cumplido» dice que el sistema tiene la capacidad y que una prueba automática la demuestra;
    «en_uso», si el acervo ya tiene casos que la ejercen. Son cosas distintas y se muestran por separado."""
    return {"numero": n, "criterio": nombre, "estado": "cumplido" if cumple else "parcial", "evidencia": evidencia,
            "verificacion": verificacion, "prueba": prueba, "motivo": motivo, "en_uso": en_uso}


def evaluar(db: Session) -> dict:
    ev = EntidadVocabulario
    rd = RecursoDocumental
    fondos = _n(db, select(func.count()).select_from(rd).where(rd.nivel == "fondo"))

    # 1. Entidades de la institución.
    institucionales = dict(db.execute(select(ev.clase, func.count()).where(vocabulario.es_compartida(), ev.estado == "activa")
                                      .group_by(ev.clase)).all())
    doc = aliased(rd)
    citadas_varios = select(Relacion.destino_id).join(doc, doc.id == Relacion.origen_id).where(
        Relacion.estado == "vigente", Relacion.origen_tipo == "recurso_documental",
        Relacion.destino_tipo == "entidad_vocabulario").group_by(Relacion.destino_id).having(
        func.count(func.distinct(doc.fondo_id)) > 1)
    en_varios = _n(db, select(func.count()).select_from(citadas_varios.subquery()))
    clases_ok = set(vocabulario.CLASES_INSTITUCIONALES) >= {"agente", "lugar", "materia", "mandato"}
    c1 = _criterio(1, "Las entidades existen por sí mismas, no subordinadas a un fondo", clases_ok, [
        f"Autoridades de la institución: {sum(institucionales.values())} "
        f"({', '.join(f'{v} de clase {k}' for k, v in sorted(institucionales.items())) or 'ninguna todavía'})",
        f"Citadas por documentos de más de un fondo: {en_varios}",
        "Clases institucionales: " + ", ".join(vocabulario.CLASES_INSTITUCIONALES)
        + ". Las formas documentales y las funciones siguen siendo del fondo: nacen de su TRD"],
        "Una autoridad registrada en un fondo aparece al describir en otro y se exporta con la misma URI en ambos",
        "tests/test_ric_nativo.py::test_un_lugar_es_uno_para_toda_la_institucion_y_se_enlaza_con_geonames_y_wikidata",
        en_uso=sum(institucionales.values()) > 0)

    # 2. Relaciones de primer nivel.
    rels = Relacion.estado == "vigente"
    total_rel = _n(db, select(func.count()).select_from(Relacion).where(rels))
    con_fecha = _n(db, select(func.count()).select_from(Relacion).where(rels, Relacion.fecha_edtf.is_not(None)))
    con_rol = _n(db, select(func.count()).select_from(Relacion).where(rels, Relacion.rol.is_not(None)))
    c2 = _criterio(2, "Las relaciones son datos de primer nivel, con fechas, rol, fuente y certeza", True, [
        f"Relaciones vigentes: {total_rel}; con vigencia: {con_fecha}; con rol: {con_rol}",
        "Cada una se exporta también como nodo rico:Relation con rico:relationSource y, si la propuso el motor, "
        "rico:relationCertainty"],
        "En la URI de cualquier relación: su clase específica de RiC-O, su fuente y su certeza",
        "tests/test_especializacion_ric.py::test_relacion_propuesta_por_el_motor_lleva_su_certeza_y_su_fuente",
        en_uso=total_rel > 0)

    # 3. Procedencia múltiple.
    varios_productores = _n(db, select(func.count()).select_from(
        select(Relacion.origen_id).where(rels, Relacion.codigo_ric == "has_creator",
                                         Relacion.origen_tipo == "recurso_documental")
        .group_by(Relacion.origen_id).having(func.count() > 1).subquery()))
    c3 = _criterio(3, "Admite procedencia múltiple", True, [
        f"Documentos con más de un productor: {varios_productores}",
        f"Autoridades citadas desde más de un fondo: {en_varios}"],
        "Un documento puede tener varios productores y un agente producir en varios fondos",
        "tests/test_autoridades_compartidas.py::test_una_autoridad_para_toda_la_institucion",
        en_uso=varios_productores + en_varios > 0)

    # 4. Intercambio en las dos direcciones.
    importaciones = dict(db.execute(select(RegistroAuditoria.accion, func.count()).where(
        RegistroAuditoria.accion.in_(("rico_importado", "eac_importado", "cuadro_importado"))).group_by(
        RegistroAuditoria.accion)).all())
    c4 = _criterio(4, "Intercambia RiC en las dos direcciones", True, [
        "Entrada: RiC-O (Turtle, JSON-LD, RDF/XML), EAD 2002 y EAD3, EAC-CPF",
        "Salida: RiC-O en Turtle y JSON-LD, EAD3 y EAC-CPF, todo validado",
        f"Importaciones registradas: {sum(importaciones.values())}"],
        "Importar un archivo RiC-O de otro sistema y volver a exportarlo",
        "tests/test_importacion_rico.py", en_uso=sum(importaciones.values()) > 0)

    # 5. Consulta del acervo.
    publicos = select(GrafoRdf).where(GrafoRdf.alcance == "publico")
    sincronizados = _n(db, select(func.count()).select_from(publicos.where(GrafoRdf.version_sincronizada > 0).subquery()))
    c5 = _criterio(5, "Permite consultar el grafo de todo el acervo", True, [
        f"Fondos en el punto SPARQL del acervo: {sincronizados} de {fondos}",
        "GET /api/publico/sparql sin fondo: la unión de los grafos públicos; con fondo: solo ese"],
        "Una sola consulta devuelve documentos de todos los fondos, sin lo clasificado o reservado",
        "tests/test_ric_nativo.py::test_sparql_sobre_todo_el_acervo", en_uso=sincronizados > 0)

    # 6. Cobertura del modelo.
    cob = cobertura_ric.medir()
    a, r = cob["atributos"], cob["relaciones"]
    completa = a["cubiertos"] + a["por_especializacion"] >= a["total"] and r["cubiertos"] + r["por_especializacion"] >= r["total"]
    c6 = _criterio(6, "Cubre el modelo conceptual", completa, [
        f"Atributos de RiC-CM 1.0: {a['cubiertos'] + a['por_especializacion']} de {a['total']}",
        f"Relaciones de RiC-CM 1.0 citadas por la ontología: {r['cubiertos'] + r['por_especializacion']} de {r['total']}"],
        "Medida desde el mapeo que usa la exportación, contra los códigos que cita el OWL oficial",
        "tests/test_cobertura_ric.py", None if completa else "Hay códigos de RiC-CM sin término exportado.")

    # 7. La historia de la descripción en RiC.
    de_motor = and_(rels, Relacion.origen.in_(("motor", "motor_editado")))
    con_mecanismo = _n(db, select(func.count()).select_from(Relacion).join(ev, ev.id == Relacion.motor_id).where(
        de_motor, ev.version.is_not(None)))
    sin_mecanismo = _n(db, select(func.count()).select_from(Relacion).where(de_motor)) - con_mecanismo
    de_persona = _n(db, select(func.count()).select_from(Relacion).where(rels, Relacion.origen == "persona"))
    c7 = _criterio(7, "La historia de la descripción también es RiC", sin_mecanismo == 0, [
        f"Relaciones propuestas por el motor, con su mecanismo y su versión: {con_mecanismo}",
        f"Relaciones registradas por una persona: {de_persona}",
        "Cada relación se asocia (rico:isAssociatedWithEvent) a la actividad que la produjo: la propuesta, "
        "ejercida por el motor como rico:Mechanism, y la validación o la corrección, ejercida por la archivista"],
        "En la URI de un documento: quién afirmó cada relación",
        "tests/test_ric_nativo.py::test_la_autoria_de_cada_relacion_esta_en_el_grafo",
        f"{sin_mecanismo} relación(es) del motor anteriores al registro de mecanismos: su propuesta sale sin el "
        "agente que la ejerció" if sin_mecanismo else None, en_uso=con_mecanismo + de_persona > 0)

    criterios = [c1, c2, c3, c4, c5, c6, c7]
    cumplidos = sum(1 for c in criterios if c["estado"] == "cumplido")
    nivel = NIVELES[3] if cumplidos == len(criterios) else NIVELES[2]

    # Conformidad de lo publicado: lo que guarda el almacén del grafo.
    grafos = db.scalars(select(GrafoRdf).where(GrafoRdf.version_sincronizada > 0)).all()
    clases = set()
    for g in grafos:
        clases |= set(((g.resumen or {}).get("por_clase") or {}).keys())
    from app.servicios import perfil_agn

    perfil = perfil_agn.catalogo()
    return {
        "nivel": nivel, "niveles": NIVELES, "cumplidos": cumplidos, "criterios": criterios,
        "conformidad": {
            "fondos": fondos, "grafos": len(grafos),
            "conformes": sum(1 for g in grafos if g.conforme), "no_conformes": sum(1 for g in grafos if g.conforme is False),
            "pendientes": _n(db, select(func.count()).select_from(GrafoRdf).where(
                GrafoRdf.version_sincronizada < GrafoRdf.version_datos)),
            "tripletas": sum(g.tripletas or 0 for g in grafos if g.alcance == "completo"),
            "clases_usadas": len(clases), "clases_total": TOTAL_CLASES_RICO,
        },
        "cobertura": {"atributos": a, "relaciones": r},
        "perfil_agn": {"total": len(perfil["filas"]), **perfil["resumen"],
                       "codigos_agn_incorrectos": perfil["codigos_agn_incorrectos"]},
        "consultas": CONSULTAS,
    }


# Consultas SPARQL que demuestran cada criterio sobre el acervo (se pueden ejecutar desde la pantalla).
_P = "PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\n"
CONSULTAS = [
    {"titulo": "Quién afirmó cada relación (criterio 7)", "consulta": _P + """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?desde ?relacion ?hacia ?actividad ?quien WHERE {
  ?r rico:isAssociatedWithEvent ?act ; rdfs:label ?relacion ;
     rico:relationHasSource/rdfs:label ?desde ; rico:relationHasTarget/rdfs:label ?hacia .
  ?act rico:name ?actividad . ?agente rico:performsOrPerformed ?act ; rico:name ?quien .
} ORDER BY ?desde ?relacion ?actividad LIMIT 50"""},
    {"titulo": "Documentos de todos los fondos y su productor (criterios 1 y 5)", "consulta": _P + """SELECT ?documento ?productor WHERE {
  ?d a rico:Record ; rico:title ?documento ; rico:hasCreator ?a . ?a rico:name ?productor .
} LIMIT 50"""},
    {"titulo": "Lugares enlazados con GeoNames o Wikidata (criterio 1)", "consulta": _P + """PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?lugar ?externo WHERE { ?l a rico:Place ; rico:name ?lugar ; owl:sameAs ?externo . } LIMIT 50"""},
    {"titulo": "Mecanismos y su versión (criterio 7)", "consulta": _P + """SELECT ?mecanismo ?version WHERE {
  ?m a rico:Mechanism ; rico:name ?mecanismo . OPTIONAL { ?m rico:technicalCharacteristics ?version }
} LIMIT 50"""},
]
