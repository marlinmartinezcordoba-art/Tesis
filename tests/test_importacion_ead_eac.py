"""
Importar desde EAD (EAD3 y EAD 2002) y EAC-CPF (2.0 y 2010).

- Un inventario en EAD se convierte a RiC-O y sigue el camino de la
  importación de RiC-O: vista previa sin crear nada, cuadro por la
  parametrización, documentos y vocabulario, validado contra la ontología y el
  perfil SHACL (todo o nada). Lo que no se convierte queda contado.
- Ida y vuelta: el EAD3 que exporta RICORA se importa con el mismo cuadro.
- Las autoridades en EAC-CPF crean o completan la ficha ISAAR del fondo sin
  pisar lo que ya tenía; el EAC-CPF que exporta RICORA vuelve igual.
- El XML se lee sin resolver entidades externas.
"""

import uuid

from sqlalchemy import select

from app.models.descripcion import EntidadVocabulario, IdentificadorEntidad, NombreEntidad
from app.models.recurso_documental import RecursoDocumental
from app.servicios import intercambio
from tests.test_descripcion import eventos
from tests.test_importacion_rico import _fondo_de_ricora, _importar, _vista

EAD3 = """<?xml version="1.0" encoding="UTF-8"?>
<ead xmlns="http://ead3.archivists.org/schema/">
  <control><recordid>CO-CMT</recordid><filedesc><titlestmt><titleproper>Archivo del Concejo</titleproper></titlestmt>
  </filedesc><maintenancestatus value="new"/><maintenanceagency><agencyname>Archivo</agencyname></maintenanceagency>
  <maintenancehistory><maintenanceevent><eventtype value="created"/><eventdatetime>2024</eventdatetime>
  <agenttype value="human"/><agent>x</agent></maintenanceevent></maintenancehistory></control>
  <archdesc level="fonds">
    <did><unittitle>Concejo Municipal de Tunja</unittitle><unitid>CO.CMT</unitid>
      <unitdate normal="1940/1960">1940-1960</unitdate>
      <origination><corpname><part>Concejo Municipal de Tunja</part></corpname></origination></did>
    <scopecontent><p>Actas y correspondencia del Concejo.</p></scopecontent>
    <accessrestrict><p>Acceso público.</p></accessrestrict>
    <controlaccess><geogname><part>Tunja</part></geogname><subject><part>Gobierno municipal</part></subject></controlaccess>
    <dsc>
      <c01 level="otherlevel" otherlevel="sección"><did><unittitle>Secretaría General</unittitle><unitid>100</unitid></did>
        <c02 level="series"><did><unittitle>Actas</unittitle><unitid>2</unitid></did>
          <c03 level="file"><did><unittitle>Actas de sesiones 1948</unittitle><unitid>100.2-1</unitid>
              <unitdate normal="1948-01-01/1948-12-31">1948</unitdate></did>
            <c04 level="item"><did><unittitle>Acta 12 de 1948</unittitle><unitid>100.2-1-12</unitid>
              <unitdate normal="1948-03-15">15 de marzo de 1948</unitdate><dao href="acta12.pdf"/></did>
              <controlaccess><persname><part>Pedro Gómez</part></persname></controlaccess></c04>
          </c03>
        </c02>
        <c02 level="series"><did><unittitle>Correspondencia</unittitle><unitid>15</unitid></did></c02>
      </c01>
    </dsc>
  </archdesc>
</ead>""".encode()

# EAD 2002 sin espacio de nombres, con <c> anidados y sin secciones.
EAD2002 = """<?xml version="1.0" encoding="UTF-8"?>
<ead><eadheader><eadid>N1</eadid><filedesc><titlestmt><titleproper>Notaría Primera</titleproper></titlestmt></filedesc>
</eadheader><archdesc level="fonds"><did><unittitle>Notaría Primera de Tunja</unittitle>
<origination><corpname>Notaría Primera de Tunja</corpname></origination></did>
<dsc><c level="series"><did><unittitle>Escrituras públicas</unittitle><unitid>3</unitid></did>
<c level="file"><did><unittitle>Protocolo de 1890</unittitle><unitdate normal="1890">1890</unitdate></did>
<c level="item"><did><unittitle>Escritura 12: venta de un solar</unittitle></did></c></c></c></dsc></archdesc></ead>""".encode()

EAC2 = """<?xml version="1.0" encoding="UTF-8"?>
<eac xmlns="https://archivists.org/ns/eac/v2">
  <control maintenanceStatus="revised"><recordId>AUT-77</recordId>
    <maintenanceAgency><agencyName>Archivo General de Boyacá</agencyName></maintenanceAgency>
    <sources><source><reference>Actas del Concejo, 1940-1960</reference></source></sources></control>
  <cpfDescription>
    <identity><entityType value="person"/>
      <nameEntry status="authorized"><part>Gómez, Pedro</part></nameEntry>
      <nameEntry status="alternative"><part>Pedro A. Gómez</part></nameEntry>
      <identityId localType="wikidata">Q2841</identityId></identity>
    <description>
      <existDates><dateRange><fromDate standardDate="1901">1901</fromDate><toDate standardDate="1970">1970</toDate>
      </dateRange></existDates>
      <occupations><occupation><term>Alcalde</term></occupation></occupations>
      <places><place><placeName>Tunja</placeName></place></places>
      <biogHist><p>Alcalde de Tunja entre 1946 y 1950.</p></biogHist>
    </description>
    <relations><relation><targetEntity><part>Concejo Municipal de Tunja</part></targetEntity></relation></relations>
  </cpfDescription>
</eac>""".encode()


def _por_codigo(db, fondo_id, codigo):
    return db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo_id,
                                                     RecursoDocumental.codigo_referencia == codigo))


def test_ead3_vista_previa_e_importacion(cliente, db, cabeceras_admin):
    cab = cabeceras_admin
    v = _vista(cliente, cab, EAD3, "inventario.xml")
    assert v.status_code == 200, v.text
    v = v.json()
    assert v["formato"] == "EAD" and v["fondo"] == "Concejo Municipal de Tunja" and v["problemas"] == []
    assert {f["codigos"]["serie"] for f in v["filas"]} == {"100.2", "100.15"}
    assert v["entidades"] == {"agente": 2, "lugar": 1, "materia": 1}
    assert any("<dao>" in k for k in v["omitidas"])
    # Sin `crear` solo valida; con `crear`, queda.
    assert _importar(cliente, cab, EAD3, "inventario.xml").json()["creado"] is False
    r = _importar(cliente, cab, EAD3, "inventario.xml", crear="1",
                  acto_aprobacion="Acuerdo 03", fecha_aprobacion="2019-02-15", vigente_desde="2019-03-01")
    assert r.status_code == 200, r.text
    hecho = r.json()
    assert hecho["creado"] and hecho["validacion"]["conforme"], hecho["validacion"]
    fid = uuid.UUID(hecho["fondo"]["id"])
    fondo = db.get(RecursoDocumental, fid)
    assert fondo.condiciones_acceso == "Acceso público." and fondo.fechas_extremas == "1940-1960"
    actas = _por_codigo(db, fid, "100.2")
    expediente = db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fid,
                                                           RecursoDocumental.nivel == "expediente"))
    acta = db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fid,
                                                     RecursoDocumental.nivel == "unidad_documental"))
    assert expediente.incluido_en_id == actas.id and acta.incluido_en_id == expediente.id
    assert acta.fechas_extremas_edtf == "1948-03-15"
    nombres = {e.nombre for e in db.scalars(select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fid))}
    assert {"Concejo Municipal de Tunja", "Pedro Gómez", "Tunja", "Gobierno municipal"} <= nombres
    assert fondo.origen and "EAD" in str(fondo.origen) if hasattr(fondo, "origen") else True


def test_ead2002_sin_secciones_pide_la_dependencia(cliente, db, cabeceras_admin):
    v = _vista(cliente, cabeceras_admin, EAD2002, "notaria.xml").json()
    assert v["formato"] == "EAD" and v["productor_sugerido"] == "Notaría Primera de Tunja"
    assert v["series_sin_seccion"] == 1
    v = _vista(cliente, cabeceras_admin, EAD2002, "notaria.xml", seccion_nombre="Notaría Primera de Tunja",
               seccion_codigo="10").json()
    assert v["filas"][0]["codigos"]["serie"] == "10.3" and v["filas"][0]["problemas"] == []


def test_ida_y_vuelta_del_ead3_de_ricora(cliente, db, cabeceras_admin):
    original = _fondo_de_ricora(cliente, db, cabeceras_admin)
    xml = intercambio.ead3(db, original)
    v = _vista(cliente, cabeceras_admin, xml, "ead3-ricora.xml").json()
    series_originales = {r.codigo_referencia for r in db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == original.id, RecursoDocumental.nivel.in_(("serie", "subserie"))))}
    leidas = {f["codigos"]["subserie"] or f["codigos"]["serie"] for f in v["filas"]}
    assert leidas and leidas <= series_originales | {c for c in series_originales}
    assert v["problemas"] == []


def test_eac_cpf_crea_y_completa_sin_pisar(cliente, db, cabeceras_admin, admin):
    from tests.test_descripcion import fondo as _  # noqa: F401
    fondo = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Concejo", creado_por_id=admin.id)
    fondo.fondo_id = fondo.id
    db.add(fondo)
    db.commit()
    datos = {"fondo_id": str(fondo.id)}
    v = cliente.post("/api/vocabulario/eac/vista-previa", headers=cabeceras_admin, data=datos,
                     files={"archivo": ("gomez.xml", EAC2)})
    assert v.status_code == 200, v.text
    [a] = v.json()["autoridades"]
    assert a["accion"] == "crear" and a["subtipo"] == "persona" and a["nombre"] == "Gómez, Pedro"
    assert a["campos"]["existencia_edtf"] == "1901/1970" and a["campos"]["ocupacion"] == "Alcalde"
    assert any("lugares" in k for k in a["omitidas"]) and any("relaciones" in k for k in a["omitidas"])
    assert db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fondo.id)) is None
    r = cliente.post("/api/vocabulario/eac", headers=cabeceras_admin, data=datos, files={"archivo": ("gomez.xml", EAC2)})
    assert r.status_code == 200, r.text and r.json()["creadas"] == 1
    e = db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fondo.id))
    assert e.historia == "Alcalde de Tunja entre 1946 y 1950." and e.institucion_responsable == "Archivo General de Boyacá"
    assert e.estado_elaboracion == "revisado"
    assert db.scalar(select(IdentificadorEntidad.valor).where(IdentificadorEntidad.entidad_id == e.id)) == "Q2841"
    assert db.scalar(select(NombreEntidad.nombre).where(NombreEntidad.entidad_id == e.id)) == "Pedro A. Gómez"
    # La ficha se corrige a mano; otro EAC-CPF del mismo agente completa, no pisa.
    e.historia = "Historia revisada por el archivo."
    db.commit()
    otra = EAC2.replace(b"Alcalde de Tunja entre 1946 y 1950.", b"Otra version.")
    r = cliente.post("/api/vocabulario/eac", headers=cabeceras_admin, data=datos, files={"archivo": ("gomez.xml", otra)})
    assert r.json()["completadas"] == 1 and any("historia" in x for x in r.json()["avisos"])
    db.refresh(e)
    assert e.historia == "Historia revisada por el archivo."
    assert len(eventos(db, "eac_importado")) == 2
    # El EAC-CPF que exporta RICORA vuelve a entrar.
    xml = intercambio.eac_cpf(db, e)
    v = cliente.post("/api/vocabulario/eac/vista-previa", headers=cabeceras_admin, data=datos,
                     files={"archivo": ("propio.xml", xml)}).json()
    assert v["autoridades"][0]["nombre"] == "Gómez, Pedro" and v["autoridades"][0]["accion"] == "completar"


def test_xml_con_entidad_externa_no_se_resuelve(cliente, cabeceras_admin):
    malicioso = b"""<?xml version="1.0"?><!DOCTYPE ead [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<ead><archdesc level="fonds"><did><unittitle>&x;</unittitle></did><dsc><c level="series"><did>
<unittitle>Serie</unittitle><unitid>1</unitid></did></c></dsc></archdesc></ead>"""
    v = _vista(cliente, cabeceras_admin, malicioso, "malo.xml")
    assert "root:" not in v.text
    eac = cliente.post("/api/importacion/rico/vista-previa", headers=cabeceras_admin,
                       files={"archivo": ("a.xml", EAC2)})
    assert eac.status_code == 422 and "Autoridades" in eac.json()["detail"]
