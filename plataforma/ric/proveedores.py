"""Proveedores de IA intercambiables sobre el núcleo RiC (AIProvider del
Entregable 3): cada uno lee un Record y su texto, y devuelve candidatos de
relación. RICORA nunca confía en el proveedor a ciegas: `generar_propuestas`
verifica la evidencia contra el texto real y el dominio/rango contra
`ric.reglas` antes de guardar nada, y solo guarda — nunca escribe el grafo
directamente (eso solo lo hace `PropuestaRiC.validar()`).
"""

from dataclasses import dataclass, field

from . import reglas, tipos
from .evidencia import crear_evidencia
from .models import PropuestaRiC

# Criterios de calidad de la especificación funcional (sección 11) que se
# aplican a cada propuesta antes de guardarla. CC-01 y CC-06 la descartan
# (queda guardada como rechazada, con el motivo: CC-02 exige que nada
# desaparezca en silencio); CC-03 también, cuando la procedencia apunta a
# quien no produjo ni firmó; CC-04, CC-05 y CC-07 la marcan para la ficha.
CC_01 = "CC-01: la evidencia citada no aparece en el texto del documento."
CC_03 = "CC-03: una relación de procedencia solo puede apuntar a un agente productor o firmante."
CC_06 = "CC-06: un mandato o regla exige una cita textual explícita de la norma."
_TIPOS_MANDATO = {"E16", "E17"}
_ROLES_SIN_PROCEDENCIA = {"destinatario", "mencionado"}


class ErrorProveedorIA(Exception):
    """Error que se muestra a la persona archivista en lenguaje claro."""


@dataclass
class PropuestaCandidata:
    relacion_id: str  # ej. "R027"
    entidad_tipo: str  # ID RiC-CM del tipo de la entidad destino, ej. "E11"
    entidad_nombre: str
    evidencia: str
    confianza: float
    justificacion: str = ""
    vocabulario_id: int | None = None  # CC-05: entrada existente que el motor propone reutilizar
    datos_extra: dict = field(default_factory=dict)  # rol del agente, fecha normalizada, DANE...


class ProveedorIA:
    nombre = "base"
    version = "0"
    advertencias: list = []
    forma_documental: dict | None = None

    def texto_de(self, instanciacion):
        return instanciacion.texto_extraido

    def proponer(self, record, texto, instanciacion=None):
        raise NotImplementedError


def _conflicto_temporal(candidato, instanciacion):
    """CC-07 (coherencia temporal): la fecha normalizada debe ser
    interpretable y una fecha de creación no puede ser posterior a la
    ingesta. Devuelve el texto del conflicto, o None si es coherente."""
    import datetime

    normalizada = (candidato.datos_extra or {}).get("fecha_normalizada", "")
    if not normalizada:
        return None
    for formato in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            fecha = datetime.datetime.strptime(normalizada, formato).date()
            break
        except ValueError:
            continue
    else:
        return f"la fecha normalizada «{normalizada}» no es una fecha ISO 8601 interpretable."
    if candidato.datos_extra.get("tipo_fecha") == "creacion" and instanciacion is not None:
        ingesta = instanciacion.fecha_registro.date()
        if fecha > ingesta:
            return f"fecha de creación {normalizada} posterior a la ingesta ({ingesta.isoformat()})."
    return None


def _entidad_sugerida(modelo, candidato):
    """CC-05: la entrada del vocabulario que la ficha debe ofrecer para
    vincular — la que indicó el motor (vocabulario_id), o la más parecida
    por trigramas por encima del umbral configurado."""
    from . import desambiguacion
    from .models import ConfiguracionSistema

    if modelo is None:
        return None
    if candidato.vocabulario_id:
        existente = modelo.objects.filter(pk=candidato.vocabulario_id).first()
        if existente is not None:
            return existente
    exacta = modelo.objects.filter(nombre__iexact=candidato.entidad_nombre).first()
    if exacta is not None:
        return exacta
    umbral = ConfiguracionSistema.actual().umbral_similitud_vocabulario
    for similar in desambiguacion.candidatos_similares(modelo, candidato.entidad_nombre, limite=1):
        if similar.similitud >= umbral:
            return similar
    return None


def generar_propuestas(record, proveedor):
    """Genera PropuestaRiC pendientes para `record` usando `proveedor`.

    Antes de guardar cada una: verifica que la evidencia exista de verdad en
    el texto (y en qué página), y que la relación/tipo de entidad propuestos
    respeten el dominio/rango verificado de RiC-CM 1.0 — si no lo respetan,
    la propuesta se guarda igual (nunca se descarta en silencio) pero queda
    'rechazada' con el motivo, para que quede auditable.

    Si `record` tiene más de una Instantiation (carga masiva de F01, o un
    segmento de F04), se usa la que más texto extraído tiene — antes se
    tomaba "la primera" sin ningún orden definido, así que con varios
    archivos era arbitrario cuál se le pasaba a la IA.
    """
    instanciaciones = list(record.instanciaciones.all())
    if not instanciaciones:
        raise ErrorProveedorIA("El Record no tiene ninguna Instantiation con texto extraído.")
    instanciacion = max(instanciaciones, key=lambda i: len(i.texto_extraido))
    texto = proveedor.texto_de(instanciacion)
    if not texto.strip():
        raise ErrorProveedorIA("La instanciación no tiene texto. Extráigalo primero.")

    # RF-M3-03 / bucle de rechazo de M6: al volver a analizar un documento
    # no se repite una propuesta idéntica a una que ya existe (pendiente o
    # ya decidida) — así "pedir una nueva propuesta" solo agrega lo nuevo.
    from django.contrib.contenttypes.models import ContentType

    from .grafo import categoria_relacion as grafo_categoria

    ya_propuestas = set(
        PropuestaRiC.objects.filter(
            origen_content_type=ContentType.objects.get_for_model(record), origen_object_id=record.pk,
        ).values_list("relacion_id", "entidad_tipo", "entidad_nombre")
    )

    from .models import EventoRiC, registrar_evento

    creadas = []
    candidatos = proveedor.proponer(record, texto, instanciacion=instanciacion)
    advertencias = list(getattr(proveedor, "advertencias", None) or [])
    forma_documental = getattr(proveedor, "forma_documental", None)
    if advertencias or forma_documental:
        registrar_evento(
            instanciacion, EventoRiC.Tipo.PROPUESTA_IA, agente=f"{proveedor.nombre} {proveedor.version}",
            detalle={"resumen_analisis": True, "advertencias": advertencias, "forma_documental": forma_documental},
        )

    for cand in candidatos:
        clave = (cand.relacion_id, cand.entidad_tipo, cand.entidad_nombre)
        if clave in ya_propuestas:
            continue
        ya_propuestas.add(clave)
        motivo_rechazo = ""
        try:
            modelos_dominio, modelos_rango = reglas.entidades_para(cand.relacion_id)
        except reglas.RelacionInvalida as e:
            motivo_rechazo = str(e)
            modelos_dominio = modelos_rango = None

        modelo_destino = tipos.ric_id_a_modelo(cand.entidad_tipo)
        inversa = False
        if not motivo_rechazo and modelo_destino is None:
            motivo_rechazo = f"Tipo de entidad desconocido: {cand.entidad_tipo!r}."
        if not motivo_rechazo:
            directa_ok = (
                (modelos_dominio is None or isinstance(record, modelos_dominio))
                and (modelos_rango is None or issubclass(modelo_destino, modelos_rango))
            )
            # Sentido inverso (p. ej. R080 "is creation date of": Date -> Record
            # Resource): la entidad propuesta es el dominio y el documento el rango.
            inversa_ok = (
                not directa_ok and modelos_dominio is not None
                and issubclass(modelo_destino, modelos_dominio)
                and (modelos_rango is None or isinstance(record, modelos_rango))
            )
            if inversa_ok:
                inversa = True
            elif not directa_ok:
                if modelos_dominio is not None and not isinstance(record, modelos_dominio):
                    permitidos = ", ".join(m.__name__ for m in modelos_dominio)
                    motivo_rechazo = f"'{cand.relacion_id}' exige un origen {permitidos}, no {type(record).__name__}."
                else:
                    permitidos = ", ".join(m.__name__ for m in modelos_rango)
                    motivo_rechazo = f"'{cand.relacion_id}' exige un destino {permitidos}, no {modelo_destino.__name__}."

        evidencia = crear_evidencia(instanciacion, cand.evidencia)
        justificacion = cand.justificacion
        if not motivo_rechazo and not evidencia.verificada:
            motivo_rechazo = CC_06 if cand.entidad_tipo in _TIPOS_MANDATO else CC_01
        rol = cand.datos_extra.get("rol_en_el_documento")
        if (
            not motivo_rechazo and rol in _ROLES_SIN_PROCEDENCIA
            and grafo_categoria(cand.relacion_id) == "procedencia"
        ):
            motivo_rechazo = f"{CC_03} (rol indicado: {rol})"

        # RF-M3-03 / CC-05: consultar primero los vocabularios ya existentes
        # — la ficha ofrecerá vincular la entrada sugerida en vez de crearla.
        datos_extra = dict(cand.datos_extra)
        if inversa:
            datos_extra["inversa"] = True
        conflicto = _conflicto_temporal(cand, instanciacion) if cand.entidad_tipo == "E18" else None
        if conflicto:
            datos_extra["conflicto_temporal"] = conflicto
            justificacion = f"⚠ CC-07: {conflicto} {justificacion}".strip()
        sugerida = _entidad_sugerida(modelo_destino, cand) if not motivo_rechazo else None
        if sugerida is not None:
            datos_extra["entidad_sugerida_id"] = sugerida.pk
            datos_extra["entidad_sugerida_nombre"] = sugerida.nombre
            justificacion = f"Ya existe en vocabularios y autoridades («{sugerida.nombre}»): se propone reutilizar la entrada. {justificacion}".strip()

        propuesta = PropuestaRiC.objects.create(
            origen_content_type=ContentType.objects.get_for_model(record),
            origen_object_id=record.pk,
            relacion_id=cand.relacion_id,
            entidad_tipo=cand.entidad_tipo,
            entidad_nombre=cand.entidad_nombre,
            proveedor=proveedor.nombre,
            version_modelo=proveedor.version,
            confianza=cand.confianza,
            justificacion=justificacion,
            evidencia=evidencia,
            datos_extra=datos_extra,
            estado=PropuestaRiC.Estado.RECHAZADA if motivo_rechazo else PropuestaRiC.Estado.PENDIENTE,
            motivo_decision=motivo_rechazo,
        )
        registrar_evento(
            instanciacion, EventoRiC.Tipo.PROPUESTA_IA,
            agente=f"{proveedor.nombre} {proveedor.version}",
            detalle={
                "propuesta": propuesta.pk, "relacion_id": cand.relacion_id,
                "confianza": cand.confianza, "evidencia_verificada": evidencia.verificada,
                "rechazada_automaticamente": bool(motivo_rechazo),
            },
        )
        creadas.append(propuesta)
    return creadas


# ---------------------------------------------------------------------------
# M11 (RF-M11-02): proveedores configurados desde la aplicación
# ---------------------------------------------------------------------------

def instanciar(config):
    """El ProveedorIA real que corresponde a una fila de ProveedorIAConfig,
    con su clave (si se guardó una) y su modelo (si se eligió uno)."""
    from .models import ProveedorIAConfig

    modelo = config.modelo or None
    if config.proveedor == ProveedorIAConfig.Proveedor.GEMINI:
        from google import genai

        from .proveedor_gemini import ProveedorGemini

        cliente = genai.Client(api_key=config.clave_api) if config.clave_api else None
        return ProveedorGemini(cliente=cliente, modelo=modelo)
    if config.proveedor == ProveedorIAConfig.Proveedor.CLAUDE:
        import anthropic

        from .proveedor_claude import ProveedorClaude

        cliente = anthropic.Anthropic(api_key=config.clave_api) if config.clave_api else None
        return ProveedorClaude(cliente=cliente, modelo=modelo)
    from .proveedor_local import ProveedorLocal

    return ProveedorLocal()


def proveedor_activo():
    """El proveedor marcado como fuente del motor de análisis, o None si
    todavía no se activó ninguno en Administración → Proveedores de IA."""
    from .models import ProveedorIAConfig

    config = ProveedorIAConfig.objects.filter(activo=True).first()
    return instanciar(config) if config else None


def probar_conexion(config):
    """Prueba mínima real contra el servicio (o carga del modelo local).
    Devuelve (True, mensaje) o (False, mensaje en lenguaje claro)."""
    from .models import ProveedorIAConfig

    try:
        proveedor = instanciar(config)
        if config.proveedor == ProveedorIAConfig.Proveedor.GEMINI:
            from google.genai import errors as genai_errors
            from google.genai import types as genai_types

            # Una generación mínima real: consultar el modelo (models.get) puede
            # responder bien aunque la clave no pueda generar con él (pasó con
            # gemini-2.5-pro, retirado para claves nuevas).
            try:
                respuesta = proveedor.cliente.models.generate_content(
                    model=proveedor.modelo, contents="Responde únicamente: OK",
                    config=genai_types.GenerateContentConfig(max_output_tokens=5),
                )
            except genai_errors.ClientError as e:
                if e.code in (401, 403):
                    return False, "La clave de API de Gemini no es válida."
                if e.code == 404:
                    return False, f"El modelo «{proveedor.modelo}» no está disponible para esta clave: {e.message}"
                if e.code == 429:
                    return False, "La clave es válida pero se superó el límite de uso; intente en unos minutos."
                return False, f"Gemini respondió con un error ({e.code})."
            except genai_errors.ServerError as e:
                return False, f"Gemini respondió con un error del servidor ({e.code})."
            return True, f"Conexión correcta con Gemini · modelo {respuesta.model_version or proveedor.modelo}."
        if config.proveedor == ProveedorIAConfig.Proveedor.CLAUDE:
            import anthropic

            try:
                proveedor.cliente.models.retrieve(proveedor.modelo)
            except anthropic.AuthenticationError:
                return False, "La clave de API de Anthropic no es válida."
            except anthropic.NotFoundError:
                return False, f"El modelo «{proveedor.modelo}» no existe para esta clave."
            except anthropic.APIStatusError as e:
                return False, f"Claude respondió con un error ({e.status_code})."
            return True, f"Conexión correcta con Claude · modelo {proveedor.modelo}."
        from .proveedor_local import _cargar_modelo

        nlp = _cargar_modelo()
        return True, f"Modelo local cargado: {nlp.meta.get('lang', '')} {nlp.meta.get('name', '')} {nlp.meta.get('version', '')}".strip()
    except ErrorProveedorIA as e:
        return False, str(e)
    except Exception as e:  # red caída, DNS, SDK: se muestra tal cual, nunca se oculta
        return False, f"No fue posible conectar: {e.__class__.__name__}: {e}"
