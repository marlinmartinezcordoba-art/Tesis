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
    criterios: list = field(default_factory=list)  # códigos de criterio


class ProveedorIA:
    nombre = "base"
    version = "0"

    def proponer(self, documento):
        raise NotImplementedError


class ProveedorReglas(ProveedorIA):
    """Extrae fechas del texto con expresiones regulares (demostración)."""

    nombre = "reglas-demo"
    version = "0.1"
    ANIO = re.compile(r"\b(1[5-9]\d{2}|20[0-2]\d)\b")

    def proponer(self, documento):
        anios = sorted({int(a) for a in self.ANIO.findall(documento.texto_extraido)})
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
            )
        ]


def generar_sugerencias(documento, proveedor):
    from lineamientos.models import Criterio

    creadas = []
    for p in proveedor.proponer(documento):
        s = SugerenciaIA.objects.create(
            documento=documento,
            proceso=p.proceso,
            campo=p.campo,
            valor_propuesto=p.valor,
            justificacion=p.justificacion,
            confianza=p.confianza,
            modelo=proveedor.nombre,
            version_modelo=proveedor.version,
        )
        if p.criterios:
            s.criterios.set(Criterio.objects.filter(codigo__in=p.criterios))
        registrar_evento(
            documento,
            EventoPreservacion.Tipo.SUGERENCIA_IA,
            agente=f"{proveedor.nombre} {proveedor.version}",
            detalle={"sugerencia": s.pk, "campo": p.campo, "confianza": p.confianza},
        )
        creadas.append(s)
    return creadas
