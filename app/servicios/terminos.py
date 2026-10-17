"""
Vocabulario único de las relaciones: cómo se llama cada relación en el
sistema, en el grafo, en las fichas, en los instrumentos, en la auditoría y
en la evaluación.

Antes cada parte tenía sus nombres («producido por» en el grafo,
«Productor» en la descripción, «se dirige a» en la etiqueta oficial…). Ahora
cada relación (código del mapeo de RiC-O, con su rol si lo tiene) tiene aquí:

- nombre: el término archivístico, como sustantivo («Productor»). Es el que
  se elige al describir y el que encabeza la ficha;
- directa: cómo se lee la relación desde el origen de la fila guardada
  («documento — producido por → Alcaldía»). Es la etiqueta del grafo;
- inversa: cómo se lee desde el destino («Alcaldía — productor de →
  documento»). La usan las fichas de autoridad.

La propiedad de RiC-O, su código RiC-CM y su etiqueta oficial en español
siguen saliendo del mapeo (servicios/ric_o.py); aquí solo está el nombre en
español del sistema. Ningún otro módulo escribe un nombre de relación a
mano: lo toman de aquí (las pruebas lo verifican). La interfaz recibe una
copia generada (frontend/src/lib/terminos.ts) y la documentación, la tabla
(documentacion/vocabulario-relaciones.md); `python -m app.cli terminos` las
regenera y una prueba falla si quedaron desactualizadas.
"""

from dataclasses import dataclass
from pathlib import Path

from app.servicios import ric_o


@dataclass(frozen=True)
class Termino:
    nombre: str
    directa: str
    inversa: str


# (código, rol) → término. El rol None es el término general de la relación;
# un rol propio (expedición, creación…) lo precisa cuando cambia el sentido.
TERMINOS: dict[tuple[str, str | None], Termino] = {
    # --- Procedencia (desde el documento) ---
    ("has_creator", None): Termino("Productor", "producido por", "productor de"),
    ("has_author", None): Termino("Autor", "escrito por", "autor de"),
    ("has_sender", None): Termino("Remitente", "remitido por", "remitente de"),
    ("has_addressee", None): Termino("Destinatario", "dirigido a", "destinatario de"),
    ("has_accumulator", None): Termino("Acumulador", "acumulado por", "acumulador de"),
    ("has_or_had_holder", None): Termino("Custodio", "custodiado por", "custodia o custodió"),
    # --- Estructura documental ---
    ("includes_or_included", None): Termino("Inclusión", "incluye", "está incluido en"),
    ("has_or_had_constituent", None): Termino("Parte documental", "tiene la parte", "es parte de"),
    ("precedes_or_preceded", None): Termino("Secuencia", "precede a", "sigue a"),
    ("has_or_had_instantiation", None): Termino("Instanciación", "tiene la instanciación", "es instanciación de"),
    ("migrated_into", None): Termino("Migración", "migrada a", "migrada desde"),
    ("has_or_had_derived_instantiation", None): Termino("Instanciación derivada", "tiene como derivada a",
                                                        "deriva de"),
    # --- Contexto funcional ---
    ("documents", None): Termino("Actividad documentada", "documenta", "está documentada en"),
    ("has_activity_type", None): Termino("Función (tipo de actividad)", "es del tipo", "es el tipo de"),
    ("performs_or_performed", None): Termino("Agente que ejerce la actividad", "ejerce o ejerció",
                                             "es o fue ejercida por"),
    ("has_direct_subevent", None): Termino("Subactividad", "tiene como sub-actividad a", "es sub-actividad de"),
    ("regulates_or_regulated", None): Termino("Norma que regula", "regula", "está regulada por"),
    ("regulates_or_regulated", "jerarquia_normativa"): Termino("Norma superior", "es norma superior de",
                                                               "desarrolla o deriva de"),
    ("regulates_or_regulated", "creacion"): Termino("Norma que crea la competencia", "crea la competencia",
                                                    "es una competencia creada por"),
    ("regulates_or_regulated", "retencion"): Termino("Regla de retención", "regula la retención de",
                                                     "tiene su retención regulada por"),
    ("issued_by", None): Termino("Quien expide la norma", "fue expedido por", "expidió"),
    ("authorizes", None): Termino("Norma que autoriza al agente", "autoriza a", "está autorizado por"),
    ("authorizes", "creacion"): Termino("Norma de creación", "crea o establece a", "fue creado o establecido por"),
    ("is_related_to", None): Termino("Relación general", "está relacionado con", "está relacionado con"),
    ("is_related_to", "serie_producida"): Termino("Función que produce la serie", "produce la serie",
                                                  "es producida por la función"),
    # --- Agente a agente ---
    ("has_or_had_subordinate", None): Termino("Subordinación", "tiene o tuvo como subordinado a",
                                              "está o estuvo subordinado a"),
    ("has_successor", None): Termino("Sucesión", "tiene como sucesor a", "es sucesor de"),
    ("is_agent_associated_with_agent", None): Termino("Agentes asociados", "está asociado con", "está asociado con"),
    ("occupies_or_occupied", None): Termino("Ocupación de un cargo", "ocupa u ocupó el cargo", "es o fue ocupado por"),
    ("has_family_association_with", None): Termino("Parentesco", "tiene parentesco con", "tiene parentesco con"),
    ("has_family_association_with", "progenitor"): Termino("Parentesco: progenitor", "es padre o madre de",
                                                           "es hijo o hija de"),
    ("has_family_association_with", "hermano"): Termino("Parentesco: hermanos", "es hermano o hermana de",
                                                        "es hermano o hermana de"),
    ("has_family_association_with", "conyuge"): Termino("Parentesco: cónyuges", "es o fue cónyuge de",
                                                        "es o fue cónyuge de"),
    ("has_or_had_member", None): Termino("Miembro de un grupo", "tiene o tuvo como miembro a", "es o fue miembro de"),
    ("is_or_was_leader_of", None): Termino("Dirección de un grupo", "dirige o dirigió", "es o fue dirigido por"),
    ("has_or_had_subdivision", None): Termino("Subdivisión", "tiene o tuvo como subdivisión a",
                                              "es o fue subdivisión de"),
    ("exists_or_existed_in", None): Termino("Cargo dentro de una entidad", "existe o existió en",
                                            "tiene o tuvo el cargo"),
    # --- Eventos ---
    ("affects_or_affected", None): Termino("Hito", "afecta o afectó a", "es o fue afectado por"),
    # --- Lugar ---
    ("contains_or_contained", None): Termino("Lugar que contiene a otro", "contiene a", "está dentro de"),
    ("is_or_was_location_of", None): Termino("Localización", "es o fue lugar de", "está o estuvo en"),
    ("is_or_was_location_of", "expedicion"): Termino("Lugar de expedición", "es lugar de expedición de",
                                                     "fue expedido en"),
    ("is_or_was_location_of", "actuacion"): Termino("Lugar de actuación", "es o fue lugar de actuación de",
                                                    "actúa o actuó en"),
    # --- Tema ---
    ("has_or_had_subject", None): Termino("Tema o mencionado", "trata de", "es tema de"),
    ("has_or_had_subject", "mencionado"): Termino("Mencionado", "menciona a", "es mencionado en"),
    ("has_or_had_subject", "lugar"): Termino("Lugar del que trata", "trata del lugar", "es lugar tratado en"),
    ("has_or_had_subject", "mandato"): Termino("Norma citada", "cita la norma", "es citada en"),
    # --- Fechas ---
    ("is_creation_date_of", None): Termino("Fecha de creación", "es fecha de creación de", "fue creado en"),
    ("is_date_associated_with", None): Termino("Fecha asociada", "es fecha de", "tiene la fecha"),
    ("is_date_associated_with", "expedicion"): Termino("Fecha de expedición", "es fecha de expedición de",
                                                       "fue expedido el"),
    # --- Atributo modelado como nodo de apoyo ---
    ("forma_documental", None): Termino("Tipo documental", "es del tipo documental", "es el tipo documental de"),
}


def de(codigo: str | None, rol: str | None = None) -> Termino | None:
    """El término de una relación: el de su rol si lo hay, si no el general."""
    if not codigo:
        return None
    return TERMINOS.get((codigo, rol)) or TERMINOS.get((codigo, None))


def nombre(codigo: str | None, rol: str | None = None) -> str:
    t = de(codigo, rol)
    return t.nombre if t else (codigo or "").replace("_", " ")


def directa(codigo: str | None, rol: str | None = None) -> str:
    t = de(codigo, rol)
    return t.directa if t else (codigo or "").replace("_", " ")


def inversa(codigo: str | None, rol: str | None = None) -> str:
    t = de(codigo, rol)
    return t.inversa if t else (codigo or "").replace("_", " ")


def catalogo() -> list[dict]:
    """Cada término con su propiedad de RiC-O, su código RiC-CM y la
    etiqueta oficial en español, para la interfaz y la documentación."""
    salida = []
    for (codigo, rol), t in TERMINOS.items():
        p = ric_o.PROPIEDADES.get(codigo)
        rico = ric_o.uri(codigo)
        salida.append({"codigo": codigo, "rol": rol, "nombre": t.nombre, "directa": t.directa, "inversa": t.inversa,
                       "rico": rico, "codigo_cm": p.codigo_cm if p else None,
                       "etiqueta_oficial": ric_o.etiqueta_es(rico.split(":")[1]) if rico else None})
    return salida


# --- Copias generadas: la interfaz y la tabla de la documentación ------------------------------------

RAIZ = Path(__file__).resolve().parent.parent.parent
ARCHIVO_TS = RAIZ / "frontend" / "src" / "lib" / "terminos.ts"
ARCHIVO_MD = RAIZ / "documentacion" / "vocabulario-relaciones.md"


def _ts_texto(s: str | None) -> str:
    return "null" if s is None else '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def generar_ts() -> str:
    lineas = [
        "// GENERADO por `python -m app.cli terminos` desde app/servicios/terminos.py: no editar a mano.",
        "// Vocabulario único de las relaciones (nombre archivístico, lectura directa e inversa).",
        "",
        "export interface Termino { nombre: string; directa: string; inversa: string; rico: string | null;",
        "  codigo_cm: string | null; etiqueta_oficial: string | null }",
        "",
        "// Clave: «código» o «código|rol».",
        "export const TERMINOS: Record<string, Termino> = {",
    ]
    for t in catalogo():
        clave = t["codigo"] + (f"|{t['rol']}" if t["rol"] else "")
        lineas.append(f'  "{clave}": {{ nombre: {_ts_texto(t["nombre"])}, directa: {_ts_texto(t["directa"])}, '
                      f'inversa: {_ts_texto(t["inversa"])}, rico: {_ts_texto(t["rico"])}, '
                      f'codigo_cm: {_ts_texto(t["codigo_cm"])}, etiqueta_oficial: {_ts_texto(t["etiqueta_oficial"])} }},')
    lineas += [
        "};",
        "",
        "// El término de una relación: el de su rol si lo hay, si no el general.",
        "export function termino(codigo: string | null | undefined, rol?: string | null): Termino | null {",
        "  if (!codigo) return null;",
        "  return (rol ? TERMINOS[`${codigo}|${rol}`] : undefined) ?? TERMINOS[codigo] ?? null;",
        "}",
        "",
        "// Rol del agente en la descripción → relación de RiC-O que crea al publicar.",
        "export const RELACION_DEL_ROL: Record<string, string> = {",
    ]
    from app.servicios.descripcion import RELACION_POR_ROL

    for (tipo, rol), (codigo, _) in RELACION_POR_ROL.items():
        if tipo == "agente":
            lineas.append(f'  {rol}: "{codigo}",')
    lineas += ["};", ""]
    return "\n".join(lineas)


def generar_md() -> str:
    lineas = [
        "# Vocabulario de relaciones de RICORA",
        "",
        "<!-- GENERADO por `python -m app.cli terminos` desde app/servicios/terminos.py: no editar a mano. -->",
        "",
        "Un solo nombre por relación en todo el sistema: el grafo, la descripción, las fichas, los instrumentos,",
        "la auditoría y la evaluación. La propiedad, el código RiC-CM y la etiqueta oficial en español vienen del",
        "mapeo verificado contra RiC-O 1.1 (`app/servicios/ric_o.py`).",
        "",
        "- **Término archivístico:** el sustantivo con que se elige y se muestra la relación.",
        "- **Lectura directa:** desde el origen (por ejemplo, documento → «producido por» → agente). Es la etiqueta del grafo.",
        "- **Lectura inversa:** desde el destino (agente → «productor de» → documento).",
        "",
        "| Término archivístico | Rol | Lectura directa | Lectura inversa | Propiedad RiC-O | RiC-CM | Etiqueta oficial (es) |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in catalogo():
        lineas.append(f"| {t['nombre']} | {t['rol'] or '—'} | {t['directa']} | {t['inversa']} | {t['rico'] or '—'} | "
                      f"{t['codigo_cm'] or '—'} | {t['etiqueta_oficial'] or '—'} |")
    lineas.append("")
    return "\n".join(lineas)


def escribir() -> list[Path]:
    ARCHIVO_TS.write_text(generar_ts(), encoding="utf-8")
    ARCHIVO_MD.write_text(generar_md(), encoding="utf-8")
    return [ARCHIVO_TS, ARCHIVO_MD]
