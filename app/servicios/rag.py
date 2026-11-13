"""
Recuperación de pasajes para el Asistente RICORA (RAG, generación aumentada por recuperación).

Antes de responder, el asistente busca en lo que la entidad tiene:

1. la biblioteca de referencia (leyes, acuerdos del AGN, manuales y procedimientos que carga la
   administración);
2. el texto de los documentos cargados al fondo activo (OCR o capa de texto);
3. las descripciones publicadas del fondo (título, alcance y contenido, notas).

La búsqueda usa el mismo índice de PostgreSQL del buscador (en español y sin tildes, migración
0035): no hace falta otra base de vectores ni otro servicio. De cada documento encontrado se toman
los pasajes donde aparecen las palabras de la pregunta (`ts_headline`), y esos pasajes, numerados,
son lo único con lo que el motor puede responder.

**Reserva.** Nunca se recupera un archivo ni una descripción bajo reserva o clasificación (Ley 1712,
arts. 18 y 19), propia o heredada, ni lo que no está publicado: el texto saldría hacia el motor.
**Datos personales.** Los pasajes pasan por el mismo filtro de identificadores que la descripción
(Ley 1581) antes de salir.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_PASAJES = 8
MAX_CARACTERES_PASAJE = 1400
LARGO_TEXTO = 400_000  # cuánto texto de un documento se recorre para sacar el pasaje
OPCIONES = ('StartSel="", StopSel="", MaxWords=90, MinWords=40, MaxFragments=3, '
            'FragmentDelimiter=" … ", ShortWord=2')
_PALABRA = re.compile(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}")


@dataclass
class Pasaje:
    numero: int
    tipo: str  # norma | documento | descripcion
    titulo: str
    detalle: str
    texto: str
    id: str
    enlace: str | None = None

    def out(self) -> dict:
        return {"numero": self.numero, "tipo": self.tipo, "titulo": self.titulo, "detalle": self.detalle,
                "id": self.id, "enlace": self.enlace, "extracto": self.texto[:300]}


def consulta(pregunta: str) -> str | None:
    """La pregunta como búsqueda «o»: basta que un pasaje tenga algunas de sus palabras (las vacías,
    como «de» o «cómo», las descarta el diccionario del español). Se ordena por cuántas tiene."""
    palabras = list(dict.fromkeys(p.lower() for p in _PALABRA.findall(pregunta or "")))[:24]
    return " or ".join(palabras) if palabras else None


def _limpio(fragmento: str | None) -> str:
    return re.sub(r"\s+", " ", fragmento or "").strip()[:MAX_CARACTERES_PASAJE]


def _normas(db: Session, q: str, limite: int) -> list[dict]:
    filas = db.execute(text(f"""
        SELECT d.id, d.titulo, d.clase, d.paginas, ts_rank_cd(d.busqueda, c, 32) AS rango,
               ts_headline('public.ricora_es', left(d.texto, {LARGO_TEXTO}), c, :op) AS pasaje
        FROM documentos_referencia d, websearch_to_tsquery('public.ricora_es', :q) c
        WHERE d.estado = 'listo' AND d.busqueda @@ c
        ORDER BY rango DESC LIMIT :limite"""), {"q": q, "op": OPCIONES, "limite": limite}).all()
    from app.servicios.biblioteca import CLASE_NOMBRE

    return [{"tipo": "norma", "id": str(i), "titulo": t, "detalle": CLASE_NOMBRE.get(c, "Referencia"),
             "rango": float(r), "texto": _limpio(p), "enlace": None} for i, t, c, _, r, p in filas if _limpio(p)]


def _documentos(db: Session, q: str, fondo_id: uuid.UUID, limite: int) -> list[dict]:
    from app.models.instanciacion import Instanciacion
    from app.servicios import derechos

    filas = db.execute(text(f"""
        SELECT i.id, i.nombre_original, ts_rank_cd(i.busqueda, c, 32) AS rango,
               ts_headline('public.ricora_es', left(i.texto_extraido, {LARGO_TEXTO}), c, :op) AS pasaje
        FROM instanciaciones i, websearch_to_tsquery('public.ricora_es', :q) c
        WHERE i.fondo_id = :fondo AND i.busqueda @@ c AND i.estado = 'listo_para_descripcion'
              AND i.derivada_de_id IS NULL
        ORDER BY rango DESC LIMIT :limite"""), {"q": q, "op": OPCIONES, "fondo": fondo_id, "limite": limite * 3}).all()
    salida = []
    for inst_id, nombre, rango, pasaje in filas:
        inst = db.get(Instanciacion, inst_id)
        if derechos.instanciacion_restringida(db, inst):
            continue  # el texto de un archivo reservado no sale hacia el motor
        if _limpio(pasaje):
            salida.append({"tipo": "documento", "id": str(inst_id), "titulo": nombre, "detalle": "Documento cargado",
                           "rango": float(rango), "texto": _limpio(pasaje), "enlace": None})
        if len(salida) >= limite:
            break
    return salida


def _descripciones(db: Session, q: str, fondo_id: uuid.UUID, limite: int) -> list[dict]:
    from app.models.recurso_documental import RecursoDocumental
    from app.servicios import derechos
    from app.servicios.busqueda import CAMPOS_FRAGMENTO

    campos = " || ' ' || ".join(f"coalesce(r.{c}, '')" for c in ("titulo", *CAMPOS_FRAGMENTO))
    filas = db.execute(text(f"""
        SELECT r.id, r.titulo, r.nivel, r.codigo_referencia, ts_rank_cd(r.busqueda, c, 32) AS rango,
               ts_headline('public.ricora_es', {campos}, c, :op) AS pasaje
        FROM recursos_documentales r, websearch_to_tsquery('public.ricora_es', :q) c
        WHERE r.fondo_id = :fondo AND r.busqueda @@ c AND r.publicado_en IS NOT NULL
        ORDER BY rango DESC LIMIT :limite"""), {"q": q, "op": OPCIONES, "fondo": fondo_id, "limite": limite * 3}).all()
    salida = []
    for rid, titulo, nivel, codigo, rango, pasaje in filas:
        recurso = db.get(RecursoDocumental, rid)
        if derechos.restringe(derechos.declaracion_de_recurso(db, recurso)):
            continue
        if _limpio(pasaje):
            salida.append({"tipo": "descripcion", "id": str(rid), "titulo": titulo,
                           "detalle": f"Descripción ({nivel.replace('_', ' ')}{f', {codigo}' if codigo else ''})",
                           "rango": float(rango), "texto": _limpio(pasaje), "enlace": f"/descripcion/registro/{rid}"})
        if len(salida) >= limite:
            break
    return salida


def recuperar(db: Session, pregunta: str, fondo_id: uuid.UUID | None, maximo: int = MAX_PASAJES) -> list[Pasaje]:
    """Los pasajes más pertinentes para la pregunta, de las tres fuentes, mezclados por puntaje."""
    q = consulta(pregunta)
    if not q:
        return []
    candidatos = _normas(db, q, maximo)
    if fondo_id is not None:
        candidatos += _documentos(db, q, fondo_id, maximo) + _descripciones(db, q, fondo_id, maximo)
    candidatos.sort(key=lambda c: c["rango"], reverse=True)
    vistos, pasajes = set(), []
    for c in candidatos:
        if c["texto"] in vistos:
            continue
        vistos.add(c["texto"])
        pasajes.append(Pasaje(numero=len(pasajes) + 1, tipo=c["tipo"], titulo=c["titulo"], detalle=c["detalle"],
                              texto=c["texto"], id=c["id"], enlace=c["enlace"]))
        if len(pasajes) >= maximo:
            break
    return pasajes


def contexto(pasajes: list[Pasaje]) -> str:
    """Los pasajes numerados, listos para el motor, sin datos personales."""
    from app.servicios.datos_personales import anonimizar_para_motor

    bloques = []
    for p in pasajes:
        bloques.append(f"[{p.numero}] {p.titulo} ({p.detalle})\n{anonimizar_para_motor(p.texto)[0]}")
    return "\n\n".join(bloques)
