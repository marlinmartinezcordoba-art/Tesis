"""Entidades idénticas: no se crean dos veces, se fusionan sin borrar, y las parecidas que solo
difieren en un número (dos resoluciones distintas) no se sugieren como duplicadas."""

import uuid

from sqlalchemy import select

from app.models.descripcion import EntidadVocabulario, SugerenciaFusion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import cuadro, vocabulario
from tests.test_vocabularios import archivista, documento_con, entidad, fondo  # noqa: F401


def _otro_fondo(db):
    f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Otro fondo")
    f.fondo_id = f.id
    db.add(f)
    db.commit()
    return f


def test_la_trd_reutiliza_la_entidad_identica_aun_de_otro_fondo(db, fondo):  # noqa: F811
    otro = _otro_fondo(db)
    agente = entidad(db, otro, "Secretaría de Hacienda")
    reusado, creado = cuadro._de_vocabulario(db, fondo.id, "agente", "SECRETARIA DE HACIENDA", None, "entidad_corporativa")
    assert reusado.id == agente.id and not creado
    # La forma documental es del fondo: en otro fondo se crea la suya, pero una sola vez.
    entidad(db, otro, "Oficio", clase="forma_documental")
    f1, c1 = cuadro._de_vocabulario(db, fondo.id, "forma_documental", "Oficio", None)
    f2, c2 = cuadro._de_vocabulario(db, fondo.id, "forma_documental", "oficio", None)
    assert c1 and not c2 and f1.id == f2.id and f1.fondo_id == fondo.id


def test_personas_y_actividades_homonimas_no_se_reutilizan(db, fondo):  # noqa: F811
    entidad(db, fondo, "Juan Pérez", subtipo="persona")
    assert vocabulario.existente(db, fondo.id, "agente", "Juan Pérez", "persona") is None
    assert not vocabulario.reutilizable("actividad") and not vocabulario.reutilizable("regla")


def test_fusionar_identicas_deja_una_con_su_traza(cliente, db, fondo, archivista):  # noqa: F811
    a = entidad(db, fondo, "Ministerio de Ambiente")
    b = entidad(db, fondo, "MINISTERIO DE AMBIENTE")
    c = entidad(db, fondo, "Ministerio  de ambiente")
    entidad(db, fondo, "Juan Pérez", subtipo="persona")
    entidad(db, fondo, "Juan Perez", subtipo="persona")  # homónimos: no se tocan
    documento_con(db, fondo, "Oficio 1", b)
    documento_con(db, fondo, "Oficio 2", b)
    documento_con(db, fondo, "Oficio 3", a)
    r = cliente.get(f"/api/vocabulario/identicas?fondo_id={fondo.id}", headers=archivista)
    assert r.status_code == 200, r.text
    assert r.json()["entidades_sobrantes"] == 2 and r.json()["grupos"][0]["veces"] == 3
    r = cliente.post(f"/api/vocabulario/fusionar-identicas?fondo_id={fondo.id}", headers=archivista)
    assert r.status_code == 200, r.text
    assert r.json()["fusionadas"] == 2 and r.json()["relaciones_movidas"] == 1
    for x in (a, b, c):
        db.refresh(x)
    # Queda la más conectada; las otras no se borran: quedan fusionadas en ella.
    assert b.estado == "activa" and a.estado == c.estado == "fusionada" and a.fusionada_en_id == c.fusionada_en_id == b.id
    personas = db.scalars(select(EntidadVocabulario).where(EntidadVocabulario.subtipo == "persona")).all()
    assert all(p.estado == "activa" for p in personas)
    assert cliente.get(f"/api/vocabulario/identicas?fondo_id={fondo.id}", headers=archivista).json()["grupos"] == []


def test_actos_con_numero_distinto_no_son_duplicados(db, fondo):  # noqa: F811
    assert vocabulario.numeros_distintos("resolucion 0123 de 2015", "resolucion 124 de 2015")
    assert not vocabulario.numeros_distintos("resolucion 0123 de 2015", "resolucion 123 de 2015")
    assert not vocabulario.numeros_distintos("ley 594 de 2000", "ley general de archivos")
    entidad(db, fondo, "Resolución 0123 de 2015", clase="mandato")
    entidad(db, fondo, "Resolución 0124 de 2015", clase="mandato")
    assert vocabulario.detectar_candidatos(db, fondo.id) == 0
    # Una sugerencia ya registrada entre las dos queda obsoleta, no se borra.
    x, y = db.scalars(select(EntidadVocabulario).where(EntidadVocabulario.clase == "mandato")
                      .order_by(EntidadVocabulario.id)).all()
    db.add(SugerenciaFusion(fondo_id=fondo.id, clase="mandato", entidad_a_id=x.id, entidad_b_id=y.id, similitud=0.9))
    db.commit()
    assert vocabulario.depurar_sugerencias(db, fondo.id) == 1
    db.commit()
    assert db.scalar(select(SugerenciaFusion.estado)) == "obsoleta"


def test_la_forma_documental_dudosa_no_entra_y_calidad_la_senala(cliente, db, fondo, archivista):  # noqa: F811
    serie = RecursoDocumental(id=uuid.uuid4(), nivel="subserie", titulo="Reservas forestales", fondo_id=fondo.id,
                              incluido_en_id=fondo.id)
    db.add(serie)
    db.commit()
    series = cuadro.nombres_de_series(db, fondo.id)
    assert "serie" in cuadro.forma_dudosa("RESERVAS FORESTALES", series)
    assert cuadro.forma_dudosa("Acta", series) is None
    # Sin límite de palabras: una tipología larga de la TRD es una forma documental.
    assert cuadro.forma_dudosa("Informe de seguimiento a la ejecución de los planes de manejo ambiental", series) is None
    entidad(db, fondo, "Reservas forestales", clase="forma_documental")
    r = cliente.get(f"/api/fondos/{fondo.id}/calidad", headers=archivista)
    assert r.status_code == 200, r.text
    [h] = [x for x in r.json()["hallazgos"] if x["tipo"] == "forma"]
    assert "Reservas forestales" in h["problema"] and "TRD" in h["accion"]


def test_el_filtro_por_reglas_funciona(cliente, fondo, archivista):  # noqa: F811
    r = cliente.get(f"/api/vocabulario?fondo_id={fondo.id}&clase=regla", headers=archivista)
    assert r.status_code == 200, r.text


def test_la_forma_sale_de_las_tipologias_de_la_trd(db, fondo):  # noqa: F811
    from app.servicios import formas_trd
    from app.servicios.motor import Documento, EntidadPropuesta, Propuesta

    acta = entidad(db, fondo, "Acta", clase="forma_documental")
    resolucion = entidad(db, fondo, "Resolución", clase="forma_documental")
    entidad(db, fondo, "Circular", clase="forma_documental")  # no es tipología de ninguna serie
    serie = RecursoDocumental(id=uuid.uuid4(), nivel="subserie", titulo="Resoluciones", fondo_id=fondo.id,
                              incluido_en_id=fondo.id, formas_miembros=sorted([acta.id, resolucion.id]))
    db.add(serie)
    db.commit()
    assert {f.id for f in formas_trd.tipologias(db, fondo.id)} == {acta.id, resolucion.id}
    texto = "MINISTERIO DE AMBIENTE\n  RESOLUCIÓN   No. 0123\nPor la cual se aprueba el acta de la reunión"
    doc = Documento(id=uuid.uuid4(), nombre="r.pdf", texto=texto)
    # El motor propuso «Circular», que no es tipología: queda la de la TRD que declara el encabezado.
    p = Propuesta(entidades=[EntidadPropuesta(clave="p1", tipo="forma_documental", valor="Circular", confianza=0.6)])
    formas_trd.ajustar(db, fondo.id, p, [doc])
    [f] = [e for e in p.entidades if e.tipo == "forma_documental"]
    assert f.existente_id == str(resolucion.id) and f.valor == "Resolución" and f.confianza == 0.9
    assert texto[f.inicio:f.inicio + len(f.fragmento)] == f.fragmento == "RESOLUCIÓN"
    # Sin forma propuesta, se agrega; si el motor ya eligió una tipología, no se toca.
    p = Propuesta()
    formas_trd.ajustar(db, fondo.id, p, [doc])
    assert p.entidades[0].existente_id == str(resolucion.id)
    p = Propuesta(entidades=[EntidadPropuesta(clave="p1", tipo="forma_documental", valor="Acta", existente_id=str(acta.id))])
    formas_trd.ajustar(db, fondo.id, p, [doc])
    assert p.entidades[0].existente_id == str(acta.id)
    # «Acta» dentro de otra palabra no cuenta («Actas» sí sería otra forma).
    p = Propuesta()
    formas_trd.ajustar(db, fondo.id, p, [Documento(id=uuid.uuid4(), nombre="x", texto="Contractual sin forma")])
    assert p.entidades == []


def test_la_clasificacion_usa_la_tipologia_y_el_expediente_citado(db, fondo):  # noqa: F811
    from app.servicios import descripcion

    resolucion = entidad(db, fondo, "Resolución", clase="forma_documental")
    con_tipologia = RecursoDocumental(id=uuid.uuid4(), nivel="subserie", titulo="Procesos ambientales de sustracción",
                                      fondo_id=fondo.id, incluido_en_id=fondo.id, formas_miembros=[resolucion.id])
    sin_tipologia = RecursoDocumental(id=uuid.uuid4(), nivel="subserie", titulo="Informes ambientales de sustracción",
                                      fondo_id=fondo.id, incluido_en_id=fondo.id)
    db.add_all([con_tipologia, sin_tipologia])
    db.flush()
    expediente = RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo="Expediente SRF-676 sustracción Almaguer",
                                   fondo_id=fondo.id, incluido_en_id=con_tipologia.id)
    db.add(expediente)
    db.commit()
    texto = "RESOLUCIÓN No. 1923\nPor la cual se resuelve un recurso ambiental de sustracción, expediente SRF 676"
    [primera, segunda, *_] = descripcion.sugerir_ubicacion(db, fondo.id, texto)
    assert primera["id"] == expediente.id and primera["palabras"] == ["expediente SRF 676"]
    assert segunda["id"] == con_tipologia.id and "tipología resolución" in segunda["palabras"]


def test_una_resolucion_no_va_a_conceptos_tecnicos_por_mencionarlos(db, fondo):  # noqa: F811
    """El texto de una resolución dice «conceptos técnicos ambientales», pero su encabezado dice qué es: va en la
    serie que recibe resoluciones según la TRD, no en la que solo comparte palabras."""
    from app.servicios import descripcion

    resolucion = entidad(db, fondo, "Resolución", clase="forma_documental")
    concepto = entidad(db, fondo, "Concepto técnico", clase="forma_documental")
    conceptos = RecursoDocumental(id=uuid.uuid4(), nivel="subserie", titulo="Conceptos Técnicos Ambientales sobre sustracción",
                                  fondo_id=fondo.id, incluido_en_id=fondo.id, formas_miembros=[concepto.id])
    resoluciones = RecursoDocumental(id=uuid.uuid4(), nivel="subserie", titulo="Resoluciones",
                                     fondo_id=fondo.id, incluido_en_id=fondo.id, formas_miembros=[resolucion.id])
    db.add_all([conceptos, resoluciones])
    db.commit()
    texto = ("RESOLUCIÓN No. 1919 del 31 de diciembre de 2025\nPor la cual se resuelve un recurso de reposición. "
             + "Según los conceptos técnicos ambientales de sustracción emitidos por la Dirección, " * 20)
    [primera, *_] = descripcion.sugerir_ubicacion(db, fondo.id, texto)
    assert primera["id"] == resoluciones.id and "tipología resolución" in primera["palabras"]
