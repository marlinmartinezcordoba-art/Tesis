"""auditoría v7: hallazgos de conformidad con RiC (sembrados con su estado
real a la fecha) y etiquetas legibles de las versiones de la instrucción

Revision ID: 0014
Revises: 0013

"""
import uuid
from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HOY = date(2026, 10, 3)

# Los diez hallazgos de la revisión de conformidad (prompt de auditoría v7,
# §12) y cuatro más que encontró la depuración de esta misma ronda. Cada uno
# con el estado que de verdad tiene hoy, no con uno optimista.
# (título, descripción, componentes, estado, abierto_en, cerrado_en, acción)
HALLAZGOS = [
    ("Punto de acceso dereferenciable y exportación RDF inconsultables sin sesión",
     "La exportación RDF y la resolución de URI exigían iniciar sesión: desde fuera del sistema no se podía "
     "consultar ningún dato en RiC-O.",
     ["instrumentos"], "en_correccion", date(2026, 10, 2), None,
     "Construido y probado (commit 3765cd5): exportación del fondo en Turtle y JSON-LD; URI /id/{uuid} con "
     "negociación de contenido; conformidad verificada contra el OWL oficial de RiC-O 1.1 y un perfil SHACL. La "
     "resolución sin sesión funciona y tiene prueba automática, pero en el servidor está apagada a propósito: el "
     "servidor todavía no tiene HTTPS y el fondo puede tener reservas sin declarar. Falta: encenderla en "
     "producción con HTTPS y dejar la evidencia de una URI resuelta sin sesión iniciada."),
    ("No se registraba la confianza del reconocimiento óptico de caracteres",
     "El texto obtenido por OCR entraba a la descripción sin ninguna medida de su calidad.",
     ["ingesta", "descripcion"], "cerrado", date(2026, 10, 2), date(2026, 10, 3),
     "Commit 5cac380 (migración 0010): confianza media por documento desde Tesseract, umbral configurable (70 "
     "por defecto), alerta «OCR de baja confianza» en el panel central y aviso en el espacio de descripción."),
    ("El motor de análisis desconocía el vocabulario del fondo",
     "El motor proponía entidades sin saber cuáles ya existían, y creaba variantes de lo ya registrado.",
     ["descripcion", "vocabularios"], "cerrado", date(2026, 10, 2), date(2026, 10, 3),
     "Commit 629f203: antes de proponer, el motor recibe las entidades del fondo parecidas al texto (pg_trgm, "
     "diez por tipo desde 0,5 de similitud) y puede referirse a una existente por su código. La instrucción "
     "cambió de versión (3c5a7af7) y así queda en cada decisión."),
    ("Cobertura parcial del catálogo de relaciones de RiC-CM",
     "El sistema implementa un subconjunto de las 85 relaciones oficiales de RiC-CM 1.0.",
     ["descripcion", "vocabularios", "instrumentos"], "en_correccion", date(2026, 10, 2), None,
     "Medido el 3 de octubre de 2026: 25 de los 85 códigos de relación de RiC-CM 1.0 (29 %), más dos propiedades "
     "propias de RiC-O (hasActivityType, hasDirectSubevent). Las 27 están verificadas contra el OWL y se exportan. "
     "Se ampliaron en esta ronda: custodia (R039i), secuencia (R008), parte constitutiva (R003), jerarquía de "
     "lugares (R007), hito (R059), expedición del mandato (R065). Para cerrarlo hay que decidir si la cobertura "
     "parcial se declara delimitación de la tesis (decisión de la autora) o se amplía."),
    ("Ficha de agente incompleta según ISAAR-CPF en la instancia real",
     "Sin historia, sin fechas de existencia, sin identificadores y sin relaciones entre agentes ni sucesión.",
     ["vocabularios"], "cerrado", date(2026, 10, 2), date(2026, 10, 3),
     "Commit 69fc720: las cuatro áreas de ISAAR-CPF; existencia en EDTF; identificadores con su esquema "
     "(interno, VIAF, Wikidata, ISNI); relaciones jerárquica (R045), temporal (R016) y asociativa (R044, "
     "isAgentAssociatedWithAgent, verificada contra el OWL)."),
    ("Faltaban tipo de actividad, mandato y sub-actividades en la instancia real",
     "No se podía decir que un documento se produjo para cumplir una función ni con qué norma.",
     ["descripcion", "vocabularios"], "cerrado", date(2026, 10, 2), date(2026, 10, 3),
     "Commit f9e1aae (módulo 2 v2): documento → actividad (documents), tipo de actividad, agente que la ejerce y "
     "mandato que la regula (R063). Commit 629f203: sub-actividades (hasDirectSubevent). Árbol de funciones SKOS en "
     "el commit 69fc720."),
    ("Solo había fechas exactas: sin rangos, aproximadas ni inciertas",
     "Una fecha histórica imprecisa se perdía o se inventaba.",
     ["descripcion"], "cerrado", date(2026, 10, 2), date(2026, 10, 3),
     "Commit f9e1aae: fechas en EDTF con sus tres subtipos (simple con calificador, rango con extremos abiertos, "
     "conjunto). Se exportan con normalizedDateValue y dateQualifier (commit 3765cd5)."),
    ("Sin paquete OAIS, metadatos PREMIS, segunda copia ni plan de preservación",
     "La preservación no producía evidencia exportable ni tenía respaldo verificado.",
     ["preservacion"], "en_correccion", date(2026, 10, 2), None,
     "Capacidad técnica construida: AIP en BagIt con PREMIS 3.0 validado contra el XSD oficial en la integración "
     "continua (commits 40ea1e6 y 016116d), segunda copia verificada aparte, agentes mecanismo con versión (commit "
     "497eff8) y un AIP real como anexo. Falta: (a) que la autora confirme y complete el fundamento normativo "
     "colombiano que el plan deja señalado; (b) en esta versión la segunda copia comparte el disco del servidor."),
    ("Cobertura incompleta entidad por entidad frente a RiC-CM",
     "Parte documental, agente grupo, identificador externo, mecanismo con versión, línea de tiempo del agente, "
     "vínculo función–serie, mandato que crea, calificador y calendario de la fecha, ficha de lugar ampliada.",
     ["descripcion", "vocabularios", "preservacion"], "cerrado", date(2026, 10, 2), date(2026, 10, 3),
     "Todo implementado (commits 69fc720, 629f203 y 497eff8) y cada nombre verificado contra el OWL de RiC-O 1.1 "
     "(commit 5cac380, anexo verificacion-ric-o-1-1.md). El calendario no gregoriano no tiene propiedad en RiC-O: "
     "se guarda y no se exporta, declarado como delimitación."),
    ("Faltaban secuencia, custodia, jerarquía normativa, idioma y condiciones",
     "Relaciones de secuencia y de custodia, norma superior de un mandato; idioma, condiciones de acceso y de uso.",
     ["descripcion", "vocabularios"], "cerrado", date(2026, 10, 2), date(2026, 10, 3),
     "Commits 5cac380 y 629f203: R008 precedesOrPreceded, R039i hasOrHadHolder, R063 con rol de jerarquía "
     "normativa, hasOrHadLanguage (ISO 639-3), conditionsOfAccess (A08) y conditionsOfUse (A09). Se exportan "
     "desde el commit 3765cd5."),
    ("El mecanismo del vocabulario existía pero ningún módulo lo usaba",
     "Ghostscript, Siegfried y el motor quedaban como texto libre en preservación y en descripción, aunque el "
     "servicio de vocabularios ya podía registrarlos como agentes mecanismo con su versión.",
     ["preservacion", "descripcion", "vocabularios"], "cerrado", date(2026, 10, 3), date(2026, 10, 3),
     "Encontrado al revisar preservación. Commit 497eff8 (migración 0013): cada acción técnica apunta a su "
     "mecanismo; en PREMIS el agente lleva el identificador del vocabulario y agentVersion."),
    ("Código RiC-CM equivocado para rico:title",
     "El mapeo anotaba rico:title como RiC-A40; en RiC-CM 1.0, A40 es Structure.",
     ["instrumentos"], "cerrado", date(2026, 10, 3), date(2026, 10, 3),
     "Encontrado al validar la exportación. Commit 3765cd5: title ↔ RiC-A28 (Name), como dice el OWL; la "
     "verificación automática compara ahora el código de cada atributo con el OWL."),
    ("Tipo de mandato con la propiedad genérica",
     "Se usaba hasOrHadRuleType cuando RiC-O 1.1 tiene la más específica hasOrHadMandateType.",
     ["instrumentos", "vocabularios"], "cerrado", date(2026, 10, 3), date(2026, 10, 3),
     "Encontrado al revisar el OWL para la exportación. Commit 3765cd5: hasOrHadMandateType → MandateType."),
    ("El índice de términos habría listado los programas del sistema",
     "Al conectar los mecanismos, el motor, Siegfried y Ghostscript aparecían como agentes del fondo en el índice.",
     ["instrumentos"], "cerrado", date(2026, 10, 3), date(2026, 10, 3),
     "Encontrado por una prueba que dejó de pasar. Commit 497eff8: el índice excluye los mecanismos; siguen "
     "administrándose en Vocabularios."),
]


def upgrade() -> None:
    estado = postgresql.ENUM('abierto', 'en_correccion', 'cerrado', name='estado_hallazgo')
    estado.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'hallazgos_conformidad',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('numero', sa.Integer(), nullable=False, unique=True),
        sa.Column('titulo', sa.String(length=300), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('componentes', postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column('estado', postgresql.ENUM(name='estado_hallazgo', create_type=False), nullable=False),
        sa.Column('abierto_en', sa.Date(), nullable=False),
        sa.Column('cerrado_en', sa.Date(), nullable=True),
        sa.Column('accion', sa.Text(), nullable=True),
        sa.Column('creado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("(estado = 'cerrado') = (cerrado_en IS NOT NULL)", name='ck_hallazgo_cierre'),
    )
    op.create_index('ix_hallazgos_conformidad_estado', 'hallazgos_conformidad', ['estado'])
    op.create_table(
        'etiquetas_version_prompt',
        sa.Column('version', sa.String(length=16), primary_key=True),
        sa.Column('etiqueta', sa.String(length=40), nullable=False, unique=True),
        sa.Column('nota', sa.String(length=300), nullable=True),
        sa.Column('asignada_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('asignada_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Siembra: cada hallazgo, con su evento de creación en la auditoría.
    tabla = sa.table('hallazgos_conformidad', *[sa.column(c) for c in (
        'id', 'numero', 'titulo', 'descripcion', 'componentes', 'estado', 'abierto_en', 'cerrado_en', 'accion')])
    auditoria = sa.table('registro_auditoria', sa.column('fecha', sa.DateTime(timezone=True)),
                         *[sa.column(c, sa.String()) for c in ('modulo', 'accion', 'entidad_tipo', 'entidad_id', 'detalle')],
                         sa.column('valor_nuevo', postgresql.JSONB()))
    for numero, (titulo, descripcion, componentes, est, abierto, cerrado, accion) in enumerate(HALLAZGOS, start=1):
        ident = uuid.uuid4()
        op.execute(tabla.insert().values(id=ident, numero=numero, titulo=titulo, descripcion=descripcion,
                                         componentes=componentes, estado=est, abierto_en=abierto, cerrado_en=cerrado,
                                         accion=accion))
        op.execute(auditoria.insert().values(
            fecha=sa.func.now(), modulo='auditoria', accion='hallazgo_creado', entidad_tipo='hallazgo',
            entidad_id=str(ident),
            valor_nuevo={"numero": numero, "titulo": titulo, "estado": est, "componentes": componentes},
            detalle=f"Hallazgo {numero}, registrado al desplegar la versión 7 del módulo de auditoría con su estado "
                    f"real al {HOY.isoformat()}"))


def downgrade() -> None:
    op.drop_table('etiquetas_version_prompt')
    op.drop_index('ix_hallazgos_conformidad_estado', table_name='hallazgos_conformidad')
    op.drop_table('hallazgos_conformidad')
    postgresql.ENUM(name='estado_hallazgo').drop(op.get_bind(), checkfirst=True)
    # Los eventos de auditoría de la siembra no se borran: el registro es de solo anexar.
