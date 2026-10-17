"""
Guía de los metadatos de la descripción: qué es cada campo, por qué importa
y con qué se relaciona.

Cada atributo del catálogo (servicios/atributos.py) y cada tipo de entidad
tiene aquí su explicación en lenguaje archivístico. Las referencias
normativas no se escriben a mano: el elemento ISAD(G) y la propiedad RiC-O
salen del catálogo de atributos, y la fila del Esquema de Metadatos del AGN
(v1.4), de servicios/perfil_agn.py, por el campo del sistema. Una prueba
exige que todo atributo tenga su explicación.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Guia:
    que_es: str
    por_que: str
    se_relaciona: str
    ejemplo: str | None = None


ATRIBUTOS: dict[str, Guia] = {
    "titulo": Guia(
        "El nombre formal con que se identifica la unidad de descripción.",
        "Es lo primero que ve quien consulta y lo que se busca. Un título con forma documental, asunto, productor y "
        "fecha permite reconocer el documento sin abrirlo.",
        "Resume a la forma documental, al productor (relación Productor) y a la fecha de creación: si cambian, revise "
        "el título.",
        "Oficio de la Alcaldía de Tunja al Concejo Municipal sobre el permiso de fiestas, 1948"),
    "codigo_referencia": Guia(
        "El código que ubica la unidad en el cuadro de clasificación (CCD): fondo, sección, serie, subserie y número.",
        "Identifica la unidad de forma única y conserva el orden original y el principio de procedencia.",
        "Se compone del código del nivel superior (relación Inclusión): una subserie 110.2 está dentro de la serie 110.",
        "CO-AM-110.2-0034"),
    "fechas_extremas": Guia(
        "Las fechas de creación de la unidad, tal como se expresan en el documento o en la práctica del archivo.",
        "Ubica el documento en su tiempo y permite buscar por periodos. Es obligatoria en el FUID.",
        "Se normaliza en «Fechas extremas (EDTF)» y, en un documento, en el nodo Fecha con la relación Fecha de creación.",
        "marzo de 1948; 1948-1952"),
    "fechas_extremas_edtf": Guia(
        "Las mismas fechas en forma normalizada (EDTF, ISO 8601-2), que admite fechas aproximadas, inciertas y abiertas.",
        "Sin forma normalizada no se puede ordenar, filtrar ni comparar por fechas. EDTF no inventa precisión: «1948~» "
        "dice que es aproximada.",
        "Es el valor del nodo Fecha (rico:Date) que el grafo une al documento.",
        "1948-03; 1948~; 1948/1952"),
    "folios": Guia(
        "La cantidad de folios de la unidad.",
        "Es la extensión física: dice cuánto material hay y permite controlar la integridad (que no falte ningún folio).",
        "Completa el volumen documental del FUID junto con caja y carpeta.", "45"),
    "caja": Guia("La caja en que se guarda la unidad.",
                 "Permite encontrar el original en el depósito.",
                 "Va con carpeta y tomo en la ubicación física (signatura topográfica).", "Caja 12"),
    "carpeta": Guia("La carpeta dentro de la caja.", "Precisa la ubicación del original.",
                    "Va con caja y tomo en la ubicación física.", "Carpeta 3"),
    "tomo": Guia("El tomo o libro, cuando la unidad está encuadernada.", "Ubica la unidad en series encuadernadas "
                 "(actas, libros de registro).", "Sustituye a caja y carpeta en material encuadernado.", "Tomo 2"),
    "otra_unidad": Guia("Otra unidad de conservación (rollo, plano, legajo).",
                        "Registra la ubicación cuando no es caja, carpeta ni tomo.", "Completa la ubicación física.",
                        "Planoteca 4, gaveta 2"),
    "soporte": Guia("El material en que está fijado el contenido (papel, fotografía, digital…).",
                    "Determina cómo se conserva y se consulta; es obligatorio en el FUID y en el Esquema del AGN.",
                    "Cada instanciación (el original y cada copia digital) tiene su propio soporte.", "Papel"),
    "frecuencia_consulta": Guia("Qué tanto se consulta la unidad (alta, media, baja), según el FUID.",
                                "Orienta prioridades de digitalización y de conservación.",
                                "Se usa en el inventario documental (FUID).", "Media"),
    "historia_archivistica": Guia(
        "Cómo llegó la unidad a su custodio actual: cambios de custodia, transferencias, intervenciones.",
        "Sostiene la autenticidad: una cadena de custodia sin vacíos es evidencia de que el documento es lo que dice ser.",
        "Se complementa con la relación Custodio (con sus fechas) y con los hitos del productor.",
        "Transferido del archivo central en 1995; intervenido por humedad en 2003."),
    "forma_ingreso": Guia("Cómo ingresó la unidad al archivo: transferencia, donación, compra, comodato.",
                          "Prueba la legitimidad de la custodia y explica qué derechos tiene la institución.",
                          "Se relaciona con la historia archivística y con el custodio anterior.",
                          "Transferencia secundaria de 1995"),
    "alcance_contenido": Guia(
        "De qué trata la unidad: asuntos, personas, lugares y actividades que documenta.",
        "Es la base de la búsqueda por contenido y lo que permite decidir si un documento sirve a quien investiga.",
        "Lo que nombra aquí debería estar también como entidades relacionadas (Productor, Mencionado, Materia, Lugar "
        "del que trata, Actividad documentada): así se encuentra por el grafo, no solo por el texto.",
        "La Alcaldía informa al Concejo los permisos concedidos para las fiestas de San Juan."),
    "valoracion": Guia("La valoración, selección y eliminación aplicadas, según la TRD.",
                       "Explica por qué se conserva (o no) la unidad y deja constancia de la decisión.",
                       "Se relaciona con la regla de retención de la TRD que regula la serie (relación Regla de retención).",
                       "Conservación total según TRD, serie 110.2."),
    "nuevos_ingresos": Guia("Si se esperan más documentos para la unidad (fondo o serie abiertos).",
                            "Dice a quien consulta si la descripción está completa o crecerá.",
                            "Aplica a agrupaciones (fondo, serie), no a un documento.", "Se esperan transferencias anuales."),
    "organizacion": Guia("Cómo está ordenada la unidad (cronológica, alfabética, numérica).",
                         "Respeta el orden original y explica cómo buscar dentro de la agrupación.",
                         "Aplica a agrupaciones; se refleja en la secuencia entre documentos.", "Orden cronológico."),
    "forma_documental_id": Guia(
        "El tipo documental: oficio, acta, resolución, carta…",
        "La forma dice qué función cumplió el documento y orienta su lectura (diplomática). Es obligatoria en el AGN.",
        "Sale del vocabulario controlado del fondo (formas documentales) y se exporta con rico:hasDocumentaryFormType.",
        "Oficio"),
    "condiciones_acceso": Guia(
        "En palabras, las condiciones para consultar la unidad.",
        "Garantiza el derecho de acceso (Ley 1712) y protege lo que la ley reserva.",
        "Acompaña a la clasificación Ley 1712 (pública, clasificada, reservada) y a datos personales.",
        "Consulta en sala; las copias requieren autorización."),
    "condiciones_uso": Guia("Las condiciones de reproducción y uso (copias, publicación).",
                            "Protege derechos de autor e imagen y orienta a quien quiere reutilizar el documento.",
                            "Va con las condiciones de acceso.", "Reproducción para fines de investigación."),
    "idiomas": Guia("Los idiomas del contenido, en código ISO 639-3.",
                    "Un código normalizado se puede buscar e intercambiar; es obligatorio en el AGN.",
                    "Se exporta con rico:hasOrHadLanguage enlazado a Lexvo.", "spa; lat"),
    "escrituras": Guia("Las escrituras (alfabetos) del contenido, en código ISO 15924.",
                       "Importa en documentos históricos con escrituras antiguas o mixtas.",
                       "Va con el idioma.", "Latn"),
    "instrumentos_descripcion": Guia("Otros instrumentos que describen la unidad (inventarios, catálogos previos).",
                                     "Lleva a descripciones complementarias.", "Se relaciona con el inventario FUID.",
                                     "Inventario de 1995 del archivo central."),
    "localizacion_originales": Guia("Dónde está el original, si lo que se describe es una copia.",
                                    "Evita tomar una copia por el original y lleva a la fuente.",
                                    "En RICORA el original físico es una instanciación del mismo documento.",
                                    "Archivo General de la Nación, fondo Gobernaciones."),
    "localizacion_copias": Guia("Dónde hay copias de la unidad.", "Ofrece alternativas de consulta.",
                                "Cada copia digital es una instanciación.", "Copia en microfilme, rollo 12."),
    "unidades_relacionadas": Guia("Otras unidades relacionadas, en este u otros archivos.",
                                  "Reconstruye el contexto cuando los documentos de un mismo asunto están dispersos.",
                                  "Las relacionadas dentro del sistema se unen en el grafo (secuencia, inclusión).",
                                  "Respuesta del Concejo, serie Correspondencia, 1948."),
    "nota_publicaciones": Guia("Publicaciones que usan o reproducen la unidad.", "Muestra su uso y su valor secundario.",
                               "Ninguna relación del grafo: es una nota.", "Citado en Historia de Tunja (1980)."),
    "nota": Guia("Información que no cabe en otro campo.", "Evita perder datos útiles.",
                 "Úsela poco: si el dato tiene campo propio o es una entidad, va allí.", "El folio 3 está mutilado."),
    "nota_archivero": Guia("Quién hizo la descripción, con qué fuentes.", "Da transparencia y responsabilidad sobre la "
                           "descripción.", "El sistema ya registra autor y fecha de cada versión.",
                           "Descripción revisada con el inventario de 1995."),
    "reglas_descripcion": Guia("Las normas aplicadas al describir (ISAD(G), NTC 4095, RiC-CM).",
                               "Permite interpretar e intercambiar la descripción.", "Es metadato de la descripción.",
                               "ISAD(G), RiC-CM 1.0"),
    "datos_personales": Guia(
        "Si la unidad contiene datos personales, sensibles o de menores (Ley 1581 de 2012).",
        "Protege a las personas: lo que tiene datos sensibles no sale en la consulta pública sin control.",
        "Condiciona la clasificación Ley 1712 y lo que muestra la ficha pública.", "Contiene datos sensibles"),
    "nota_accesibilidad": Guia("Una versión del contenido en lenguaje claro o accesible (Ley 1680 de 2013).",
                               "Hace el patrimonio accesible a personas con discapacidad visual o cognitiva.",
                               "Sale en la ficha pública.", "Carta del alcalde que pide permiso para las fiestas."),
}

ENTIDADES: dict[str, Guia] = {
    "agente": Guia(
        "Quien actúa: una persona, una entidad, un cargo, un grupo, una familia o un programa (mecanismo).",
        "Es el contexto de producción: sin productor no hay procedencia.",
        "Se une al documento con su papel (Productor, Remitente, Destinatario, Mencionado, Custodio) y a otros agentes "
        "(subordinación, sucesión, cargo). Se reutiliza en todos los documentos que lo nombran."),
    "lugar": Guia("Un lugar: país, departamento, municipio, edificio.",
                  "Ubica los hechos y permite buscar por territorio.",
                  "Lugar del que trata el documento o Lugar de expedición; puede estar dentro de otro lugar."),
    "fecha": Guia("Una fecha del documento (creación) en forma normalizada EDTF.",
                  "Permite ordenar y buscar por tiempo sin inventar precisión.",
                  "Fecha de creación del documento; también periodo de una actividad o expedición de una norma."),
    "actividad": Guia("Lo que se hizo y quedó documentado: el trámite o la acción concreta y fechada.",
                      "Une el documento con la función que lo produjo: es lo que hace relacional a RiC.",
                      "El documento documenta la actividad; un agente la ejerce; una norma la regula; tiene un tipo."),
    "tipo_actividad": Guia("La función o competencia (valor controlado) de la que la actividad es un caso.",
                           "Agrupa actividades por función, como en la TRD.",
                           "Se asigna a una actividad; puede tener funciones superiores (SKOS)."),
    "mandato": Guia("La norma que regula una actividad o que se cita (ley, decreto, ordenanza, acuerdo, resolución).",
                    "Explica por qué se produjo el documento y con qué autoridad.",
                    "Regula una actividad y autoriza al agente que la ejerce; o es Norma citada."),
    "forma_documental": Guia("El tipo documental (oficio, acta, resolución).",
                             "Dice qué función cumplió el documento.", "Un documento tiene a lo sumo una."),
    "materia": Guia(
        "El tema del documento, normalizado con un tesauro (UNESCO, ambiental de Minambiente u otro).",
        "Un término normalizado reúne en la búsqueda y en el grafo todos los documentos sobre lo mismo, aunque cada "
        "persona lo escriba distinto; es «Palabras clave o temas» del FUID.",
        "Relación Materia (rico:hasOrHadSubject) con el documento; enlace skos:exactMatch al concepto del tesauro."),
}


def _agn_por_campo() -> dict[str, list[dict]]:
    """Filas del Esquema del AGN por campo del sistema: una fila cubre todos
    los campos que nombra (la de volumen documental, folios, caja y carpeta)."""
    import re

    from app.servicios import atributos as catalogo
    from app.servicios.perfil_agn import CATALOGO

    claves = {a.clave for a in catalogo.ATRIBUTOS}
    salida: dict[str, list[dict]] = {}
    for fila in CATALOGO:
        for clave in dict.fromkeys(t for t in re.findall(r"[a-z_]+", fila.campo) if t in claves):
            salida.setdefault(clave, []).append({"id": fila.id, "elemento": fila.elemento,
                                                 "obligatoriedad": fila.obligatoriedad, "codigo_agn": fila.codigo_agn})
    return salida


def atributos() -> list[dict]:
    """Cada atributo del catálogo con su guía y sus referencias normativas."""
    from app.servicios import atributos as catalogo

    agn = _agn_por_campo()
    salida = []
    for a in catalogo.ATRIBUTOS:
        g = ATRIBUTOS[a.clave]
        salida.append({"clave": a.clave, "etiqueta": a.etiqueta, "isad": a.isad, "rico": a.rico,
                       "cardinalidad": f"{a.minimo}..{'n' if a.maximo > 1 else a.maximo}",
                       "obligatorio": a.minimo > 0, "que_es": g.que_es, "por_que": g.por_que,
                       "se_relaciona": g.se_relaciona, "ejemplo": g.ejemplo, "agn": agn.get(a.clave, [])})
    return salida


def entidades() -> list[dict]:
    from app.servicios import ric_o

    return [{"tipo": t, "rico": f"rico:{ric_o.CLASE_VOCABULARIO.get(t) or ('Date' if t == 'fecha' else 'Agent')}",
             "que_es": g.que_es, "por_que": g.por_que, "se_relaciona": g.se_relaciona, "ejemplo": g.ejemplo}
            for t, g in ENTIDADES.items()]
