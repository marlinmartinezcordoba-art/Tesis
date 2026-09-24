"""Detección de datos personales en el texto de los documentos.

Base normativa: Ley 1581 de 2012 (protección de datos personales), en
especial el artículo 5 sobre datos sensibles, y Ley 1712 de 2014
(transparencia y acceso a la información pública).

El detector solo SEÑALA posibles datos personales; no restringe ni publica
nada por sí mismo. La decisión es siempre de la persona archivista, que
además debe considerar el contexto histórico (por ejemplo, si las personas
mencionadas viven o si la información ya es de dominio público).
"""

import re
from dataclasses import asdict, dataclass

VERSION = "0.1"


@dataclass
class Hallazgo:
    categoria: str
    tipo: str
    texto: str
    inicio: int
    fin: int
    sensible: bool

    def como_dict(self):
        return asdict(self)


# Datos de identificación y contacto (Ley 1581 de 2012, art. 3)
PATRONES = [
    ("identificacion", "Cédula o documento de identidad",
     r"\b(?:C\.?\s?C\.?|c[ée]dula(?:\s+de\s+ciudadan[íi]a)?|T\.?\s?I\.?)\s*(?:No\.?|N[°º]|n[úu]mero)?\s*[:.]?\s*\d{1,3}(?:[.\s]?\d{3}){1,3}\b"),
    ("identificacion", "NIT", r"\bNIT\.?\s*[:.]?\s*\d{3}[.\s]?\d{3}[.\s]?\d{3}(?:-\d)?\b"),
    ("contacto", "Correo electrónico", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    ("contacto", "Teléfono celular", r"(?<!\d)(?:\+?57\s?)?3\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)"),
    ("contacto", "Teléfono fijo", r"(?<!\d)(?:\+?57\s?)?60\d[\s-]?\d{3}[\s-]?\d{4}(?!\d)"),
    ("contacto", "Dirección",
     r"\b(?:Calle|Cl\.|Carrera|Cra\.?|Kr\.?|Avenida|Av\.|Transversal|Tv\.|Diagonal|Dg\.)\s*\d+[A-Za-z]?\s*(?:#|No\.?|N[°º])\s*\d+[A-Za-z]?\s*-\s*\d+\b"),
]

# Datos sensibles (Ley 1581 de 2012, art. 5): se detectan por vocabulario.
SENSIBLES = {
    "Salud": ["historia clínica", "diagnóstico", "enfermedad", "VIH", "sida",
              "discapacidad", "tratamiento médico", "incapacidad médica"],
    "Vida sexual u orientación sexual": ["orientación sexual", "homosexual", "vida sexual"],
    "Convicciones religiosas o filosóficas": ["religión", "creencia religiosa", "convicciones religiosas"],
    "Orientación política": ["militante", "afiliación política", "partido político"],
    "Pertenencia a sindicatos u organizaciones sociales": ["sindicato", "sindicalista"],
    "Origen racial o étnico": ["origen étnico", "origen racial"],
    "Datos biométricos": ["huella dactilar", "datos biométricos"],
}


def detectar(texto):
    hallazgos = []
    for categoria, tipo, patron in PATRONES:
        for m in re.finditer(patron, texto, flags=re.IGNORECASE):
            hallazgos.append(Hallazgo(categoria, tipo, m.group(), m.start(), m.end(), False))
    for tipo, terminos in SENSIBLES.items():
        for termino in terminos:
            for m in re.finditer(rf"\b{re.escape(termino)}\b", texto, flags=re.IGNORECASE):
                hallazgos.append(Hallazgo("sensible", tipo, m.group(), m.start(), m.end(), True))
    return sorted(hallazgos, key=lambda h: h.inicio)


MARCA = "[DATO RESERVADO]"


def anonimizar(texto, hallazgos):
    """Oculta los datos de identificación y contacto.

    Los términos sensibles no se ocultan: indican el tema del documento, no
    identifican a nadie. Si el tema en sí es reservado, la decisión correcta
    es restringir el documento, no anonimizarlo.
    """
    tramos = sorted(
        (h["inicio"], h["fin"]) for h in hallazgos if not h["sensible"]
    )
    partes, cursor = [], 0
    for inicio, fin in tramos:
        if inicio < cursor:  # tramos superpuestos
            cursor = max(cursor, fin)
            continue
        partes += [texto[cursor:inicio], MARCA]
        cursor = fin
    partes.append(texto[cursor:])
    return "".join(partes)
