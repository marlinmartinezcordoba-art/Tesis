"""buscador de texto completo (brechas RF-SEARCH-001 y RF-SEARCH-002):
índice en español, sin tildes, sobre la descripción ISAD(G) y el texto de
cada archivo (OCR o capa de texto)

- Configuración `ricora_es`: la del español de PostgreSQL con `unaccent`
  delante, para que «Medellin» encuentre «Medellín» y los fragmentos de
  resultado conserven las tildes originales.
- `ricora_tsv(texto)`: el índice de un texto. Si un OCR es tan largo que no
  cabe en un índice (límite de 1 MB de PostgreSQL), se indexa recortado en
  vez de fallar: un error aquí detendría la ingesta.
- Columnas `busqueda` en recursos_documentales e instanciaciones, que llenan
  disparadores (no columnas generadas: estas se recalcularían en cada
  cambio de progreso de la ingesta, con OCR de cientos de páginas).

Revision ID: 0035
Revises: 0034

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0035'
down_revision: Union[str, None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Peso A: título y código de referencia; B: alcance y contenido; C: el resto
# de la descripción ISAD(G) que escribe una persona.
CAMPOS_C = ("fechas_extremas", "nota", "historia_archivistica", "forma_ingreso", "valoracion", "nuevos_ingresos",
            "organizacion", "condiciones_acceso", "condiciones_uso", "instrumentos_descripcion",
            "localizacion_originales", "localizacion_copias", "unidades_relacionadas", "nota_publicaciones",
            "nota_accesibilidad", "caja", "carpeta", "tomo", "otra_unidad")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'ricora_es') THEN
            CREATE TEXT SEARCH CONFIGURATION public.ricora_es (COPY = pg_catalog.spanish);
            ALTER TEXT SEARCH CONFIGURATION public.ricora_es
              ALTER MAPPING FOR hword, hword_part, word WITH public.unaccent, pg_catalog.spanish_stem;
          END IF;
        END $$""")
    op.execute("""
        CREATE OR REPLACE FUNCTION public.ricora_tsv(texto text) RETURNS tsvector
        LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
        DECLARE largo integer := 1000000;
        BEGIN
          IF texto IS NULL OR texto = '' THEN RETURN ''::tsvector; END IF;
          LOOP
            BEGIN
              RETURN pg_catalog.to_tsvector('public.ricora_es'::regconfig, pg_catalog.left(texto, largo));
            EXCEPTION WHEN program_limit_exceeded THEN
              largo := largo / 2;
              IF largo < 1000 THEN RETURN ''::tsvector; END IF;
            END;
          END LOOP;
        END $$""")
    resto = " || ' ' || ".join(f"coalesce(NEW.{c}, '')" for c in CAMPOS_C)
    op.execute(f"""
        CREATE OR REPLACE FUNCTION public.ricora_indexar_recurso() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          NEW.busqueda :=
            pg_catalog.setweight(public.ricora_tsv(coalesce(NEW.titulo, '') || ' ' || coalesce(NEW.codigo_referencia, '')), 'A') ||
            pg_catalog.setweight(public.ricora_tsv(NEW.alcance_contenido), 'B') ||
            pg_catalog.setweight(public.ricora_tsv({resto}), 'C');
          RETURN NEW;
        END $$""")
    op.execute("""
        CREATE OR REPLACE FUNCTION public.ricora_indexar_instanciacion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          NEW.busqueda := public.ricora_tsv(NEW.texto_extraido);
          RETURN NEW;
        END $$""")

    op.execute("ALTER TABLE recursos_documentales ADD COLUMN busqueda tsvector")
    op.execute("ALTER TABLE instanciaciones ADD COLUMN busqueda tsvector")
    columnas = ", ".join(("titulo", "codigo_referencia", "alcance_contenido") + CAMPOS_C)
    op.execute(f"""CREATE TRIGGER recursos_indexar BEFORE INSERT OR UPDATE OF {columnas}
                   ON recursos_documentales FOR EACH ROW EXECUTE FUNCTION public.ricora_indexar_recurso()""")
    op.execute("""CREATE TRIGGER instanciaciones_indexar BEFORE INSERT OR UPDATE OF texto_extraido
                  ON instanciaciones FOR EACH ROW EXECUTE FUNCTION public.ricora_indexar_instanciacion()""")
    # Lo que ya existe se indexa ahora (el disparador corre al reescribir la columna).
    op.execute("UPDATE recursos_documentales SET titulo = titulo")
    op.execute("UPDATE instanciaciones SET texto_extraido = texto_extraido WHERE texto_extraido IS NOT NULL")
    op.execute("CREATE INDEX ix_recursos_busqueda ON recursos_documentales USING gin (busqueda)")
    op.execute("CREATE INDEX ix_instanciaciones_busqueda ON instanciaciones USING gin (busqueda)")
    # Identificadores: el código de referencia y los de las autoridades (VIAF,
    # ORCID…) se buscan también por partes, sin distinguir mayúsculas.
    op.execute("CREATE INDEX ix_recursos_codigo_trgm ON recursos_documentales USING gin (lower(codigo_referencia) gin_trgm_ops)")
    op.execute("CREATE INDEX ix_identificadores_valor_trgm ON identificadores_entidad USING gin (lower(valor) gin_trgm_ops)")
    # Los nombres de las entidades y sus otras formas ya tienen índice de
    # trigramas (migraciones 0003 y 0027).


def downgrade() -> None:
    for indice in ("ix_identificadores_valor_trgm", "ix_recursos_codigo_trgm",
                   "ix_instanciaciones_busqueda", "ix_recursos_busqueda"):
        op.execute(f"DROP INDEX IF EXISTS {indice}")
    op.execute("DROP TRIGGER IF EXISTS instanciaciones_indexar ON instanciaciones")
    op.execute("DROP TRIGGER IF EXISTS recursos_indexar ON recursos_documentales")
    op.execute("ALTER TABLE instanciaciones DROP COLUMN IF EXISTS busqueda")
    op.execute("ALTER TABLE recursos_documentales DROP COLUMN IF EXISTS busqueda")
    op.execute("DROP FUNCTION IF EXISTS public.ricora_indexar_instanciacion()")
    op.execute("DROP FUNCTION IF EXISTS public.ricora_indexar_recurso()")
    op.execute("DROP FUNCTION IF EXISTS public.ricora_tsv(text)")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS public.ricora_es")
