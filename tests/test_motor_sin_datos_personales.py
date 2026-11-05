"""
Lo que sale hacia el motor de análisis (servicio externo) no lleva identificadores personales
(Ley 1581 de 2012): se reemplazan por su tipo con las reglas locales del detector.
"""

from app.servicios.datos_personales import anonimizar_para_motor


def test_quita_identificadores_y_deja_el_sentido():
    texto = ("Resolución 120 de 1975. El señor Pedro Gómez, identificado con cédula de ciudadanía 79.123.456, "
             "correo pedro.gomez@gmail.com, solicita licencia de aprovechamiento forestal en Montería.")
    limpio, n = anonimizar_para_motor(texto)
    assert "79.123.456" not in limpio and "pedro.gomez@gmail.com" not in limpio
    assert n >= 2 and "[Correo electrónico]" in limpio
    # Lo que el motor necesita para describir sigue ahí.
    assert "Pedro Gómez" in limpio and "Resolución 120 de 1975" in limpio and "Montería" in limpio


def test_texto_vacio():
    assert anonimizar_para_motor("") == ("", 0)
    assert anonimizar_para_motor(None) == ("", 0)
