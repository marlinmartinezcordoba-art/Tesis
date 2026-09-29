"""F01/F02/F03/F04: lo que pasa automáticamente al ingerir un archivo nuevo.

El hash ya lo calcula `Instantiation.save()` solo (F01); aquí van el OCR
(F02), la detección de estructura (F03) y la propuesta de segmentación
(F04), para que el archivista no tenga que acordarse de pedirlos aparte.

Un único punto de entrada (`ingerir`) usado tanto por el panel técnico
(admin) como por la pantalla simple de "Subir documento" — el mismo
comportamiento sin importar por dónde se suba el archivo.
"""


def ingerir(instanciacion, agente):
    """Si el formato no tiene OCR soportado, el archivo igual queda
    preservado (el hash es lo que garantiza F01; lo demás son pasos
    aparte, best-effort). La segmentación solo PROPONE: nunca separa el
    archivo sola (ver PropuestaSegmentacion.validar). Devuelve un dict con
    lo que pasó, para que la interfaz se lo pueda mostrar a la persona."""
    from .estructura import detectar_y_guardar_estructura
    from .extraccion import FormatoNoSoportado, extraer_texto_de_instanciacion
    from .segmentacion import detectar_y_proponer_segmentos

    resultado = {
        "texto_extraido": False, "paginas": 0, "caracteres": 0, "confianza_ocr": None,
        "componentes": 0, "segmentos_propuestos": 0, "formato_no_soportado": False,
    }
    try:
        _, detalle = extraer_texto_de_instanciacion(instanciacion, agente=agente)
    except FormatoNoSoportado:
        resultado["formato_no_soportado"] = True
        return resultado

    resultado.update(
        texto_extraido=True, paginas=detalle["paginas"],
        caracteres=detalle["caracteres"], confianza_ocr=detalle["confianza_ocr"],
    )
    componentes = detectar_y_guardar_estructura(instanciacion)
    resultado["componentes"] = len(componentes)
    segmentos = detectar_y_proponer_segmentos(instanciacion)
    resultado["segmentos_propuestos"] = len(segmentos)
    return resultado


def preprocesar(instanciacion, agente):
    """M2 completo sobre un archivo ya cargado (M1): OCR/texto nativo,
    idioma (RF-M2-03), marca de páginas de calidad baja (RF-M2-04) y,
    si no queda ninguna página por decidir, entrega automática al motor
    de análisis (M3) — el paso 7 del flujo "Cargar y procesar"."""
    from .idioma import detectar_idioma, nombre_idioma
    from .motor import enviar_al_motor

    resultado = ingerir(instanciacion, agente)
    resultado.update(idioma="", calidad_baja=0, analisis=None)
    if not resultado["texto_extraido"]:
        return resultado

    codigo = detectar_idioma(instanciacion.texto_extraido)
    instanciacion.idioma_detectado = codigo
    instanciacion.save(update_fields=["idioma_detectado"])
    record = instanciacion.record_resource
    if codigo and not record.idioma:
        record.idioma = nombre_idioma(codigo)
        record.save(update_fields=["idioma"])
    resultado["idioma"] = codigo

    resultado["calidad_baja"] = instanciacion.paginas_calidad_baja().count()
    if resultado["calidad_baja"]:
        return resultado  # queda marcada para que la persona decida antes de continuar

    from .models import Record

    documento = Record.objects.filter(pk=record.pk).first()  # la FK apunta a RecordResource
    if documento is None:
        return resultado  # un RecordSet/RecordPart: el motor solo analiza Records
    resultado["analisis"] = enviar_al_motor(documento, agente)
    return resultado
