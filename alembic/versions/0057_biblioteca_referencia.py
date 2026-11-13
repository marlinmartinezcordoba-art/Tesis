"""biblioteca de referencia del asistente (RAG): leyes, acuerdos, manuales

El Asistente RICORA responde con los documentos de la entidad y su normativa: recupera los
pasajes pertinentes con el mismo índice en español y sin tildes del buscador (migración 0035)
y responde solo con ellos, citándolos.

Revision ID: 0057
Revises: 0056

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0057'
down_revision: Union[str, None] = '0056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'documentos_referencia',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('titulo', sa.String(300), nullable=False),
        sa.Column('clase', sa.String(30), nullable=False, server_default='otro'),
        sa.Column('nombre_original', sa.String(255), nullable=False),
        sa.Column('ruta', sa.String(500), nullable=False),
        sa.Column('huella', sa.String(64), nullable=False),
        sa.Column('tamano_bytes', sa.Integer(), nullable=False),
        sa.Column('formato_mime', sa.String(120), nullable=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='procesando'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('texto', sa.Text(), nullable=True),
        sa.Column('origen_texto', sa.String(20), nullable=True),
        sa.Column('paginas', sa.Integer(), nullable=True),
        sa.Column('busqueda', postgresql.TSVECTOR(), nullable=True),
        sa.Column('cargado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('cargado_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('procesado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('anulado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('anulado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('motivo_anulacion', sa.Text(), nullable=True),
        sa.CheckConstraint("estado IN ('procesando', 'listo', 'error', 'anulado')", name='ck_referencia_estado'),
        sa.CheckConstraint("clase IN ('ley', 'decreto', 'acuerdo_agn', 'manual', 'procedimiento', 'otro')",
                           name='ck_referencia_clase'),
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION public.ricora_indexar_referencia() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          NEW.busqueda := pg_catalog.setweight(public.ricora_tsv(NEW.titulo), 'A') || public.ricora_tsv(NEW.texto);
          RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER referencia_indexar BEFORE INSERT OR UPDATE OF titulo, texto
                  ON documentos_referencia FOR EACH ROW EXECUTE FUNCTION public.ricora_indexar_referencia()""")
    op.execute("CREATE INDEX ix_referencia_busqueda ON documentos_referencia USING gin (busqueda)")
    op.create_index('ix_referencia_estado', 'documentos_referencia', ['estado'])


def downgrade() -> None:
    op.drop_index('ix_referencia_estado', table_name='documentos_referencia')
    op.execute("DROP INDEX IF EXISTS ix_referencia_busqueda")
    op.execute("DROP TRIGGER IF EXISTS referencia_indexar ON documentos_referencia")
    op.execute("DROP FUNCTION IF EXISTS public.ricora_indexar_referencia()")
    op.drop_table('documentos_referencia')
