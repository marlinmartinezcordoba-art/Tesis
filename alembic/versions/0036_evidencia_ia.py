"""evidencia de la IA (brechas RF-AI-002 y RF-OCR-001): la propuesta del
motor como registro propio e inalterable, y la página y la zona de cada
fragmento citado

- propuestas_ia: cada vez que el motor propone (al describir o en la
  evaluación ciega) queda una fila con el modelo y su versión, la versión
  de la instrucción, los parámetros, lo que se le envió (con la huella de
  cada texto), la respuesta tal como llegó, la propuesta ya controlada, la
  hora y la duración, y su estado (generada, publicada, cancelada,
  expirada). El contenido no se puede cambiar ni borrar: lo impide la base
  de datos. Solo cambia el estado.
- paginas_texto: el texto extraído de cada archivo, partido por páginas,
  con las líneas del OCR y su caja (en fracciones de la página).
- relaciones: la página y la zona del fragmento citado, y de qué propuesta
  salió la relación.

Revision ID: 0036
Revises: 0035

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0036'
down_revision: Union[str, None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'propuestas_ia',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('origen', sa.String(20), nullable=False),  # descripcion | evaluacion
        sa.Column('fondo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('recursos_documentales.id'), nullable=False, index=True),
        sa.Column('trabajo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('trabajos_descripcion.id'), nullable=True, index=True),
        sa.Column('evaluacion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluaciones.id'), nullable=True, index=True),
        sa.Column('solicitada_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('nivel', sa.String(40), nullable=False),
        sa.Column('instanciaciones', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column('motor', sa.String(120), nullable=True),
        sa.Column('version_modelo', sa.String(120), nullable=True),
        sa.Column('version_prompt', sa.String(20), nullable=True),
        sa.Column('parametros', postgresql.JSONB(), nullable=False),
        sa.Column('entrada', postgresql.JSONB(), nullable=False),
        sa.Column('respuesta', postgresql.JSONB(), nullable=True),
        sa.Column('contenido', postgresql.JSONB(), nullable=False),
        sa.Column('huella', sa.String(64), nullable=False),
        sa.Column('disponible', sa.Boolean(), nullable=False),
        sa.Column('aviso', sa.Text(), nullable=True),
        sa.Column('entidades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confianza_media', sa.Float(), nullable=True),
        sa.Column('generada_en', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('duracion_ms', sa.Integer(), nullable=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='generada', index=True),
        sa.Column('estado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('recurso_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('recursos_documentales.id'), nullable=True, index=True),
    )
    # Lo que la propuesta dijo no cambia nunca; solo su estado (y a qué
    # descripción llegó). Tampoco se borra.
    op.execute("""
        CREATE OR REPLACE FUNCTION public.propuesta_ia_inalterable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Una propuesta del motor no se puede borrar: es evidencia.';
          END IF;
          IF (NEW.origen, NEW.fondo_id, NEW.trabajo_id, NEW.evaluacion_id, NEW.solicitada_por_id, NEW.nivel,
              NEW.instanciaciones, NEW.motor, NEW.version_modelo, NEW.version_prompt, NEW.parametros, NEW.entrada,
              NEW.respuesta, NEW.contenido, NEW.huella, NEW.disponible, NEW.aviso, NEW.generada_en, NEW.duracion_ms)
             IS DISTINCT FROM
             (OLD.origen, OLD.fondo_id, OLD.trabajo_id, OLD.evaluacion_id, OLD.solicitada_por_id, OLD.nivel,
              OLD.instanciaciones, OLD.motor, OLD.version_modelo, OLD.version_prompt, OLD.parametros, OLD.entrada,
              OLD.respuesta, OLD.contenido, OLD.huella, OLD.disponible, OLD.aviso, OLD.generada_en, OLD.duracion_ms) THEN
            RAISE EXCEPTION 'Lo que propuso el motor no se puede modificar: es evidencia. Solo cambia su estado.';
          END IF;
          RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER propuestas_ia_inalterables BEFORE UPDATE OR DELETE ON propuestas_ia
                  FOR EACH ROW EXECUTE FUNCTION public.propuesta_ia_inalterable()""")

    op.add_column('trabajos_descripcion', sa.Column(
        'propuesta_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('propuestas_ia.id'), nullable=True))
    op.add_column('evaluacion_documentos', sa.Column(
        'propuesta_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('propuestas_ia.id'), nullable=True))

    op.create_table(
        'paginas_texto',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('instanciacion_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('instanciaciones.id', ondelete='CASCADE'), nullable=False),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('inicio', sa.Integer(), nullable=False),
        sa.Column('fin', sa.Integer(), nullable=False),
        sa.Column('origen', sa.String(20), nullable=False),  # ocr | capa_de_texto
        sa.Column('ancho_px', sa.Integer(), nullable=True),
        sa.Column('alto_px', sa.Integer(), nullable=True),
        sa.Column('confianza', sa.Float(), nullable=True),
        sa.Column('lineas', postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint('instanciacion_id', 'numero', name='uq_paginas_texto_numero'),
    )
    op.create_index('ix_paginas_texto_inst_inicio', 'paginas_texto', ['instanciacion_id', 'inicio'])

    op.add_column('relaciones', sa.Column('fragmento_pagina', sa.Integer(), nullable=True))
    op.add_column('relaciones', sa.Column('fragmento_zona', postgresql.JSONB(), nullable=True))
    op.add_column('relaciones', sa.Column(
        'propuesta_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('propuestas_ia.id'), nullable=True))
    op.create_index('ix_relaciones_propuesta', 'relaciones', ['propuesta_id'])


def downgrade() -> None:
    op.drop_index('ix_relaciones_propuesta', table_name='relaciones')
    for c in ('propuesta_id', 'fragmento_zona', 'fragmento_pagina'):
        op.drop_column('relaciones', c)
    op.drop_index('ix_paginas_texto_inst_inicio', table_name='paginas_texto')
    op.drop_table('paginas_texto')
    op.drop_column('evaluacion_documentos', 'propuesta_id')
    op.drop_column('trabajos_descripcion', 'propuesta_id')
    op.execute("DROP TRIGGER IF EXISTS propuestas_ia_inalterables ON propuestas_ia")
    op.drop_table('propuestas_ia')
    op.execute("DROP FUNCTION IF EXISTS public.propuesta_ia_inalterable()")
