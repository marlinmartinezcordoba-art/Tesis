"""Proveedores de IA intercambiables.

Cada proveedor recibe un documento y devuelve propuestas. La plataforma no
depende de un modelo concreto: la entidad puede usar un modelo local o uno
en la nube según su política de datos. `ProveedorReglas` es un proveedor
de demostración sin IA generativa que sirve para probar el flujo completo.
"""

import re
from dataclasses import dataclass, field

from acervo.models import EventoPreservacion, registrar_evento

from .models import SugerenciaIA


@dataclass
class Propuesta:
    proceso: str
    campo: str
    valor: str
    confianza: float
    justificacion: str
    evidencia: str = ""  # fragmento literal del documento
    criterios: list = field(default_factory=list)  # códigos de criterio
    relacion: str = ""  # solo para entidades (DES-04): productor/mencionado/destinatario
    # Solo para valoración: la entidad del grafo RiC que justifica el
    # indicio (relación trata_sobre), si el proveedor pudo identificarla.
    entidad_tipo: str = ""
    entidad_nombre: str = ""


# Confianza máxima de una propuesta cuya evidencia no aparece en el texto.
CONFIANZA_SIN_EVIDENCIA = 0.3


def _normalizar(texto):
    return " ".join(texto.lower().split())


def evidencia_en_texto(evidencia, texto):
    """Comprueba que la cita exista en el texto (sin importar espacios ni mayúsculas)."""
    return bool(evidencia.strip()) and _normalizar(evidencia) in _normalizar(texto)


class ProveedorIA:
    nombre = "base"
    version = "0"

    def texto_de(self, documento):
        """Texto que el proveedor puede leer; un proveedor en la nube lo restringe."""
        return documento.texto_extraido

    def proponer(self, documento, texto):
        raise NotImplementedError


class ProveedorReglas(ProveedorIA):
    """Extrae fechas del texto con expresiones regulares (demostración)."""

    nombre = "reglas-demo"
    version = "0.1"
    ANIO = re.compile(r"\b(1[5-9]\d{2}|20[0-2]\d)\b")

    def proponer(self, documento, texto):
        anios = sorted({int(a) for a in self.ANIO.findall(texto)})
        if not anios:
            return []
        valor = str(anios[0]) if len(anios) == 1 else f"{anios[0]}-{anios[-1]}"
        return [
            Propuesta(
                proceso="descripcion",
                campo="fechas",
                valor=valor,
                confianza=0.6,
                justificacion=f"Años encontrados en el texto: {anios}",
                evidencia=str(anios[0]),
            )
        ]


def generar_sugerencias(documento, proveedor):
    """Crea sugerencias pendientes y verifica la evidencia de cada una.

    La verificación la hace MAZUCA, no el proveedor: así el control contra
    datos inventados es el mismo para cualquier modelo de IA.
    """
    from lineamientos.models import Criterio

    texto = proveedor.texto_de(documento)
    creadas = []
    for p in proveedor.proponer(documento, texto):
        verificada = evidencia_en_texto(p.evidencia, texto)
        confianza, justificacion = p.confianza, p.justificacion
        if not verificada:
            confianza = min(confianza, CONFIANZA_SIN_EVIDENCIA)
            justificacion = f"⚠ Evidencia no encontrada en el texto. {justificacion}"
        s = SugerenciaIA.objects.create(
            documento=documento,
            proceso=p.proceso,
            campo=p.campo,
            valor_propuesto=p.valor,
            justificacion=justificacion,
            evidencia=p.evidencia,
            evidencia_verificada=verificada,
            relacion=p.relacion,
            entidad_tipo=p.entidad_tipo,
            entidad_nombre=p.entidad_nombre,
            confianza=confianza,
            modelo=proveedor.nombre,
            version_modelo=proveedor.version,
        )
        if p.criterios:
            s.criterios.set(Criterio.objects.filter(codigo__in=p.criterios))
        registrar_evento(
            documento,
            EventoPreservacion.Tipo.SUGERENCIA_IA,
            agente=f"{proveedor.nombre} {proveedor.version}",
            detalle={
                "sugerencia": s.pk,
                "campo": p.campo,
                "confianza": confianza,
                "evidencia_verificada": verificada,
            },
        )
        creadas.append(s)
    return creadas
