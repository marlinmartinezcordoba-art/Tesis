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


def test_propone_el_nombre_de_la_entidad_del_encabezado():
    """El encabezado «ENTIDAD: …» de la TRD se propone como nombre del fondo; si no está, no se inventa."""
    from app.servicios.cuadro import _entidad

    assert _entidad([[["ENTIDAD:", "", "Instituto Nacional de los Recursos Naturales (INDERENA)"], ["Serie"]]]) == \
        "Instituto Nacional de los Recursos Naturales (INDERENA)"
    assert _entidad([[["Nombre de la entidad: Alcaldía de Tunja"]]]) == "Alcaldía de Tunja"
    assert _entidad([[["Serie", "Subserie"], ["Actas", ""]]]) is None


def test_la_s_suelta_entre_ct_e_m_es_seleccion_y_no_codigo_de_serie():
    """En «CT | E | S | M», la S es la selección de la disposición final, no el código de la serie."""
    from app.servicios.cuadro import vista_previa

    csv = ("Código,Dependencia,Código serie,Serie,Subserie,Tipos documentales,AG,AC,CT,E,S,M,Procedimiento\n"
           "100,Dirección General,2,Informes,Informes de gestión,Informe,2,5,,,X,,Seleccionar muestra\n")
    fila = vista_previa(csv.encode(), "trd.csv")["filas"][0]
    assert fila["disposicion"] == "s"
    assert fila["codigos"]["serie"] == "100.2"
    assert not fila["problemas"]


def test_sin_motor_explica_por_que_no_se_leyo_un_formato_distinto():
    """Un archivo del .zip sin tabla reconocible, y sin motor: el motivo dice qué hacer."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("TRD.csv", CSV.decode())
        z.writestr("otra.csv", "Lo que sea,Otra cosa\nuno,dos\n")
    v = cuadro.vista_previa(buf.getvalue(), "TRD.zip")
    otra = next(a for a in v["archivos"] if a["archivo"] == "otra.csv")
    assert otra["estado"] == "sin_tabla"
    assert "motor de análisis" in otra["motivo"]


def test_en_el_zip_cada_fila_tiene_su_numero_aunque_los_archivos_repitan():
    """Dos dependencias en archivos distintos traen «fila 2»: se numeran de corrido para marcarlas por separado."""
    import io
    import zipfile

    cab = "Código,Dependencia,Código serie,Serie,Subserie,Tipos documentales,AG,AC,CT,E,S,M,Procedimiento\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.csv", cab + "100,Despacho,1,Actas,,Acta,2,8,X,,,,C\n")
        z.writestr("b.csv", cab + "200,Comunicaciones,1,Informes,,Informe,2,5,,,X,,S\n")
    filas = cuadro.vista_previa(buf.getvalue(), "TRD.zip")["filas"]
    assert len({f["fila"] for f in filas}) == 2
    assert {f["parte"] for f in filas} == {"a.csv", "b.csv"}


def test_trd_en_pdf_con_el_encabezado_en_vertical():
    """Una TRD en PDF con el encabezado girado 90° (sale al revés: «EIRES», «OGIDÓC», «TC»), los nombres completos
    en la fila de abajo («DEPENDENCIA», «ARCHIVO GESTIÓN») y palabras partidas («RETENCI/ÓN»): se lee completa."""
    from pathlib import Path

    contenido = (Path(__file__).parent / "datos" / "trd_encabezado_vertical.pdf").read_bytes()
    v = cuadro.vista_previa(contenido, "1000_TRD-V2_Despacho del Ministro.pdf")
    assert v["entidad"] == "MINISTERIO DE AMBIENTE Y DESARROLLO SOSTENIBLE"
    filas = v["filas"]
    assert [(f["serie"]["nombre"], f["subserie"]["nombre"]) for f in filas] == [
        ("ACTAS", "Actas de Comité Directivo"), ("INFORMES", "Informes de Gestión")]
    assert {f["seccion"]["nombre"] for f in filas} == {"DESPACHO DEL MINISTRO"}
    assert [(f["gestion"], f["central"], f["disposicion"]) for f in filas] == [(2, 8, "ct"), (2, 5, "s")]
    assert filas[0]["tipos"] == ["Acta", "Citación"]
    assert not any(f["problemas"] for f in filas)


def test_enderezar_solo_toca_encabezados_al_reves():
    from app.servicios.cuadro import _enderezar

    assert _enderezar("EIRES") == "SERIE"
    assert _enderezar("NÓITSEG\nOVIHCRA") == "ARCHIVO\nGESTIÓN"
    assert _enderezar("TC") == "CT"
    assert _enderezar("Actas de Comité Directivo") == "Actas de Comité Directivo"
    assert _enderezar("SERIE") == "SERIE"
    assert _enderezar("2") == "2"


def test_si_ningun_archivo_se_lee_dice_el_motivo_de_cada_uno():
    """Cuando nada se lee, el aviso dice por qué cada archivo falló: escaneado no es lo mismo que una tabla sin «Serie»."""
    import io
    import zipfile

    import pytest

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("otra.csv", "Lo que sea,Otra cosa\nuno,dos\n")
        z.writestr("roto.pdf", "%PDF-1.4 nada")
    with pytest.raises(cuadro.ErrorCuadro) as exc:
        cuadro.vista_previa(buf.getvalue(), "TRD.zip")
    texto = str(exc.value)
    assert "otra.csv: trae texto, pero no se reconoció la columna «Serie»" in texto
    assert "roto.pdf: No se pudo abrir el PDF" in texto


def test_pdf_escaneado_de_lado_se_lee_con_ocr_y_la_ia(monkeypatch):
    """Un PDF escaneado (solo imagen, sin texto) y girado 90°, como muchas TRD antiguas: se endereza,
    se le pasa OCR conservando las filas y la IA arma la tabla. El original no se modifica."""
    import io
    import shutil
    import zipfile
    from pathlib import Path

    import pytest

    from app.servicios import motor

    if not shutil.which("tesseract"):
        pytest.skip("Sin Tesseract en este equipo")
    m = MotorFalso()
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    pdf = (Path(__file__).parent / "datos" / "trd_escaneada_de_lado.pdf").read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("1000_TRD-V2_Despacho del Ministro.pdf", pdf)
    v = cuadro.vista_previa(buf.getvalue(), "TRD.zip")
    a = v["archivos"][0]
    assert a["estado"] == "leido_ia" and a["filas"] == 2
    assert "escaneado" in a["motivo"] and "OCR" in a["motivo"]
    # A la IA le llegó el texto del OCR, enderezado y con la fila de la serie en su renglón.
    assert "MINISTERIO DE AMBIENTE" in m.textos[0]
    assert any("Actas de Comit" in linea and "1000" in linea for linea in m.textos[0].splitlines())


def test_pdf_escaneado_sin_motor_explica_que_hacer(monkeypatch):
    from pathlib import Path

    import pytest

    from app.servicios import motor

    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    pdf = (Path(__file__).parent / "datos" / "trd_escaneada_de_lado.pdf").read_bytes()
    with pytest.raises(cuadro.ErrorCuadro, match="OCR"):
        cuadro.vista_previa(pdf, "TRD.pdf")


def test_con_filas_buenas_no_se_llama_a_la_ia_y_es_rapido(monkeypatch):
    """Como antes: si las reglas sacan filas buenas, la IA no entra (segundos, no minutos). La fila dudosa
    queda marcada para que la persona la desmarque."""
    from app.servicios import motor
    m = MotorFalso()
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    csv = ("Código,Dependencia,Código serie,Serie,Subserie,Tipos documentales,AG,AC,CT,E,S,M,Procedimiento\n"
           "100,Despacho,1,Actas,,Acta,2,8,X,,,,C\n"
           "100,Despacho,2,Informes,,Informe,2,5,,,X,,S\n"
           "100,Despacho,3,TABLA DE RETENCIÓN DOCUMENTAL Vigencia 2019,,,,,,,,,\n").encode("utf-8")
    v = cuadro.vista_previa(csv, "TRD.csv")
    assert v["archivos"][0]["estado"] == "leido"
    assert not m.textos  # la IA no se consultó


def test_subseries_sin_codigo_se_numeran_y_lo_avisan():
    """TRD antiguas sin código en la subserie: RICORA las numera dentro de su serie y la fila lo avisa,
    para que se puedan guardar todas y la persona verifique el código."""
    csv = ("Código,Dependencia,Código serie,Serie,Subserie,Tipos documentales,AG,AC,CT,E,S,M,Procedimiento\n"
           "1000,Despacho,2,Actas,Actas de comité,Acta,2,8,X,,,,C\n"
           "1000,Despacho,2,Actas,Actas de junta,Acta,2,8,X,,,,C\n"
           "1000,Despacho,,Informes,,Informe,2,5,,,X,,S\n").encode("utf-8")
    filas = cuadro.vista_previa(csv, "TRD.csv")["filas"]
    assert [f["codigos"]["subserie"] for f in filas[:2]] == ["1000.2.1", "1000.2.2"]
    assert filas[2]["serie"]["codigo"] == "3" and "asignado por RICORA" in filas[2]["avisos"][0]
    assert all(not f["problemas"] for f in filas)


def test_el_codigo_de_la_dependencia_sale_del_nombre_del_archivo():
    """TRD publicadas una por dependencia («4104_Grupo_Tesorería.pdf»): si la tabla no trae el código de la
    dependencia, se toma del nombre del archivo y se avisa; «dependencias y entidades del sector» no es una dependencia."""
    import io
    import zipfile

    cab = "Dependencia,Código serie,Serie,Subserie,Tipos documentales,AG,AC,CT,E,S,M,Procedimiento\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("4104_Grupo_Tesorería.csv", cab + "Grupo de Tesorería,2,Actas,,Acta,2,8,X,,,,C\n")
        z.writestr("4106_Grupo_Gestión_Documental.csv", cab + "Grupo de Gestión Documental,5,Inventarios,,Inventario,2,8,X,,,,C\n")
    v = cuadro.vista_previa(buf.getvalue(), "TRD.zip")
    codigos = {f["seccion"]["nombre"]: f["seccion"]["codigo"] for f in v["filas"]}
    assert codigos == {"Grupo de Tesorería": "4104", "Grupo de Gestión Documental": "4106"}
    assert all(not f["problemas"] for f in v["filas"]) and "nombre del archivo" in v["filas"][0]["avisos"][0]
    assert {p["sugerido"] for p in v["partes"]} == {"trd"}
    assert cuadro.DEPENDENCIA.search("las dependencias y entidades del sector") is None



def test_un_archivo_largo_se_envia_a_la_ia_por_tramos_de_paginas(monkeypatch):
    """Una TVD de muchas páginas: antes se cortaba en 80 000 caracteres y se perdían las series del final."""
    from app.servicios import motor, trd_ia

    textos = []

    class Motor(MotorFalso):
        max_caracteres = 1000

        def estructurar(self, instruccion, texto, esquema):
            textos.append(texto)
            n = len(textos)
            return {"filas": [{"codigo_seccion": "100", "seccion": "Gerencia", "codigo_serie": str(n),
                               "serie": f"Serie {n}", "tipos": ["Acta"], "ag": 2, "ac": 8, "ct": True}]}

    monkeypatch.setattr(motor, "motor_activo", lambda: Motor())
    largo = "\n\n".join(f"[Página {i}]\n" + "texto de la tabla " * 30 for i in range(1, 11))
    monkeypatch.setattr(trd_ia, "texto_de", lambda *a, **k: largo)
    filas = trd_ia.extraer(b"%PDF", "TVD-INDERENA.pdf")
    assert len(textos) > 3 and "[Página 10]" in textos[-1]
    assert len(filas) == len(textos)
    assert all(len(t) < 1300 for t in textos)


def test_pdf_escaneado_cuando_falla_la_ia_dice_el_motivo_real(monkeypatch):
    """Antes se perdía el motivo del motor y salía «puede ser un PDF escaneado» aunque el OCR sí se pasó."""
    import io
    import shutil
    import zipfile
    from pathlib import Path

    import pytest

    from app.servicios import motor

    if not shutil.which("tesseract"):
        pytest.skip("Sin Tesseract en este equipo")

    class Agotado(MotorFalso):
        def estructurar(self, instruccion, texto, esquema):
            raise motor.MotorError("El motor de análisis alcanzó su límite de uso del día")

    monkeypatch.setattr(motor, "motor_activo", lambda: Agotado())
    pdf = (Path(__file__).parent / "datos" / "trd_escaneada_de_lado.pdf").read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("1000_TRD.pdf", pdf)
        z.writestr("buena.csv", "Código,Dependencia,Código serie,Serie,Subserie,Tipos documentales,AG,AC,CT,E,S,M,"
                                "Procedimiento\n100,Despacho,1,Actas,,Acta,2,8,X,,,,C\n")
    v = cuadro.vista_previa(buf.getvalue(), "TRD.zip")
    a = next(x for x in v["archivos"] if x["archivo"] == "1000_TRD.pdf")
    assert "límite de uso del día" in a["motivo"] and "OCR" in a["motivo"]


def test_el_ocr_estampado_se_hace_una_sola_vez():
    import shutil
    from pathlib import Path

    import pytest

    from app.servicios import trd_ia

    if not shutil.which("tesseract"):
        pytest.skip("Sin Tesseract en este equipo")
    pdf = (Path(__file__).parent / "datos" / "trd_escaneada_de_lado.pdf").read_bytes()
    texto, estampado = trd_ia.ocr_pdf(pdf)
    assert "MINISTERIO DE AMBIENTE" in texto
    assert not trd_ia.es_escaneado(estampado)  # la copia ya trae su capa de texto
    assert trd_ia.ocr_pdf(pdf) is trd_ia.ocr_pdf(pdf)


def test_gemini_espera_el_limite_por_minuto_al_leer_una_trd(monkeypatch):
    import json as _json

    from app.core.config import settings
    from app.servicios import motor

    esperas, respuestas = [], [
        (429, '{"error": {"details": [{"retryDelay": "20s"}]}}'),
        (200, _json.dumps({"candidates": [{"content": {"parts": [{"text": '{"filas": []}'}]}}]}))]

    class R:
        def __init__(self, codigo, texto):
            self.status_code, self.text = codigo, texto

        def json(self):
            return _json.loads(self.text)

    monkeypatch.setattr(settings, "gemini_api_key", "x")
    monkeypatch.setattr(motor.httpx, "post", lambda *a, **k: R(*respuestas.pop(0)))
    monkeypatch.setattr(motor.time, "sleep", esperas.append)
    assert motor.MotorGemini("x", "g").estructurar("i", "t", {}) == {"filas": []}
    assert esperas == [21]


def test_gemini_sin_cuota_del_dia_no_espera_en_vano(monkeypatch):
    import pytest

    from app.servicios import motor

    class R:
        status_code, text = 429, '{"error": {"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}}'

    monkeypatch.setattr(motor.httpx, "post", lambda *a, **k: R())
    esperas = []
    monkeypatch.setattr(motor.time, "sleep", esperas.append)
    with pytest.raises(motor.MotorError, match="del día"):
        motor.MotorGemini("x", "g").estructurar("i", "t", {})
    assert esperas == []


def test_subserie_sin_la_fila_de_su_serie_reconstruye_la_serie_por_su_codigo():
    """TRD antiguas incompletas: la subserie no queda suelta («Falta la serie»); la serie se arma con su código."""
    filas = [["Dependencia: Grupo de Tesorería Código: 4104"],
             ["Código", "", "", "Series, subseries y tipos documentales", "Retención", "", "Disposición final", "", "", "",
              "Procedimiento"],
             ["D", "S", "SB", "", "AG", "AC", "CT", "E", "M", "S", ""],
             ["4104", "27", "1", "Informes de gestión\nInforme", "2", "8", "X", "", "", "", "Se conserva"],
             ["4104", "27", "2", "Informes a entes de control\nInforme", "2", "8", "X", "", "", "", ""]]
    leidas = cuadro._interpretar_hojas([filas])[0]
    assert [f.problemas for f in leidas] == [[], []]
    assert {f.serie.codigo for f in leidas} == {"27"} and leidas[0].serie is leidas[1].serie
    assert "reconstruyó" in leidas[0].avisos[0]


def test_codigo_de_la_dependencia_al_final_del_nombre_del_archivo():
    """«TRD Ultima OK_4106.xlsx»: el código va al final; «acta 2019.pdf» no es una dependencia."""
    from app.servicios.cuadro import FilaCuadro, Nodo, _dependencia_del_archivo, _motivo_frecuente

    f = FilaCuadro(fila=1, seccion=Nodo(None, "Grupo de Contratos"))
    f.problemas = ["La dependencia «Grupo de Contratos» no tiene código en el archivo: …"]
    g = FilaCuadro(fila=2)
    _dependencia_del_archivo([f, g], "TRD Ultima OK_4106.xlsx")
    assert f.seccion == Nodo("4106", "Grupo de Contratos") and f.problemas == []
    assert g.seccion == Nodo("4106", "Dependencia 4106")
    h = FilaCuadro(fila=3)
    _dependencia_del_archivo([h], "acta 2019.pdf")
    assert h.seccion is None
    a, b = FilaCuadro(fila=1), FilaCuadro(fila=2)
    a.problemas, b.problemas = ["Falta la serie."], ["Falta la serie."]
    assert _motivo_frecuente([a, b, FilaCuadro(fila=3)]) == "Falta la serie."
