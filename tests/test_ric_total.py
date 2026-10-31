"""
Cobertura total de RiC-CM 1.0 (42 atributos, 85 relaciones), probada en el grafo.

La medida de app/servicios/cobertura_ric.py sale del mapeo; esta prueba
comprueba que el mapeo no es una promesa: arma un fondo con la TRD, sus
documentos, archivos, originales en papel, agentes y su contexto, lo exporta
completo y exige que cada código de RiC-CM (salvo R026, cubierta por
hasCreator y hasAccumulator) aparezca en el grafo como propiedad o clase, que
el grafo sea conforme al OWL y al perfil SHACL, que el grupo demográfico (dato
sensible) no salga en la exportación pública y que el grafo vuelva a las
tablas sin pérdida.
"""

import uuid

from rdflib import RDF, URIRef

from app.models.recurso_documental import RecursoDocumental
from app.servicios import (autoridad, cobertura_ric, conformidad_rico, descripcion, exportacion_rico, fechas,
                           grafo_control, grafo_rdf, recorte, ric_o, vocabulario)
from tests import archivos
from tests.test_disposicion import _fondo
from tests.test_especializacion_ric import documento, relacion
from tests.test_preservacion import herramientas, ingresar_archivo  # noqa: F401  (fixtures)

RICO = ric_o.RICO


def _entidad(db, fondo, clase, nombre, subtipo=None):
    return vocabulario.crear(db, fondo_id=fondo.id, clase=clase, nombre=nombre, subtipo=subtipo, origen="persona",
                             confianza=None, motor=None, usuario_id=None)


def _fecha(db, edtf):
    f = descripcion._crear_fecha(db, edtf, fechas.interpretar(edtf), "persona", None, None)
    db.flush()
    return f


def _armar(cliente, db, cab):
    fnd, viejo, nuevo = _fondo(cliente, db, cab)
    usuario = fnd.creado_por_id
    serie = db.get(RecursoDocumental, viejo.incluido_en_id)
    # Disposición final: la eliminación del expediente vencido (fecha de destrucción).
    r = cliente.post("/api/disposicion/ejecutar", headers=cab, json={
        "fondo_id": str(fnd.id), "recursos": [str(viejo.id)], "disposicion": "eliminacion", "acta_numero": "05",
        "acta_fecha": "2025-03-10", "ejecutor": "Comité Institucional de Gestión y Desempeño"})
    assert r.status_code == 201, r.text
    # Ente que vigila la TRD (RiC-R066).
    version = cliente.get("/api/trd/versiones", headers=cab, params={"fondo_id": str(fnd.id)}).json()
    version = version[0]
    r = cliente.patch(f"/api/trd/versiones/{version['id']}", headers=cab,
                      json={"ente_vigilancia": "Archivo General de la Nación"})
    assert r.status_code == 200, r.text

    # Documentos con su contenido, estado, respuesta, borrador y copia.
    oficio = documento(db, fnd, "Oficio 114")
    oficio.incluido_en_id = nuevo.id
    oficio.tipos_contenido = ["texto"]
    oficio.estado_documento = "definitivo"
    oficio.nota_integridad = "Completo, con sus dos anexos."
    respuesta = documento(db, fnd, "Respuesta al oficio 114")
    respuesta.incluido_en_id = nuevo.id
    borrador = documento(db, fnd, "Borrador del oficio 114")
    copia = documento(db, fnd, "Copia del oficio 114")
    oficio.folios = 2
    oficio.idiomas = ["spa"]
    oficio.condiciones_acceso = "Libre acceso."
    oficio.condiciones_uso = "Cítese la fuente."
    oficio.fechas_extremas_edtf = "2024-04-02"
    respuesta.fechas_extremas_edtf = "2023-12/2024-02"  # se cruza con las del expediente
    nuevo.fechas_extremas_edtf = "2024"
    nuevo.fechas_predominantes_edtf = "2024-03/2024-06"
    nuevo.nuevos_ingresos = "Se esperan ingresos anuales."
    nuevo.organizacion = "Orden cronológico."
    parte = RecursoDocumental(id=uuid.uuid4(), nivel="parte_documental", titulo="Anexo 1", fondo_id=fnd.id,
                              incluido_en_id=oficio.id, publicado_en=oficio.publicado_en)
    db.add(parte)
    db.flush()
    relacion(db, respuesta, oficio, "has_reply", destino_tipo="recurso_documental")
    relacion(db, borrador, oficio, "is_draft_of", destino_tipo="recurso_documental")
    relacion(db, oficio, copia, "has_copy", destino_tipo="recurso_documental")
    relacion(db, oficio, respuesta, "precedes_or_preceded", destino_tipo="recurso_documental")

    # Fechas: creación del documento (dentro de las del expediente) y modificación.
    creacion = _fecha(db, "2024-04-02")
    relacion(db, creacion, oficio, "is_creation_date_of", origen_tipo="fecha", destino_tipo="recurso_documental")
    cruzada = _fecha(db, "2023-12/2024-02")
    relacion(db, cruzada, respuesta, "is_creation_date_of", origen_tipo="fecha", destino_tipo="recurso_documental")
    modificacion = _fecha(db, "2024-05~")  # aproximada: lleva su calificador
    relacion(db, modificacion, oficio, "is_modification_date_of", origen_tipo="fecha",
             destino_tipo="recurso_documental")

    # Agentes de cada clase, con sus atributos de RiC-CM.
    alcaldia = _entidad(db, fnd, "agente", "Alcaldía de Tunja", "entidad_corporativa")
    alcaldia.tipo_entidad = "publica_distrital_municipal"
    alcaldia.estatuto_juridico = "publica"
    alcaldia.historia = "Municipio fundado en 1539."
    familia = _entidad(db, fnd, "agente", "Familia Rojas Pinilla", "familia")
    familia.tipo_familia = "nuclear"
    persona = _entidad(db, fnd, "agente", "María Cano", "persona")
    persona.ocupacion = "Secretaria de despacho"
    persona.grupo_demografico = "Mujeres"
    persona.existencia_edtf = "1887-08-12/1967-04-26"
    alumna = _entidad(db, fnd, "agente", "Ana Rojas", "persona")
    hija = _entidad(db, fnd, "agente", "Lucía Rojas", "persona")
    grupo = _entidad(db, fnd, "agente", "Comisión de Notables", "grupo")
    cargo = _entidad(db, fnd, "agente", "Secretaría de Gobierno", "cargo")
    ministerio = _entidad(db, fnd, "agente", "Ministerio del Interior", "entidad_corporativa")
    ministerio.existencia_edtf = "1886/1990"
    tunja = _entidad(db, fnd, "lugar", "Tunja")
    tunja.latitud, tunja.longitud = 5.5353, -73.3678
    boyaca = _entidad(db, fnd, "lugar", "Boyacá")
    soraca = _entidad(db, fnd, "lugar", "Soracá")
    actividad = _entidad(db, fnd, "actividad", "Atención de peticiones")
    tramite = _entidad(db, fnd, "actividad", "Respuesta a derechos de petición")
    funcion = _entidad(db, fnd, "tipo_actividad", "Gestión de peticiones")
    decreto = _entidad(db, fnd, "mandato", "Decreto 001 de 1990", "decreto")
    concejo = _entidad(db, fnd, "agente", "Concejo Municipal", "entidad_corporativa")
    materia = _entidad(db, fnd, "materia", "Servicios públicos")
    db.flush()

    # Relaciones de los documentos con los agentes (roles del registro).
    for codigo, destino in (("has_receiver", ministerio), ("has_collector", persona),
                            ("has_or_had_owner", alcaldia), ("has_or_had_manager", cargo),
                            ("has_or_had_ipr_holder", alcaldia), ("has_or_had_main_subject", materia),
                            ("has_creator", alcaldia), ("has_accumulator", alcaldia),
                            ("has_sender", persona), ("has_addressee", ministerio), ("has_or_had_holder", alcaldia),
                            ("has_author", persona), ("has_or_had_subject", tunja)):
        relacion(db, oficio, destino, codigo)

    # Vínculos de autoridad entre agentes, lugares y actividades.
    for tipo, desde, con in (("ascendiente_de", persona, hija), ("autoridad_sobre", ministerio, alcaldia),
                             ("controla_a", ministerio, alcaldia), ("relacion_laboral", persona, alumna),
                             ("sabe_de", persona, alumna), ("conoce_a", alumna, hija),
                             ("correspondencia_con", persona, hija), ("maestro_de", persona, alumna),
                             ("participante", actividad, persona), ("jurisdiccion", alcaldia, tunja),
                             ("adyacente_a", tunja, soraca), ("se_superpone_con", tunja, boyaca),
                             ("miembro", familia, hija), ("miembro", grupo, persona),
                             ("subordinado", alcaldia, concejo), ("sucesor", ministerio, alcaldia),
                             ("asociado", alcaldia, grupo), ("ocupa_cargo", persona, cargo),
                             ("progenitor_de", persona, hija), ("hermano_de", hija, alumna),
                             ("conyuge_de", persona, alumna), ("dirige", persona, grupo),
                             ("subdivision", alcaldia, ministerio), ("cargo_en", cargo, alcaldia),
                             ("lugar_superior", tunja, boyaca), ("actividad_mayor", tramite, actividad),
                             ("expedido_por", decreto, concejo), ("creado_por", concejo, decreto),
                             ("serie_producida", funcion, serie)):
        con_tipo = "recurso_documental" if isinstance(con, RecursoDocumental) else "entidad_vocabulario"
        autoridad.vincular(db, tipo=tipo, desde=desde, con_tipo=con_tipo, con_id=con.id, usuario_id=usuario)

    # Línea de tiempo de la alcaldía: dos hitos sucesivos con su tipo y su fecha.
    autoridad.agregar_hito(db, alcaldia, tipo="creacion", descripcion="Creación del municipio", edtf="1541-12-23",
                           usuario_id=usuario, lugar_id=tunja.id)
    autoridad.agregar_hito(db, alcaldia, tipo="reforma", descripcion="Reforma administrativa", edtf="2001-05-02",
                           usuario_id=usuario)

    # Archivos: el digital, su migración, un recorte, un componente y el original en papel.
    pdf = ingresar_archivo(cliente, db, cab, fnd, "Oficio 114.pdf", archivos.pdf_con_texto())
    png = ingresar_archivo(cliente, db, cab, fnd, "Anexo 1.png", archivos.png_con_texto())
    for i in (pdf, png):
        relacion(db, oficio, i, "has_or_had_instantiation", destino_tipo="instanciacion")
    m = cliente.post(f"/api/preservacion/instanciacion/{pdf.id}/migrar", headers=cab,
                     json={"destino": "pdfa_2b", "aprobada": True})
    assert m.status_code in (200, 201), m.text
    sello = recorte.recortar(db, png, {"pagina": 1, "x": 0.1, "y": 0.1, "ancho": 0.5, "alto": 0.4}, "Sello", usuario)
    relacion(db, parte, sello, "has_or_had_instantiation", destino_tipo="instanciacion")
    descripcion.componente(db, oficio, pdf.id, png.id, usuario)
    descripcion.registrar_original_fisico(
        db, oficio, soporte="papel", ubicacion="Caja 3, carpeta 12", usuario_id=usuario,
        caracteristicas="Dos folios con sello húmedo.",
        datos_agn={"deposito": "Depósito 1", "estante": "4", "entrepano": "2", "tecnica_produccion": "mecanografiado",
                   "estado_conservacion": "bueno"})
    db.commit()
    return fnd, persona


def _terminos(g) -> set[str]:
    salida = set()
    for s, p, o in g:
        for x in (p, o if p == RDF.type else None):
            if isinstance(x, URIRef) and str(x).startswith(RICO):
                salida.add(str(x)[len(RICO):])
    return salida


def test_cada_codigo_de_ric_cm_esta_en_el_grafo_y_es_conforme(cliente, db, cabeceras_admin, herramientas):  # noqa: F811
    fnd, persona = _armar(cliente, db, cabeceras_admin)
    ex = exportacion_rico.exportar(db, fnd, incluir_restringidos=True)
    reporte = conformidad_rico.reporte(ex)
    assert reporte["owl"]["problemas"] == [], reporte["owl"]["problemas"]
    assert reporte["shacl"]["conforme"], "\n".join(map(str, reporte["shacl"]["resultados"]))

    escritos = _terminos(ex.grafo)
    medida = cobertura_ric.medir()["por_codigo"]
    assert len(medida) == 42 + 85
    ausentes = {c: t for c, t in medida.items() if c not in cobertura_ric.FALTANTES and not set(t) & escritos}
    assert not ausentes, "\n".join(f"{c}: {t}" for c, t in ausentes.items())

    # El grupo demográfico es dato sensible: solo en el grafo completo.
    publico = exportacion_rico.exportar(db, fnd)
    sujeto = exportacion_rico.uri(persona.id)
    assert any(ex.grafo.objects(sujeto, URIRef(RICO + "hasOrHadDemographicGroup")))
    assert not any(publico.grafo.objects(sujeto, URIRef(RICO + "hasOrHadDemographicGroup")))


def test_ida_y_vuelta_exacta_con_todo_ric(cliente, db, cabeceras_admin, herramientas):  # noqa: F811
    fnd, _ = _armar(cliente, db, cabeceras_admin)
    for alcance in grafo_rdf.ALCANCES:
        grafo_rdf.sincronizar(db, fnd, alcance)
    db.commit()
    antes = grafo_control.foto(db, fnd.id)
    assert grafo_rdf.comparar(db, fnd.id) == []
    assert grafo_rdf.reconstruir(db, fnd.id)["diferencias_despues"] == []
    assert grafo_control.foto(db, fnd.id) == antes
