"""Proveedores de IA intercambiables sobre el núcleo RiC (AIProvider del
Entregable 3): cada uno lee un Record y su texto, y devuelve candidatos de
relación. MAZUCA nunca confía en el proveedor a ciegas: `generar_propuestas`
verifica la evidencia contra el texto real y el dominio/rango contra
`ric.reglas` antes de guardar nada, y solo guarda — nunca escribe el grafo
directamente (eso solo lo hace `PropuestaRiC.validar()`).
"""

from dataclasses import dataclass

from . import reglas, tipos
from .evidencia import crear_evidencia
from .models import PropuestaRiC

# Confianza máxima de una propuesta cuya evidencia no aparece en el texto.
CONFIANZA_SIN_EVIDENCIA = 0.3


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


class ProveedorIA:
    nombre = "base"
    version = "0"

    def texto_de(self, instanciacion):
        return instanciacion.texto_extraido

    def proponer(self, record, texto):
        raise NotImplementedError


def generar_propuestas(record, proveedor):
    """Genera PropuestaRiC pendientes para `record` usando `proveedor`.

    Antes de guardar cada una: verifica que la evidencia exista de verdad en
    el texto (y en qué página), y que la relación/tipo de entidad propuestos
    respeten el dominio/rango verificado de RiC-CM 1.0 — si no lo respetan,
    la propuesta se guarda igual (nunca se descarta en silencio) pero queda
    'rechazada' con el motivo, para que quede auditable.
    """
    instanciacion = record.instanciaciones.first()
    if instanciacion is None:
        raise ErrorProveedorIA("El Record no tiene ninguna Instantiation con texto extraído.")
    texto = proveedor.texto_de(instanciacion)
    if not texto.strip():
        raise ErrorProveedorIA("La instanciación no tiene texto. Extráigalo primero.")

    creadas = []
    for cand in proveedor.proponer(record, texto):
        motivo_rechazo = ""
        try:
            modelos_dominio, modelos_rango = reglas.entidades_para(cand.relacion_id)
        except reglas.RelacionInvalida as e:
            motivo_rechazo = str(e)
            modelos_dominio = modelos_rango = None

        if not motivo_rechazo and modelos_dominio is not None and not isinstance(record, modelos_dominio):
            permitidos = ", ".join(m.__name__ for m in modelos_dominio)
            motivo_rechazo = f"'{cand.relacion_id}' exige un origen {permitidos}, no {type(record).__name__}."

        modelo_destino = tipos.ric_id_a_modelo(cand.entidad_tipo)
        if not motivo_rechazo and modelo_destino is None:
            motivo_rechazo = f"Tipo de entidad desconocido: {cand.entidad_tipo!r}."
        elif not motivo_rechazo and modelos_rango is not None and not issubclass(modelo_destino, modelos_rango):
            permitidos = ", ".join(m.__name__ for m in modelos_rango)
            motivo_rechazo = f"'{cand.relacion_id}' exige un destino {permitidos}, no {modelo_destino.__name__}."

        evidencia = crear_evidencia(instanciacion, cand.evidencia)
        confianza = cand.confianza
        if not evidencia.verificada:
            confianza = min(confianza, CONFIANZA_SIN_EVIDENCIA)
            justificacion = f"⚠ Evidencia no encontrada en el texto. {cand.justificacion}"
        else:
            justificacion = cand.justificacion

        from django.contrib.contenttypes.models import ContentType

        propuesta = PropuestaRiC.objects.create(
            origen_content_type=ContentType.objects.get_for_model(record),
            origen_object_id=record.pk,
            relacion_id=cand.relacion_id,
            entidad_tipo=cand.entidad_tipo,
            entidad_nombre=cand.entidad_nombre,
            proveedor=proveedor.nombre,
            version_modelo=proveedor.version,
            confianza=confianza,
            justificacion=justificacion,
            evidencia=evidencia,
            estado=PropuestaRiC.Estado.RECHAZADA if motivo_rechazo else PropuestaRiC.Estado.PENDIENTE,
            motivo_decision=motivo_rechazo,
        )
        creadas.append(propuesta)
    return creadas
