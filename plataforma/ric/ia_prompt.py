"""Lo que cualquier proveedor de IA en la nube necesita para proponer
entidades y relaciones RiC — instrucciones, esquema de salida estructurada
y el filtro de qué relaciones/tipos son válidos para un Record dado —
independiente de si quien responde es Claude, Gemini o cualquier otro.

Las instrucciones siguen los siete prompts de la sección 12 de la
especificación funcional (rol del motor, siete reglas sin excepción y las
indicaciones por clase: forma documental, agente, actividad/función,
mandato/regla, fecha, lugar y relaciones), unificados en una sola llamada
con salida estructurada. La diferencia con la especificación es
deliberada y a favor de RiC: en vez de cinco categorías genéricas de
relación, el motor debe elegir el identificador exacto de RiC-CM 1.0
(R001-R086) y el tipo de entidad (E08-E22) verificados en
ric/fixtures/ric_matrix.json; la categoría (procedencia, asociación,
temporal, inclusión) se deriva después, en ric.grafo.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from . import reglas, tipos

CONFIANZA = {"alta": 0.9, "media": 0.7, "baja": 0.4}

# Cuántas entradas del vocabulario se le muestran al motor (CC-05 / regla 3
# del prompt de sistema): las más recientes de cada tipo.
_VOCABULARIO_POR_TIPO = 40


class RelacionPropuestaRiC(BaseModel):
    relacion_id: str = Field(description="Un ID de relación de la lista de relaciones permitidas.")
    entidad_tipo: str = Field(description="Un ID de tipo de entidad de la lista de tipos permitidos para esa relación.")
    entidad_nombre: str = Field(description="Forma normalizada del nombre de la entidad.")
    evidencia: str = Field(description="Fragmento copiado literalmente del documento que respalda la propuesta.")
    confianza: Literal["alta", "media", "baja"]
    justificacion: str = Field(description="Una frase que explica el razonamiento.")
    vocabulario_id: Optional[int] = Field(
        default=None,
        description="Si la entidad ya existe en el vocabulario recibido (similitud de al menos 80 %), su id; si no, null.",
    )
    rol_en_el_documento: Optional[Literal["productor", "firmante", "destinatario", "mencionado"]] = Field(
        default=None, description="Solo para agentes: qué papel cumple en el documento.",
    )
    fecha_texto_original: Optional[str] = Field(default=None, description="Solo para fechas: tal como aparece escrita.")
    fecha_normalizada: Optional[str] = Field(default=None, description="Solo para fechas: ISO 8601 (AAAA-MM-DD, o AAAA-MM, o AAAA).")
    precision_fecha: Optional[Literal["exacta", "aproximada", "rango"]] = None
    tipo_fecha: Optional[Literal["creacion", "tramite", "vigencia", "plazo"]] = None
    tipo_norma: Optional[Literal["externa", "interna"]] = Field(default=None, description="Solo para mandatos o reglas.")
    tipo_funcion: Optional[Literal["sustantiva", "de_apoyo"]] = Field(default=None, description="Solo para actividades.")
    tipo_lugar: Optional[Literal["pais", "departamento", "municipio", "direccion"]] = None
    codigo_dane: Optional[str] = Field(default=None, description="Solo para lugares colombianos identificables; null si no está seguro.")


class FormaDocumentalPropuesta(BaseModel):
    nombre_tipo: str = Field(description="Oficio, resolución, acta, contrato, memorando, circular... o 'tipo no identificado'.")
    definicion: str = ""
    fragmento_fuente: str = ""
    confianza: Literal["alta", "media", "baja"]
    vocabulario_id: Optional[int] = None


class PropuestasRecordRiC(BaseModel):
    relaciones: list[RelacionPropuestaRiC]
    forma_documental: Optional[FormaDocumentalPropuesta] = None
    advertencias: list[str] = Field(default_factory=list, description="Clases sin evidencia suficiente y por qué; ambigüedades.")


def relaciones_aplicables(modelo_origen):
    """{relacion_id: {"nombre":..., "tipos_destino": [ric_id, ...]}} para las
    relaciones cuyo dominio (verificado) acepta `modelo_origen`, restringidas
    a tipos de entidad "hoja" (nunca la categoría abstracta Agent/Event/Rule)."""
    matriz = reglas.cargar_matriz()
    aplicables = {}
    for rid, datos in matriz["relaciones"].items():
        try:
            modelos_dominio, modelos_rango = reglas.entidades_para(rid)
        except reglas.RelacionInvalida:
            continue
        if modelos_dominio is None or issubclass(modelo_origen, modelos_dominio):
            tipos_destino = [
                ric_id for ric_id in tipos.LEAF_TIPOS
                if modelos_rango is None or issubclass(tipos.ric_id_a_modelo(ric_id), modelos_rango)
            ]
            if tipos_destino:
                aplicables[rid] = {"nombre": datos["nombre"], "tipos_destino": tipos_destino, "inversa": False}
            continue
        # Relaciones que RiC-CM define desde la entidad hacia el documento
        # (todas las de fecha: "R080 is creation date of", Date -> Record
        # Resource). El motor las propone igual; al aceptarlas la relación se
        # guarda con la entidad como origen y el documento como destino.
        if modelos_dominio is not None and (modelos_rango is None or issubclass(modelo_origen, modelos_rango)):
            tipos_destino = [
                ric_id for ric_id in tipos.LEAF_TIPOS if issubclass(tipos.ric_id_a_modelo(ric_id), modelos_dominio)
            ]
            if tipos_destino:
                aplicables[rid] = {"nombre": datos["nombre"], "tipos_destino": tipos_destino, "inversa": True}
    return aplicables


def es_inversa(relacion_id, modelo_origen):
    """True si `relacion_id` se aplica a `modelo_origen` solo en sentido
    inverso (la entidad propuesta es el dominio y el documento el rango)."""
    return relaciones_aplicables(modelo_origen).get(relacion_id, {}).get("inversa", False)


def tabla_relaciones(aplicables):
    matriz = reglas.cargar_matriz()
    nombres_tipo = {eid: d["nombre"] for eid, d in matriz["entidades"].items()}
    lineas = []
    for rid, info in sorted(aplicables.items(), key=lambda kv: int(kv[0][1:])):
        tipos_legibles = ", ".join(f"{t} ({nombres_tipo.get(t, t)})" for t in info["tipos_destino"])
        nota = " — la entidad es el sujeto de la relación y el documento su objeto" if info.get("inversa") else ""
        lineas.append(f"- {rid} \"{info['nombre']}\": entidad_tipo debe ser uno de [{tipos_legibles}]{nota}")
    return "\n".join(lineas)


def vocabulario_existente():
    """CC-05 / RF-M3-03: las entradas de autoridad ya validadas que el motor
    debe consultar antes de proponer una entidad nueva — id, tipo y nombre,
    para que pueda devolver `vocabulario_id` en vez de duplicar."""
    from .models import FormaDocumental

    lineas = []
    for ric_id in tipos.LEAF_TIPOS:
        if ric_id == "E18":  # las fechas no son entradas de autoridad
            continue
        modelo = tipos.ric_id_a_modelo(ric_id)
        for pk, nombre in modelo.objects.order_by("-fecha_registro").values_list("pk", "nombre")[:_VOCABULARIO_POR_TIPO]:
            lineas.append(f"- id {pk} · {ric_id} · {nombre}")
    for pk, nombre in FormaDocumental.objects.values_list("pk", "nombre")[:_VOCABULARIO_POR_TIPO]:
        lineas.append(f"- id {pk} · forma documental · {nombre}")
    return "\n".join(lineas) if lineas else "(el vocabulario todavía está vacío)"


INSTRUCCIONES = """Rol
Eres el motor de análisis del sistema de descripción documental basado en el estándar \
Records in Contexts (RiC-CM 1.0 y RiC-O 1.1) del Consejo Internacional de Archivos. Lees el \
texto de un documento de archivo colombiano, ya extraído por OCR o de forma nativa, y propones \
las entidades y relaciones que permiten describirlo según el modelo conceptual. No tomas \
ninguna decisión final: todo lo que propongas será revisado y confirmado o corregido por una \
persona archivista antes de publicarse.

Relaciones permitidas para este documento (usa solo estos IDs de RiC-CM, con el entidad_tipo \
indicado para cada una):
{tabla_relaciones}

Vocabulario y autoridades ya existentes (consúltalo antes de proponer una entidad nueva):
{vocabulario}

Reglas, sin excepción
1. No inventes ningún dato que no esté respaldado por un fragmento textual del documento. Si \
no encuentras evidencia suficiente para una clase de entidad (agente, actividad, fecha, lugar, \
mandato, forma documental), decláralo en "advertencias" en lugar de completar con una suposición.
2. Toda entidad que propongas debe incluir en "evidencia" el fragmento exacto del que la \
derivaste, copiado literalmente, sin corregir ortografía ni parafrasear.
3. Antes de proponer una entidad nueva de agente, lugar, actividad o forma documental, revisa \
el vocabulario recibido: si alguna entrada coincide en al menos un ochenta por ciento, devuelve \
su id en "vocabulario_id" en vez de proponer una entidad nueva.
4. Asigna a cada propuesta una confianza (alta, media, baja) según qué tan explícita es la \
evidencia textual, nunca según qué tan típica te parezca la entidad.
5. Un mandato o una regla (E16, E17) solo se propone si el texto contiene una mención explícita \
a una norma, ley, decreto, resolución, acuerdo, artículo o procedimiento; nunca por inferencia \
del contexto institucional, aunque conozcas el marco normativo. Indica tipo_norma: externa \
(ley, decreto) o interna (procedimiento, manual).
6. Para las fechas (E18) devuelve las dos formas: fecha_texto_original tal como aparece y \
fecha_normalizada en ISO 8601; si la fecha es incompleta o ambigua, indica precision_fecha \
"aproximada" o "rango" en vez de forzar una fecha exacta, y di el criterio en "advertencias". \
Indica tipo_fecha: creacion, tramite, vigencia o plazo.
7. Responde únicamente en el formato JSON especificado, sin texto adicional.

Indicaciones por clase
- Agentes (E08 persona, E11 entidad corporativa, E10 familia, E09 grupo, E12 cargo): solo \
quienes cumplen un papel real en la producción, el trámite o el destino del documento, no un \
nombre mencionado de paso. Indica rol_en_el_documento: productor, firmante, destinatario o \
mencionado. Solo un agente productor o firmante puede sustentar una relación de procedencia \
(por ejemplo R027 "has creator", R026 "has or had provenance"); quien es únicamente el tema o \
asunto del documento nunca es productor — úsalo con R019 "has or had subject".
- Actividad o función (E15): el trámite, proceso o función que dio origen al documento \
(contratación, personal, solicitud ciudadana...), con tipo_funcion sustantiva o de_apoyo. No \
inventes una función genérica de la entidad si el texto no permite identificar el trámite.
- Lugares (E22): lugar de expedición, de los hechos o jurisdicción competente, con tipo_lugar \
(pais, departamento, municipio, direccion) y codigo_dane solo cuando puedas determinarlo con \
certeza; si no, null.
- Forma documental: el tipo documental del documento (oficio, resolución, acta, contrato, \
memorando, circular u otro de la gestión documental colombiana), según su estructura formal y \
no solo su tema; si no encaja claramente, "tipo no identificado" y explica en advertencias.
- No inventes una entidad de tipo "tema" o "concepto": RiC-CM no lo tiene.
- El texto puede tener errores de OCR y la marca [DATO RESERVADO]; no intentes reconstruir \
los datos reservados."""

INSTRUCCIONES_VISUAL = """

También puedes ver la imagen o el PDF original del documento, no solo su texto \
extraído por OCR. Úsalo para notar lo que el OCR suele perderse: firmas, sellos, \
membretes, tablas o zonas mal escaneadas. Si la evidencia de una propuesta viene de \
algo que solo se ve en la imagen (una firma, por ejemplo) y no aparece igual en el \
texto, dilo en la justificación — el archivista puede necesitar verificarlo a mano."""

EJEMPLOS = """

Ejemplos de decisiones ya validadas por la persona archivista en documentos parecidos \
(úsalos para aprender el patrón, pero cada propuesta debe seguir basándose en evidencia \
real de ESTE documento, no de los ejemplos):
{lista}"""


def contexto_archivistico(record):
    """Lo que ya se sabe del documento por su clasificación (expediente,
    serie de la TRD, oficina productora): se le informa al motor para que
    reutilice esas entidades (CC-05) y para la relación de inclusión, sin
    que tenga que adivinarlas del texto."""
    from .clasificacion import expediente_de, oficina_de

    if not hasattr(record, "record_set_id"):
        return ""
    conjunto = expediente_de(record)
    if conjunto is None:
        return ""
    serie = conjunto.serie()
    lineas = [f"- expediente: {conjunto.nombre}"]
    if serie is not None and serie.actividad_id:
        lineas.append(f"- serie de la TRD: {serie.nombre} ({serie.identificador}) · actividad id {serie.actividad_id} · {serie.actividad.nombre}")
        oficina = oficina_de(serie.actividad)
        if oficina is not None:
            lineas.append(f"- oficina productora: {oficina.nombre} (agente id {oficina.pk}, E11)")
    return (
        "\n\nContexto archivístico ya validado por la persona archivista (no lo propongas de nuevo; "
        "reutiliza estos identificadores en vocabulario_id cuando el texto los mencione):\n" + "\n".join(lineas) + "\n"
    )


def construir_instrucciones(record, texto, con_visual=False):
    """El mensaje de sistema completo para `record`, o None si RiC-CM no
    admite ninguna relación desde ese tipo de origen."""
    from . import aprendizaje

    aplicables = relaciones_aplicables(type(record))
    if not aplicables:
        return None
    instrucciones = INSTRUCCIONES.format(
        tabla_relaciones=tabla_relaciones(aplicables), vocabulario=vocabulario_existente(),
    )
    if con_visual:
        instrucciones += INSTRUCCIONES_VISUAL
    contexto = contexto_archivistico(record)
    if contexto:
        instrucciones += contexto
    ejemplos = aprendizaje.ejemplos_similares(texto, origen_modelo=type(record))
    if ejemplos:
        instrucciones += EJEMPLOS.format(lista=aprendizaje.formatear_ejemplos(ejemplos))
    return instrucciones


def _limpio(valor):
    return None if valor is None or isinstance(valor, type(Ellipsis)) else valor


def candidatos_desde_respuesta(parsed):
    """Convierte la salida estructurada en PropuestaCandidata (con los
    datos extra por clase) y devuelve (candidatos, forma_documental,
    advertencias)."""
    from .proveedores import PropuestaCandidata

    candidatos = []
    for r in parsed.relaciones:
        extra = {
            k: v for k, v in {
                "rol_en_el_documento": r.rol_en_el_documento,
                "fecha_texto_original": r.fecha_texto_original,
                "fecha_normalizada": r.fecha_normalizada,
                "precision_fecha": r.precision_fecha,
                "tipo_fecha": r.tipo_fecha,
                "tipo_norma": r.tipo_norma,
                "tipo_funcion": r.tipo_funcion,
                "tipo_lugar": r.tipo_lugar,
                "codigo_dane": r.codigo_dane,
            }.items() if v not in (None, "")
        }
        candidatos.append(PropuestaCandidata(
            relacion_id=r.relacion_id, entidad_tipo=r.entidad_tipo, entidad_nombre=r.entidad_nombre,
            evidencia=r.evidencia, confianza=CONFIANZA[r.confianza], justificacion=r.justificacion,
            vocabulario_id=r.vocabulario_id, datos_extra=extra,
        ))
    forma = None
    if parsed.forma_documental is not None and isinstance(parsed.forma_documental, FormaDocumentalPropuesta):
        f = parsed.forma_documental
        forma = {
            "nombre_tipo": f.nombre_tipo, "definicion": f.definicion, "fragmento_fuente": f.fragmento_fuente,
            "confianza": CONFIANZA[f.confianza], "vocabulario_id": f.vocabulario_id,
        }
    advertencias = [a for a in (parsed.advertencias or []) if isinstance(a, str)]
    return candidatos, forma, advertencias
