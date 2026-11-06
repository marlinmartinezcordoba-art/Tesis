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
