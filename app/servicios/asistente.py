"""
Asistente RICORA con IA: responde preguntas de archivística y de uso del sistema.

Usa el mismo motor de análisis que la descripción (Gemini). Reglas:

- Solo orienta: no lee documentos, no cambia nada y no ve datos del fondo
  distintos del nombre del fondo y de la pantalla en la que está la persona.
- Lo que la persona escribe sale hacia el servicio de IA. Por eso la pantalla
  advierte que no se escriban datos personales ni información con reserva legal,
  y la auditoría guarda que se consultó, pero no el texto de la pregunta.
- Sin motor configurado, el asistente queda en modo guiado (sin IA).
"""

from sqlalchemy.orm import Session

from app.servicios import motor as servicio_motor
from app.servicios.auditoria import registrar

MAX_TURNOS = 10
MAX_CARACTERES = 1500

AVISO = ("Lo que escriba se envía al servicio de IA del motor de análisis. No escriba datos personales ni información "
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
- Usuarios y permisos: usuarios, roles, puesta en marcha (solo administración)."""

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

{MAPA}"""


class AsistenteNoDisponible(Exception):
    pass


def estado() -> dict:
    m = servicio_motor.motor_activo()
    return {"disponible": m is not None, "modelo": getattr(m, "modelo", None) if m else None, "aviso": AVISO}


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


def preguntar(db: Session, usuario_id, mensajes: list[dict], pantalla: dict | None = None, fondo: str | None = None) -> dict:
    m = servicio_motor.motor_activo()
    if m is None:
        raise AsistenteNoDisponible("El asistente con IA necesita el motor de análisis configurado en el servidor "
                                    "(GEMINI_API_KEY). Mientras tanto, use la búsqueda y la guía de cada pantalla.")
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
    respuesta = m.conversar(INSTRUCCION, contenido)
    # Se registra que se consultó y con qué modelo; el texto no se guarda (puede traer datos personales).
    registrar(db, modulo="sistema", accion="asistente_consultado", usuario_id=usuario_id, entidad_tipo="asistente",
              detalle="Consultó al Asistente RICORA", nuevo={"modelo": m.modelo, "turnos": len(turnos)})
    db.commit()
    return {"respuesta": respuesta.replace("**", "").strip(), "modelo": m.modelo}
