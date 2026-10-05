"""versiones de cada descripción (brecha RF-RIC-001)

- versiones_descripcion: una fila por versión numerada, con la instantánea
  de los atributos y del contexto, quién, cuándo y por qué. No se modifica
  ni se borra (disparador). Su huella SHA-256 la calcula la base sobre la
  forma canónica del JSON (jsonb::text), para verificarla siempre igual.
- Las descripciones ya publicadas reciben su versión 1, «estado inicial»,
  con sus atributos actuales (el contexto anterior no se conoce).

Revision ID: 0037
Revises: 0036

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0037'
down_revision: Union[str, None] = '0036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Copia de app/servicios/atributos.py al momento de esta migración (atributos
# y sus columnas de procedencia): una migración no depende del código vivo.
COLUMNAS = (
    "titulo", "codigo_referencia", "fechas_extremas", "fechas_extremas_edtf", "folios", "caja", "carpeta", "tomo",
    "otra_unidad", "soporte", "frecuencia_consulta", "historia_archivistica", "forma_ingreso", "alcance_contenido",
    "valoracion", "nuevos_ingresos", "organizacion", "forma_documental_id", "condiciones_acceso", "condiciones_uso",
    "idiomas", "escrituras", "instrumentos_descripcion", "localizacion_originales", "localizacion_copias",
    "unidades_relacionadas", "nota_publicaciones", "nota", "nota_archivero", "reglas_descripcion", "datos_personales",
    "nota_accesibilidad", "origen_titulo", "origen_historia_archivistica", "origen_alcance", "confianza_alcance",
    "origen_idiomas", "confianza_idiomas",
)


def upgrade() -> None:
    op.create_table(
        'versiones_descripcion',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('recurso_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('recursos_documentales.id'),
                  nullable=False, index=True),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.String(30), nullable=False),
        sa.Column('restaurada_de', sa.Integer(), nullable=True),
        sa.Column('autor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('contenido', postgresql.JSONB(), nullable=False),
        sa.Column('huella', sa.String(64), nullable=False),
        sa.UniqueConstraint('recurso_id', 'numero', name='uq_version_descripcion_numero'),
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION public.version_descripcion_sellar() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            NEW.huella := encode(sha256(convert_to(NEW.contenido::text, 'UTF8')), 'hex');
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'Una versión de la descripción no se modifica ni se borra: restaurar crea una versión nueva.';
        END $$""")
    op.execute("""CREATE TRIGGER versiones_descripcion_selladas BEFORE INSERT OR UPDATE OR DELETE ON versiones_descripcion
                  FOR EACH ROW EXECUTE FUNCTION public.version_descripcion_sellar()""")
    pares = ", ".join(f"'{c}', r.{c}" for c in COLUMNAS)
    op.execute(f"""
        INSERT INTO versiones_descripcion (id, recurso_id, numero, motivo, autor_id, creada_en, contenido, huella)
        SELECT gen_random_uuid(), r.id, 1, 'estado_inicial', r.publicado_por_id,
               coalesce(r.actualizado_en, r.publicado_en, r.creado_en),
               jsonb_build_object('atributos', jsonb_build_object({pares}), 'contexto', NULL), ''
        FROM recursos_documentales r
        WHERE r.publicado_en IS NOT NULL""")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS versiones_descripcion_selladas ON versiones_descripcion")
    op.drop_table('versiones_descripcion')
    op.execute("DROP FUNCTION IF EXISTS public.version_descripcion_sellar()")
