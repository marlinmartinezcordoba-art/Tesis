"""
Asistente RICORA con IA: responde preguntas de archivística y de uso del sistema.

Usa el mismo motor de análisis que la descripción (Gemini). Tiene dos modos:

- **Con los documentos de la entidad (RAG, el modo inicial).** Antes de responder recupera los
  pasajes que tratan la pregunta en la biblioteca de referencia (leyes, acuerdos, manuales) y en
  los documentos y descripciones publicadas del fondo (app/servicios/rag.py), y el motor responde
  solo con esos pasajes, citándolos con su número. Si no hay pasajes, no se consulta al motor:
  se dice que no está en los documentos. Sin búsqueda en Google.
- **Con internet.** Responde con su conocimiento general y Google Search, citando las páginas.

Reglas comunes:

- No cambia nada. Lo reservado o sin publicar nunca se recupera.
- Lo que la persona escribe sale hacia el servicio de IA. Por eso la pantalla
  advierte que no se escriban datos personales ni información con reserva legal,
  y la auditoría guarda que se consultó, pero no el texto de la pregunta.
- Sin motor configurado, el asistente queda en modo guiado (sin IA).
"""

import re

from sqlalchemy.orm import Session

from app.servicios import motor as servicio_motor
from app.servicios.auditoria import registrar

MAX_TURNOS = 10
MAX_CARACTERES = 1500

AVISO_LOCAL = ("La IA corre en este mismo servidor: lo que escriba no sale de él. Aun así, no escriba datos personales "
               "ni información con reserva legal.")
AVISO = ("Lo que escriba se envía a Gemini, que busca en Google para responder con fuentes. No escriba datos personales ni información "
         "con reserva legal.")

# Pantallas de RICORA, para que el asistente indique dónde se hace cada cosa.
MAPA = """PANTALLAS DE RICORA (menú lateral):
- Inicio: tablero del fondo, recorrido y siguiente paso.
- Instrumentos > TRD y CCD: cargar el cuadro de clasificación y la tabla de retención (paso a paso), cuadro y versiones.
- Instrumentos > TVD: tabla de valoración documental para fondos acumulados.
- Instrumentos > Disposición final: calendario de retención y registro de disposiciones (conservar, eliminar, transferir).
- Carga de documentos: subir archivos (huella SHA-256, OCR), revisar lo cargado.
- Descripción: documentos por describir; el motor propone, la archivista valida, corrige o descarta; descritas.
- Autoridades y términos: agentes, lugares, formas documentales, actividades, mandatos; posibles duplicados; tesauros.
- Consulta y difusión > Catálogo y grafo: buscar y explorar el contexto.
- Consulta y difusión > Instrumentos de descripción: inventario (FUID), guía del fondo, índice.
- Consulta y difusión > Datos enlazados (RiC-O): grafo RiC-O, descargas, consulta SPARQL, adopción de RiC.
- Auditoría: registro de actividad y trazabilidad.
- Evaluación: comparación humano frente a máquina (a ciegas, asistida, calificación).
- Usuarios y permisos: usuarios, roles, biblioteca del asistente (leyes y manuales con los que responde), puesta en marcha (solo administración)."""

INSTRUCCION = f"""Eres el Asistente RICORA, apoyo para archivistas en un sistema de gestión de archivo histórico de Colombia
que describe en Records in Contexts (RiC-CM 1.0 y RiC-O 1.1).

Conoces: RiC-CM y RiC-O, ISAD(G), ISAAR(CPF), ISDF, ISDIAH, EAC-CPF, la Ley 594 de 2000 (Ley General de Archivos),
los acuerdos del Archivo General de la Nación sobre TRD, TVD, FUID y organización de archivos, la Ley 1712 de 2014
(transparencia y acceso) y la Ley 1581 de 2012 (datos personales).

Reglas:
1. Responde en español claro y breve (máximo unas 180 palabras), en lenguaje archivístico sencillo.
2. Sin formato Markdown: nada de asteriscos, almohadillas ni tablas. Para listas usa líneas que empiecen con «- ».
3. No inventes datos del fondo ni de documentos: no los conoces. Si te piden un dato del archivo, di en qué pantalla
   de RICORA se consulta.
4. Si citas una norma y no estás seguro del número de artículo o acuerdo, dilo y recomienda verificarlo en la fuente.
5. Cuando la pregunta sea cómo hacer algo en RICORA, indica la pantalla y los pasos según el mapa de abajo.
6. Las decisiones archivísticas (clasificar, valorar, eliminar) las toma la archivista o el comité: tú orientas.
7. Si te escriben datos personales o información reservada, no los repitas y recuerda no compartirlos.
8. Si buscas en internet, prefiere fuentes oficiales: el Archivo General de la Nación de Colombia (archivogeneral.gov.co), el Consejo Internacional de Archivos (ica.org, para RiC), la Función Pública y las normas colombianas (Ley 594 de 2000, Acuerdo 001 de 2024). No inventes normas ni números de acuerdos.

{MAPA}"""


INSTRUCCION_RAG = f"""Eres el Asistente RICORA, apoyo para archivistas en un sistema de gestión de archivo histórico de Colombia
que describe en Records in Contexts (RiC-CM 1.0 y RiC-O 1.1).

Responde SOLO con los PASAJES numerados que vienen con la pregunta: son fragmentos de las normas, manuales y documentos
que la entidad cargó en RICORA.

Reglas:
1. Usa únicamente lo que dicen los pasajes. No completes con lo que sabes por fuera de ellos.
2. Después de cada afirmación pon entre corchetes el número del pasaje que la sostiene, por ejemplo [2] o [1][3].
3. Si los pasajes no responden la pregunta, o la responden solo en parte, dilo con claridad («Los documentos
   cargados no dicen…») y sugiere cargar la norma o el manual en la biblioteca del asistente o preguntar con internet.
4. No inventes números de artículos, fechas, nombres ni plazos que no estén en los pasajes.
5. Español claro y breve (máximo unas 200 palabras), sin formato Markdown: nada de asteriscos ni almohadillas. Para
   listas usa líneas que empiecen con «- ».
6. Las decisiones archivísticas (clasificar, valorar, eliminar) las toma la archivista o el comité: tú orientas.
7. Si un pasaje trae datos personales, no los repitas.

{MAPA}"""

SIN_PASAJES = ("No encontré nada sobre eso en la biblioteca del asistente ni en los documentos y descripciones "
               "publicadas del fondo. Puede cargar la norma o el manual en Usuarios y permisos › Biblioteca del "
               "asistente, o cambiar arriba a «Internet» y preguntar de nuevo.")


class AsistenteNoDisponible(Exception):
    pass


def estado() -> dict:
    m = servicio_motor.motor_activo()
    # Solo con la IA local sola, la pregunta no sale del servidor; con Gemini, responde Gemini con Google Search.
    local = isinstance(m, servicio_motor.MotorLocal)
    return {"disponible": m is not None, "modelo": getattr(m, "modelo", None) if m else None,
            "aviso": AVISO_LOCAL if local else AVISO, "local": local}


def _contexto(pantalla: dict | None, fondo: str | None) -> str:
    partes = []
    if fondo:
        partes.append(f"Fondo activo: {fondo[:200]}.")
    if pantalla and pantalla.get("titulo"):
        partes.append(f"La persona está en la pantalla «{str(pantalla['titulo'])[:120]}».")
        pasos = [str(p)[:200] for p in (pantalla.get("pasos") or [])[:8]]
        if pasos:
            partes.append("Guía de esa pantalla: " + " | ".join(pasos))
    return "\n".join(partes)


def preguntar(db: Session, usuario_id, mensajes: list[dict], pantalla: dict | None = None, fondo: str | None = None,
              fuentes: str = "documentos", fondo_id=None) -> dict:
    if fuentes == "documentos":
        return _con_documentos(db, usuario_id, mensajes, fondo_id)
    m = servicio_motor.motor_activo()
    if m is None:
        raise AsistenteNoDisponible("El asistente con IA necesita el motor de análisis, que no está configurado en este "
                                    "servidor. Mientras tanto, use la búsqueda y la guía de cada pantalla.")
    turnos = [x for x in mensajes if str(x.get("texto") or "").strip()][-MAX_TURNOS:]
    if not turnos or turnos[-1].get("rol") != "persona":
        raise ValueError("Falta la pregunta.")
    contenido = []
    contexto = _contexto(pantalla, fondo)
    for i, t in enumerate(turnos):
        texto = str(t["texto"]).strip()[:MAX_CARACTERES]
        if i == len(turnos) - 1 and contexto:
            texto = f"{contexto}\n\nPregunta: {texto}"
        contenido.append({"role": "user" if t.get("rol") == "persona" else "model", "parts": [{"text": texto}]})
    # Gemini consulta Google Search (respuestas al día y con fuentes); la pregunta va sin datos personales.
    from app.servicios.datos_personales import anonimizar_para_motor

    for turno in contenido:
        turno["parts"] = [{"text": anonimizar_para_motor(p["text"])[0]} for p in turno["parts"]]
    respuesta = m.conversar(INSTRUCCION, contenido, buscar=True)
    fuentes = (getattr(m, "ultima", None) or {}).get("fuentes") or []
    modelo = getattr(m, "respondio", None) or m.modelo
    # Se registra que se consultó y con qué modelo; el texto no se guarda (puede traer datos personales).
    registrar(db, modulo="sistema", accion="asistente_consultado", usuario_id=usuario_id, entidad_tipo="asistente",
              detalle="Consultó al Asistente RICORA", nuevo={"modelo": modelo, "turnos": len(turnos),
                                                           "fuentes_web": len(fuentes)})
    db.commit()
    return {"respuesta": respuesta.replace("**", "").strip(), "modelo": modelo, "fuentes": fuentes, "modo": "internet",
            "pasajes": []}


def _con_documentos(db: Session, usuario_id, mensajes: list[dict], fondo_id) -> dict:
    """RAG: recupera los pasajes de la biblioteca y del fondo, y el motor responde solo con ellos."""
    from app.servicios import rag
    from app.servicios.datos_personales import anonimizar_para_motor

    turnos = [x for x in mensajes if str(x.get("texto") or "").strip()][-MAX_TURNOS:]
    if not turnos or turnos[-1].get("rol") != "persona":
        raise ValueError("Falta la pregunta.")
    pregunta = str(turnos[-1]["texto"]).strip()[:MAX_CARACTERES]
    # Una pregunta de seguimiento («¿y el plazo?») se busca junto con la anterior.
    anteriores = [str(t["texto"]) for t in turnos[:-1] if t.get("rol") == "persona"][-1:]
    pasajes = rag.recuperar(db, " ".join([*anteriores, pregunta]), fondo_id)
    if not pasajes:
        registrar(db, modulo="sistema", accion="asistente_consultado", usuario_id=usuario_id, entidad_tipo="asistente",
                  detalle="Consultó al Asistente RICORA con los documentos de la entidad (sin pasajes)",
                  nuevo={"modo": "documentos", "pasajes": 0})
        db.commit()
        return {"respuesta": SIN_PASAJES, "modelo": None, "fuentes": [], "modo": "documentos", "pasajes": []}
    m = servicio_motor.motor_activo()
    if m is None:
        raise AsistenteNoDisponible("El asistente con IA necesita el motor de análisis, que no está configurado en este "
                                    "servidor. Los pasajes encontrados se muestran abajo.")
    contenido = []
    for t in turnos[:-1]:
        contenido.append({"role": "user" if t.get("rol") == "persona" else "model",
                          "parts": [{"text": anonimizar_para_motor(str(t["texto"]).strip()[:MAX_CARACTERES])[0]}]})
    contenido.append({"role": "user", "parts": [{"text": f"PASAJES:\n\n{rag.contexto(pasajes)}\n\nPregunta: "
                                                         f"{anonimizar_para_motor(pregunta)[0]}"}]})
    respuesta = m.conversar(INSTRUCCION_RAG, contenido, buscar=False)
    modelo = getattr(m, "respondio", None) or m.modelo
    citados = {int(n) for n in re.findall(r"\[(\d{1,2})\]", respuesta)}
    registrar(db, modulo="sistema", accion="asistente_consultado", usuario_id=usuario_id, entidad_tipo="asistente",
              detalle="Consultó al Asistente RICORA con los documentos de la entidad",
              nuevo={"modelo": modelo, "modo": "documentos", "pasajes": len(pasajes), "citados": len(citados)})
    db.commit()
    return {"respuesta": respuesta.replace("**", "").strip(), "modelo": modelo, "fuentes": [], "modo": "documentos",
            "pasajes": [p.out() | {"citado": p.numero in citados} for p in pasajes]}
