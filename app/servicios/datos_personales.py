"""
Detección de posibles datos personales (Ley 1581 de 2012) en el texto de cada archivo.

Son reglas, no IA, y corren en el servidor: el texto no sale a ningún servicio
para esto. Buscan lo que en un archivo colombiano identifica a una persona o
revela algo de ella:

- Personales (art. 3 c): cédula de ciudadanía o de extranjería, pasaporte,
  fecha de nacimiento, correo, celular, dirección, cuenta bancaria, tarjeta.
- Sensibles (art. 5): salud (historia clínica, diagnóstico con código CIE-10,
  incapacidad médica…), origen étnico, opinión política, religión, afiliación
  sindical, vida sexual, datos biométricos.
- De niños, niñas y adolescentes (art. 7): tarjeta de identidad, NUIP,
  menciones de un menor.

Cada hallazgo agrupa todas las veces que el mismo dato aparece en el archivo y
dice su tipo, su categoría, la página, la confianza (fija por regla: un número
con su rótulo es más seguro que una palabra suelta) y qué hacer. Una persona lo
confirma, lo corrige o lo descarta; hasta entonces la descripción del documento
no se publica (ver `exigir_revision`).

Lo que las reglas no pueden saber (si una dirección es de una entidad o de una
persona, si «niños» habla de uno identificable o de la población en general) no
lo afirman: lo dicen en la recomendación y bajan la confianza.
"""

import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.dato_personal import CATEGORIA_DATO, DatoPersonalDetectado
from app.models.evidencia_ia import PaginaTexto
from app.models.instanciacion import Instanciacion

VERSION_REGLAS = "1"
MAX_OCURRENCIAS = 200
ORDEN_CATEGORIA = {None: -1, "no_contiene": 0, "personal": 1, "personales": 1, "sensible": 2, "sensibles": 2,
                   "menores": 3}
NIVEL_RECURSO = {"personal": "personales", "sensible": "sensibles", "menores": "menores"}  # valores del recurso
CATEGORIA_NOMBRE = {"personal": "Dato personal", "sensible": "Dato sensible", "menores": "Dato de niños, niñas o adolescentes"}

N = r"(?:n[o°º.]*|n[uú]m(?:ero)?\.?)?\s*[:.]?\s*"  # «No.», «N°», «número:»
NUMERO_ID = r"(\d{1,3}(?:[.\s]\d{3}){1,3}|\d{5,11})"


@dataclass(frozen=True)
class Regla:
    clave: str
    tipo: str
    nombre: str
    categoria: str
    confianza: float
    patron: re.Pattern
    recomendacion: str
    grupo: int = 0  # grupo del patrón con el valor; 0 = toda la coincidencia
    agrupar_por_tipo: bool = False  # palabras: un hallazgo por tipo, no por valor
    valida: object = None  # función extra sobre el valor


def _luhn(valor: str) -> bool:
    d = [int(c) for c in re.sub(r"\D", "", valor)][::-1]
    if not 13 <= len(d) <= 19:
        return False
    return sum(x if i % 2 == 0 else (x * 2 - 9 if x * 2 > 9 else x * 2) for i, x in enumerate(d)) % 10 == 0


GENERICOS = {"contacto", "info", "informacion", "notificaciones", "notificacionesjudiciales", "correspondencia",
             "servicioalciudadano", "atencionalciudadano", "radicacion", "pqrs", "pqrsd", "soporte", "ventanilla",
             "contactenos", "comunicaciones", "prensa", "admin", "webmaster", "noreply", "no-reply"}


def _correo_personal(valor: str) -> bool:
    return re.sub(r"[._-]", "", valor.split("@")[0].lower()) not in GENERICOS


I = re.IGNORECASE
REC_IDENTIFICA = "Identifica a una persona. Si la descripción queda pública, no lo transcriba en ella."
REGLAS: tuple[Regla, ...] = (
    # Niños, niñas y adolescentes (art. 7): primero, para que un número con su rótulo no se tome por cédula.
    Regla("tarjeta_identidad", "tarjeta_identidad", "Tarjeta de identidad", "menores", 0.95,
          re.compile(r"(?:\btarjeta\s+de\s+identidad|\bT\.\s?I\.?|\bTI\b)\s*" + N + NUMERO_ID),
          "Es de un niño, niña o adolescente: su tratamiento está restringido (Ley 1581, art. 7). "
          "No lo publique; clasifique o anonimice la versión de consulta.", grupo=1),
    Regla("nuip", "registro_civil", "NUIP o registro civil de nacimiento", "menores", 0.7,
          re.compile(r"\b(?:NUIP|registro\s+civil\s+de\s+nacimiento)\s*" + N + r"(\d{1,3}(?:[.\s]\d{3}){1,3}|\d{6,11})?", I),
          "Suele identificar a un menor. Verifique la edad de la persona; si es adulta, corríjalo a dato personal."),
    Regla("menor_de_edad", "mencion_menor", "Mención de un menor de edad", "menores", 0.7,
          # Sin ignorar mayúsculas: «el menor Juan» sí, «el menor impacto» y «El Niño» no.
          re.compile(r"\b(?:[Mm]enor(?:es)?\s+de\s+edad|(?:[Ee]l|[Ll]a|[Dd]el|[Aa]l)\s+(?:menor|niñ[oa]|adolescente)"
                     r"\s+(?=[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b))"),
          "Habla de un menor. Si se puede identificar (nombre, colegio, familia), es dato de menores; "
          "si es la población en general, descártelo.", agrupar_por_tipo=True),
    # Identificación.
    Regla("cedula", "cedula", "Cédula de ciudadanía o de extranjería", "personal", 0.95,
          re.compile(r"(?:\bc[ée]dula(?:\s+de\s+(?:ciudadan[ií]a|extranjer[ií]a))?|\bC\.\s?[CE]\.?|\bC[CE]\b|"
                     r"\bidentificad[oa]\s+con(?:\s+(?:la\s+)?c[ée]dula(?:\s+de\s+ciudadan[ií]a)?)?)\s*" + N + NUMERO_ID, I),
          REC_IDENTIFICA, grupo=1),
    Regla("pasaporte", "pasaporte", "Pasaporte", "personal", 0.9,
          re.compile(r"\bpasaporte\s*" + N + r"([A-Z]{0,3}\d{6,9})\b", I), REC_IDENTIFICA, grupo=1),
    Regla("fecha_nacimiento", "fecha_nacimiento", "Fecha de nacimiento", "personal", 0.9,
          re.compile(r"\b(?:fecha\s+de\s+nacimiento|nacid[oa]\s+el)\s*[:.]?\s*"
                     r"(\d{1,2}\s*(?:/|-|de)\s*(?:\d{1,2}|[a-zé]+)\s*(?:/|-|de)\s*\d{2,4})", I),
          "Con el nombre identifica a la persona y revela su edad. Verifique si es de un menor.", grupo=1),
    # Contacto.
    Regla("correo", "correo", "Correo electrónico", "personal", 0.75,
          re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
          "Si es el correo de una persona, es dato personal. Los buzones institucionales no se detectan; "
          "si este lo es, descártelo.", valida=_correo_personal),
    Regla("celular", "telefono", "Número de celular", "personal", 0.8,
          re.compile(r"(?<![\d.$,])(?:\+?57[\s-]?)?3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}(?!\d|[.,]\d)"),
          "Si es el celular de una persona, es dato personal. Si es una línea institucional, descártelo."),
    Regla("direccion", "direccion", "Dirección", "personal", 0.6,
          re.compile(r"\b(?:calle|cl|carrera|cra|kra|kr|avenida|av|diagonal|dg|transversal|tv)\.?\s*\d{1,3}\s*"
                     r"[a-z]?\s*(?:bis\s*[a-z]?)?\s*(?:#|n[o°º.]+)\s*\d{1,3}\s*[a-z]?\s*[-–]\s*\d{1,3}\b", I),
          "Si es el domicilio de una persona, es dato personal. Si es la sede de una entidad, descártelo."),
    # Financieros.
    Regla("cuenta_bancaria", "cuenta_bancaria", "Cuenta bancaria", "personal", 0.9,
          re.compile(r"\bcuenta\s+(?:de\s+)?(?:ahorros|corriente)\s*" + N + r"(\d[\d\s-]{5,22}\d)", I),
          "Dato financiero de una persona: no lo transcriba en una descripción pública.", grupo=1),
    Regla("tarjeta", "tarjeta_credito", "Número de tarjeta", "personal", 0.85,
          # Con su rótulo: sin él, un número de radicado largo pasaría la verificación una de cada diez veces.
          re.compile(r"\btarjeta(?:\s+de\s+cr[eé]dito|\s+d[eé]bito)?\s*" + N + r"((?:\d[\s-]?){12,18}\d)(?!\d)", I),
          "Número de tarjeta con su rótulo (cumple la verificación de Luhn).", grupo=1, valida=_luhn),
    # Sensibles (art. 5).
    Regla("historia_clinica", "salud", "Salud: historia clínica", "sensible", 0.85,
          re.compile(r"\bhistoria\s+cl[ií]nica\b", I),
          "Dato de salud: sensible. Si la descripción queda pública, clasifíquela o anonimice la versión de consulta.",
          agrupar_por_tipo=True),
    Regla("diagnostico_cie", "salud", "Salud: diagnóstico con código", "sensible", 0.9,
          re.compile(r"\b[Dd]iagn[oó]stic[oa]s?\b[^.\n]{0,40}?\b([A-TV-Z]\d{2}(?:\.\d{1,2})?)\b"),
          "Diagnóstico con código CIE-10: dato sensible de salud.", grupo=1),
    Regla("salud", "salud", "Salud", "sensible", 0.7,
          re.compile(r"\b(?:diagn[oó]stico\s+(?:m[eé]dico|cl[ií]nico)|incapacidad\s+(?:m[eé]dica|laboral)|"
                     r"(?:dictamen|calificaci[oó]n)\s+de\s+(?:p[eé]rdida\s+de\s+)?capacidad\s+laboral|"
                     r"\bVIH\b|\bSIDA\b|tratamiento\s+(?:m[eé]dico|psiqui[aá]trico|psicol[oó]gico)|"
                     r"en\s+estado\s+de\s+(?:embarazo|gestaci[oó]n)|licencia\s+de\s+maternidad)", I),
          "Dato de salud de una persona: sensible. Si habla de un programa o de la población, descártelo.",
          agrupar_por_tipo=True),
    Regla("etnico", "origen_etnico", "Origen racial o étnico", "sensible", 0.6,
          re.compile(r"\b(?:pertenencia\s+[ée]tnica|autorreconoc\w*\s+(?:como|[ée]tnic\w*)|origen\s+(?:racial|[ée]tnico))", I),
          "Si se refiere a una persona identificable es sensible. Si habla de una comunidad o de un "
          "proceso colectivo (por ejemplo, una consulta previa), descártelo.", agrupar_por_tipo=True),
    Regla("politica", "opinion_politica", "Orientación política", "sensible", 0.6,
          re.compile(r"\b(?:filiaci[oó]n\s+pol[ií]tica|militante\s+del?\s+partido|afiliad[oa]\s+al?\s+partido|"
                     r"orientaci[oó]n\s+pol[ií]tica)", I),
          "Revela la orientación política de una persona: sensible.", agrupar_por_tipo=True),
    Regla("religion", "religion", "Convicciones religiosas", "sensible", 0.6,
          re.compile(r"\b(?:creencias?\s+religiosas?|convicci[oó]n(?:es)?\s+religiosas?|confesi[oó]n\s+religiosa|"
                     r"religi[oó]n\s+que\s+profesa)", I),
          "Revela las convicciones religiosas de una persona: sensible.", agrupar_por_tipo=True),
    Regla("sindical", "sindical", "Pertenencia a un sindicato", "sensible", 0.65,
          re.compile(r"\b(?:afiliad[oa]s?\s+al\s+sindicato|afiliaci[oó]n\s+sindical|miembro\s+del\s+sindicato|"
                     r"fuero\s+sindical)", I),
          "Revela la pertenencia de una persona a un sindicato: sensible.", agrupar_por_tipo=True),
    Regla("sexual", "vida_sexual", "Vida sexual", "sensible", 0.7,
          re.compile(r"\b(?:orientaci[oó]n\s+sexual|identidad\s+de\s+g[eé]nero|vida\s+sexual|violencia\s+sexual|"
                     r"abuso\s+sexual)", I),
          "Dato sobre la vida sexual de una persona: sensible.", agrupar_por_tipo=True),
    Regla("biometrico", "biometrico", "Dato biométrico", "sensible", 0.7,
          re.compile(r"\b(?:huellas?\s+dactilar(?:es)?|datos?\s+biom[eé]tricos?|reconocimiento\s+facial)", I),
          "Dato biométrico: sensible. Si el documento solo menciona el procedimiento, descártelo.",
          agrupar_por_tipo=True),
)
TIPOS = {r.tipo: r.nombre.split(":")[0] for r in REGLAS}
POR_CLAVE = {r.clave: r for r in REGLAS}


@dataclass
class Hallazgo:
    regla: Regla
    valor: str
    ocurrencias: list = field(default_factory=list)


def _normal(valor: str) -> str:
    return re.sub(r"[\s.\-]", "", valor).lower()


def _huella(tipo: str, valor: str) -> str:
    clave = (settings.secret_key or "ricora-sin-clave").encode()
    return hmac.new(clave, f"{tipo}|{_normal(valor)}".encode(), hashlib.sha256).hexdigest()


def enmascarar(valor: str) -> str:
    """Deja ver los tres últimos caracteres útiles y el dominio de un correo."""
    valor = " ".join(valor.split())[:100]
    if "@" in valor:
        usuario, dominio = valor.split("@", 1)
        return (usuario[:1] + "•" * max(len(usuario) - 1, 2)) + "@" + dominio
    utiles = [i for i, c in enumerate(valor) if c.isalnum()]
    visibles = set(utiles[-3:]) if len(utiles) > 4 else set()
    return "".join(c if (not c.isalnum() or i in visibles) else "•" for i, c in enumerate(valor))


def detectar(texto: str) -> list[Hallazgo]:
    """Los posibles datos personales del texto, agrupados por tipo y valor."""
    texto = texto or ""
    ocupado: list[tuple[int, int]] = []
    grupos: dict[tuple, Hallazgo] = {}
    for regla in REGLAS:
        for m in regla.patron.finditer(texto):
            g = regla.grupo if m.group(regla.grupo) else 0
            inicio, fin = m.span(g)
            valor = m.group(g)
            if regla.valida and not regla.valida(valor):
                continue
            # Un mismo tramo no se cuenta dos veces (el celular dentro de una cuenta, la cédula de una TI).
            if any(inicio < f and i < fin for i, f in ocupado):
                continue
            ocupado.append((inicio, fin))
            clave = (regla.tipo, regla.clave if regla.agrupar_por_tipo else _normal(valor))
            h = grupos.setdefault(clave, Hallazgo(regla, valor if not regla.agrupar_por_tipo else regla.nombre))
            if len(h.ocurrencias) < MAX_OCURRENCIAS:
                h.ocurrencias.append((inicio, fin))
    return list(grupos.values())


def _pagina(paginas: list[PaginaTexto], posicion: int) -> int | None:
    return next((p.numero for p in paginas if p.inicio <= posicion < p.fin + 2), None)


def _sello(inst: Instanciacion) -> str:
    return f"{VERSION_REGLAS}:{hashlib.sha256((inst.texto_extraido or '').encode()).hexdigest()}"


def revisar(db: Session, inst: Instanciacion) -> list[DatoPersonalDetectado]:
    """Revisa el texto del archivo si cambió o si cambiaron las reglas; devuelve los hallazgos nuevos.

    Lo ya decidido no se toca. Un hallazgo pendiente que ya no aparece (el texto se
    volvió a leer) lo cierra el sistema como descartado, con su motivo."""
    if not inst.texto_extraido:
        return []
    sello = _sello(inst)
    if inst.revision_datos_personales == sello:
        return []
    paginas = list(db.scalars(select(PaginaTexto).where(PaginaTexto.instanciacion_id == inst.id)
                              .order_by(PaginaTexto.numero)))
    existentes = {(d.tipo, d.huella_valor): d for d in db.scalars(
        select(DatoPersonalDetectado).where(DatoPersonalDetectado.instanciacion_id == inst.id))}
    vistos, nuevos = set(), []
    for h in detectar(inst.texto_extraido):
        huella = _huella(h.regla.tipo, h.regla.clave if h.regla.agrupar_por_tipo else h.valor)
        ocurrencias = [{"pagina": _pagina(paginas, i), "inicio": i, "fin": f} for i, f in h.ocurrencias]
        vistos.add((h.regla.tipo, huella))
        d = existentes.get((h.regla.tipo, huella))
        if d is not None:
            d.ocurrencias = ocurrencias  # las posiciones cambian si el texto se volvió a leer
            continue
        d = DatoPersonalDetectado(
            id=uuid.uuid4(), instanciacion_id=inst.id, fondo_id=inst.fondo_id, tipo=h.regla.tipo,
            categoria=h.regla.categoria, confianza=h.regla.confianza, regla=h.regla.clave,
            version_reglas=VERSION_REGLAS, muestra=h.valor if h.regla.agrupar_por_tipo else enmascarar(h.valor),
            huella_valor=huella, ocurrencias=ocurrencias, estado="pendiente", detectado_en=ahora())
        db.add(d)
        nuevos.append(d)
    for clave, d in existentes.items():
        if clave not in vistos and d.estado == "pendiente":
            d.estado, d.decidido_en = "descartado", ahora()
            d.motivo = "El sistema volvió a leer el texto y ya no lo encuentra."
    inst.revision_datos_personales = sello
    db.flush()
    return nuevos


def alertar(db: Session, inst: Instanciacion, nuevos: list[DatoPersonalDetectado]) -> None:
    """Alerta en el panel si hay datos sensibles o de menores (sin el dato: solo tipo y cantidad)."""
    from app.servicios import alertas

    graves = [d for d in nuevos if d.categoria in ("sensible", "menores")]
    if not graves:
        return
    tipos = sorted({TIPOS.get(d.tipo, d.tipo) for d in graves})
    menores = any(d.categoria == "menores" for d in graves)
    alertas.crear(
        db, tipo="datos_personales_sensibles", severidad="alta", modulo="descripcion", entidad_tipo="instanciacion",
        entidad_id=inst.id, fondo_id=inst.fondo_id,
        mensaje=f"«{inst.nombre_original}»: el sistema encontró posibles datos "
                f"{'de niños, niñas o adolescentes' if menores else 'sensibles'} ({', '.join(tipos)}). "
                "Revíselos al describir el documento antes de publicarlo (Ley 1581, arts. 5 a 7).",
        detalle={"hallazgos": len(graves), "tipos": tipos})


def contexto(texto: str, inicio: int, fin: int, margen: int = 70) -> dict:
    a = max(0, inicio - margen)
    b = min(len(texto), fin + margen)
    return {"antes": ("…" if a else "") + texto[a:inicio], "valor": texto[inicio:fin],
            "despues": texto[fin:b] + ("…" if b < len(texto) else "")}


def categoria_vigente(d: DatoPersonalDetectado) -> str | None:
    if d.estado == "descartado":
        return None
    return d.categoria_final or d.categoria


def out(d: DatoPersonalDetectado, texto: str | None, nombres: dict | None = None) -> dict:
    regla = POR_CLAVE.get(d.regla)
    primera = d.ocurrencias[0] if d.ocurrencias else None
    return {
        "id": str(d.id), "instanciacion_id": str(d.instanciacion_id), "tipo": d.tipo,
        "tipo_nombre": regla.nombre if regla else TIPOS.get(d.tipo, d.tipo), "categoria": d.categoria,
        "categoria_nombre": CATEGORIA_NOMBRE[d.categoria], "confianza": d.confianza, "muestra": d.muestra,
        "veces": len(d.ocurrencias), "paginas": sorted({o["pagina"] for o in d.ocurrencias if o["pagina"]}),
        "contexto": contexto(texto, primera["inicio"], primera["fin"]) if texto and primera else None,
        "recomendacion": regla.recomendacion if regla else "",
        "estado": d.estado, "tipo_final": d.tipo_final, "categoria_final": d.categoria_final, "motivo": d.motivo,
        "decidido_por": (nombres or {}).get(d.decidido_por_id) if d.decidido_por_id else
                        ("El sistema" if d.decidido_en else None),
        "decidido_en": d.decidido_en.isoformat() if d.decidido_en else None,
    }


def de_documentos(db: Session, documentos: list[Instanciacion]) -> dict:
    """Lo que la pantalla de descripción muestra: los hallazgos y el nivel que se deduce de ellos."""
    from app.models.usuario import Usuario

    for inst in documentos:
        alertar(db, inst, revisar(db, inst))
    ids = [d.id for d in documentos]
    filas = list(db.scalars(select(DatoPersonalDetectado).where(DatoPersonalDetectado.instanciacion_id.in_(ids))
                            .order_by(DatoPersonalDetectado.detectado_en))) if ids else []
    nombres = dict(db.execute(select(Usuario.id, Usuario.nombre)).all()) if filas else {}
    textos = {d.id: d.texto_extraido for d in documentos}
    pendientes = [d for d in filas if d.estado == "pendiente"]
    return {
        "documentos": [{"id": str(i.id), "nombre": i.nombre_original, "revisado": bool(i.revision_datos_personales),
                        "hallazgos": [out(d, textos[i.id], nombres) for d in filas if d.instanciacion_id == i.id]}
                       for i in documentos],
        "pendientes": len(pendientes),
        "nivel_propuesto": nivel_confirmado(filas),
        "sin_texto": [i.nombre_original for i in documentos if not i.texto_extraido],
    }


def nivel_confirmado(filas: list[DatoPersonalDetectado]) -> str | None:
    """El nivel del recurso (no_contiene/personales/sensibles/menores) que exigen los hallazgos confirmados."""
    mayor = max((categoria_vigente(d) for d in filas if d.estado in ("confirmado", "corregido")),
                key=lambda c: ORDEN_CATEGORIA[c], default=None)
    return NIVEL_RECURSO.get(mayor) if mayor else None


class ErrorDatoPersonal(ValueError):
    pass


def decidir(db: Session, d: DatoPersonalDetectado, *, accion: str, usuario_id: uuid.UUID,
            categoria: str | None = None, tipo: str | None = None, motivo: str | None = None) -> dict:
    """Confirmar, corregir o descartar. Devuelve el antes y el después para la auditoría."""
    motivo = (motivo or "").strip() or None
    antes = {"estado": d.estado, "categoria": categoria_vigente(d) or d.categoria, "tipo": d.tipo_final or d.tipo,
             "motivo": d.motivo}
    if accion == "confirmar":
        d.estado, d.tipo_final, d.categoria_final = "confirmado", None, None
    elif accion == "corregir":
        if categoria not in CATEGORIA_DATO:
            raise ErrorDatoPersonal("Indique la categoría correcta: dato personal, sensible o de menores.")
        if tipo and tipo not in TIPOS:
            raise ErrorDatoPersonal("El tipo de dato no existe.")
        if categoria == d.categoria and (not tipo or tipo == d.tipo):
            raise ErrorDatoPersonal("La corrección no cambia nada: si el hallazgo está bien, confírmelo.")
        d.estado, d.categoria_final, d.tipo_final = "corregido", categoria, tipo if tipo and tipo != d.tipo else None
    elif accion == "descartar":
        if not motivo or len(motivo) < 4:
            raise ErrorDatoPersonal("Diga por qué lo descarta (por ejemplo, «es el correo institucional de la entidad»).")
        d.estado = "descartado"
    else:
        raise ErrorDatoPersonal("La acción debe ser confirmar, corregir o descartar.")
    d.motivo = motivo if accion != "confirmar" else (motivo or None)
    d.decidido_por_id, d.decidido_en = usuario_id, ahora()
    despues = {"estado": d.estado, "categoria": categoria_vigente(d), "tipo": d.tipo_final or d.tipo, "motivo": d.motivo}
    return {"anterior": antes, "nuevo": despues}


def exigir_revision(db: Session, documentos: list[Instanciacion], recurso, usuario_id: uuid.UUID) -> None:
    """Antes de publicar o corregir: nada pendiente, y el nivel declarado no puede ser menor que lo confirmado.

    Si la persona no declaró el nivel, se toma el de los hallazgos confirmados."""
    from app.servicios.descripcion import ErrorDescripcion

    for inst in documentos:
        revisar(db, inst)
    ids = [i.id for i in documentos]
    if not ids:
        return
    filas = list(db.scalars(select(DatoPersonalDetectado).where(DatoPersonalDetectado.instanciacion_id.in_(ids))))
    pendientes = [d for d in filas if d.estado == "pendiente"]
    if pendientes:
        raise ErrorDescripcion(
            f"Hay {len(pendientes)} posible(s) dato(s) personal(es) sin revisar. Confírmelos, corríjalos o "
            "descártelos en «Datos personales» antes de publicar (Ley 1581 de 2012).",
            datos={"datos_personales_pendientes": len(pendientes)})
    nivel = nivel_confirmado(filas)
    if nivel is None:
        return
    if recurso.datos_personales is None:
        from app.servicios.auditoria import registrar

        recurso.datos_personales = nivel
        registrar(db, modulo="descripcion", accion="proteccion_datos_declarada", usuario_id=usuario_id,
                  entidad_tipo="recurso_documental", entidad_id=recurso.id,
                  detalle=f"Datos personales de «{recurso.titulo}», según los hallazgos confirmados",
                  anterior={"datos_personales": None}, nuevo={"datos_personales": nivel})
    elif ORDEN_CATEGORIA[recurso.datos_personales] < ORDEN_CATEGORIA[nivel]:
        nombre = {"personales": "datos personales", "sensibles": "datos sensibles",
                  "menores": "datos de niños, niñas o adolescentes"}[nivel]
        raise ErrorDescripcion(f"Confirmó {nombre} en el documento, pero la descripción declara menos. "
                               "Corrija el campo «Datos personales» o revise los hallazgos.")
