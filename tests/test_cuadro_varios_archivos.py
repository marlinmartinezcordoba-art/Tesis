"""TRD en varios archivos (uno por dependencia): el resultado de cada archivo, con su motivo si no se leyó."""

import io
import zipfile

from app.servicios import cuadro

CSV = ("Código;Dependencia;Serie;Subserie;Tipo documental;Archivo de gestión;Archivo central;Disposición final\n"
       "100;Despacho;Actas;;Acta;2;8;CT\n").encode("utf-8")


def test_cada_archivo_dice_si_se_leyo_y_por_que_no():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("1000_TRD_Despacho.csv", CSV)
        z.writestr("1001_TRD_Comunicaciones.pdf", b"%PDF-1.4 roto")
        z.writestr("1002_otra_cosa.csv", "nada;aqui\n1;2\n")
    v = cuadro.vista_previa(b.getvalue(), "TRD.zip")
    estados = {a["archivo"]: a for a in v["archivos"]}
    assert estados["1000_TRD_Despacho.csv"]["estado"] == "leido" and estados["1000_TRD_Despacho.csv"]["filas"] == 1
    assert estados["1001_TRD_Comunicaciones.pdf"]["estado"] == "sin_leer"
    assert "(" not in estados["1001_TRD_Comunicaciones.pdf"]["motivo"]
    assert estados["1002_otra_cosa.csv"]["estado"] == "sin_tabla" and "Serie" in estados["1002_otra_cosa.csv"]["motivo"]


def test_un_solo_archivo_tambien_informa():
    v = cuadro.vista_previa(CSV, "TRD.csv")
    assert v["archivos"] == [{"archivo": "TRD.csv", "estado": "leido", "filas": 1, "con_problemas": v["archivos"][0]["con_problemas"],
                              "motivo": None}]


class MotorFalso:
    modelo = "prueba"

    def __init__(self):
        self.textos = []

    def estructurar(self, instruccion, texto, esquema):
        self.textos.append(texto)
        return {"filas": [
            {"codigo_seccion": "1000", "seccion": "Despacho del Ministro", "codigo_serie": "1000-12", "serie": "Informes",
             "codigo_subserie": "1000-12.3", "subserie": "Informes de gestión", "tipos": ["Informe", "Anexos"],
             "ag": 2, "ac": 8, "ct": True, "e": False, "s": False, "m": True, "procedimiento": "Se conserva."},
            {"codigo_seccion": "1000", "seccion": "Despacho del Ministro", "codigo_serie": "1000-2", "serie": "Actas",
             "tipos": ["Acta"], "ag": 2, "ac": 18, "ct": True, "procedimiento": ""}]}


def test_una_tabla_rara_la_lee_el_motor_y_queda_para_revisar(monkeypatch):
    from app.servicios import motor
    m = MotorFalso()
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    # Un archivo cuyo «encabezado» se lee como filas sueltas: la lectura por reglas sale floja.
    raro = ("Serie;Subserie;Tipo documental;Archivo de gestión;Archivo central;Disposición final\n"
            "SECCIÓN.3 Vigencia: 11/06/2019;SECCIÓN.3.UNIDAD;;;;\n"
            "AMBIENTE TABLA DE RETENCIÓN DOCUMENTAL;;Proceso;;;\n").encode("utf-8")
    v = cuadro.vista_previa(raro, "1000_TRD-V2_Despacho.csv")
    assert v["archivos"][0]["estado"] == "leido_ia" and v["archivos"][0]["filas"] == 2
    assert "motor de análisis" in v["origen"]
    series = {f["serie"]["nombre"] for f in v["filas"]}
    assert series == {"Informes", "Actas"}
    assert m.textos and "Vigencia" in m.textos[0]


def test_sin_motor_se_queda_la_lectura_por_reglas(monkeypatch):
    from app.servicios import motor
    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    v = cuadro.vista_previa(CSV, "TRD.csv")
    assert v["archivos"][0]["estado"] == "leido"
