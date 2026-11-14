"""
Documentos citados (Tabla 3 de la tesis, dimensión 1: recurso documental, RiC-E02 a E06).

El motor propone aparte los otros documentos de archivo que el texto cita por su identificación
(el acto que se recurre, el oficio que se responde). En la evaluación son una clase más
(rico:Record), que se compara como las demás; en la descripción se ofrecen para «Unidades de
descripción relacionadas» y no entran como entidades, así que publicar no cambia.
"""

import uuid

from app.servicios import evaluacion_ric as ric
from app.servicios import motor

TEXTO = ("Por la cual se resuelve un recurso de reposición en contra de la Resolución No. 0818 del 18 de junio de "
         "2025, en el marco del expediente SRF 679.")


def test_el_motor_propone_los_documentos_citados_con_su_fragmento():
    doc = motor.Documento(id=uuid.uuid4(), nombre="res.pdf", texto=TEXTO)
    p = motor.normalizar({"titulo": "Resolución 1919", "alcance_contenido": "Resuelve un recurso.", "entidades": [],
                          "documentos_citados": [
                              {"valor": "Resolución No. 0818 del 18 de junio de 2025", "documento": 1, "confianza": 0.9,
                               "fragmento": "en contra de la Resolución No. 0818 del 18 de junio de 2025"},
                              {"valor": "Expediente SRF 679", "documento": 1, "confianza": 0.9,
                               "fragmento": "texto que no está en el documento"},
                              {"valor": "Expediente SRF 679", "documento": 1, "confianza": 0.9, "fragmento": "x"},
                              {"valor": "", "documento": 1, "confianza": 0.9, "fragmento": "x"}]},
                         [doc], "motor-de-prueba")
    citados = p.a_dict()["documentos_citados"]
    assert [c["valor"] for c in citados] == ["Resolución No. 0818 del 18 de junio de 2025", "Expediente SRF 679"]
    assert citados[0]["fragmento_localizado"] and citados[0]["documento_id"] == str(doc.id)
    # Sin fragmento en el texto, la confianza baja como en las entidades.
    assert not citados[1]["fragmento_localizado"] and citados[1]["confianza"] <= motor.CONFIANZA_SIN_FRAGMENTO
    assert "documentos_citados" in motor.INSTRUCCION and "documentos_citados" in motor.ESQUEMA["properties"]
    assert p.entidades == []  # no se mezclan con las entidades de la descripción


def test_en_la_evaluacion_el_documento_citado_es_un_record_del_que_trata_el_documento():
    ric_motor = ric.desde_roles({"titulo": "Resolución 1919 de 2025", "entidades": [], "documentos_citados": [
        {"valor": "Resolución No. 0818 de 2025", "fragmento": "la Resolución No. 0818", "confianza": 0.9}]})
    [e] = ric_motor["entidades"]
    assert e["tipo"] == "documento_citado" and e["evidencia"] == "la Resolución No. 0818"
    assert ric.clase(e) == "Record"
    assert {"origen": ric.DOCUMENTO, "propiedad": "has_or_had_subject", "destino": e["clave"]} in ric_motor["relaciones"]
    assert ric.conformidad(ric_motor)["conforme"]
    # La archivista lo registra igual, y puede unir dos documentos con «responde a».
    datos = ric.limpiar({"titulo": "Resolución 1919 de 2025", "entidades": [{"clave": "e1", "tipo": "documento_citado", "valor": "Resolución 0818 de 2025"}],
                         "relaciones": [{"origen": ric.DOCUMENTO, "propiedad": "has_reply", "destino": "e1"}]})
    assert datos["entidades"][0]["tipo"] == "documento_citado" and ric.conformidad(datos)["conforme"]
