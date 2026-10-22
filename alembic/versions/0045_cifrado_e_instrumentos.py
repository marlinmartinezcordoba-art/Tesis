"""clave del segundo factor cifrada e instrumentos de descripción aprobados

- usuarios.mfa_secreto pasa a guardar la clave cifrada (AES-256-GCM, atada a la
  cuenta; app/core/cifrado.py) y se cifran las que había en claro.
- instrumentos_aprobados: el FUID, la guía y el índice aprobados como
  documentos fijos con su huella, acta y responsable.

Revision ID: 0045
Revises: 0044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0045'
down_revision: Union[str, None] = '0044'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.core import doble_factor

    op.alter_column("usuarios", "mfa_secreto", type_=sa.String(200), existing_nullable=True)
    doble_factor.cifrar_en_claro(op.get_bind())

    op.create_table(
        "instrumentos_aprobados",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fondo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recursos_documentales.id"), nullable=False),
        sa.Column("recurso_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recursos_documentales.id"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("ruta", sa.String(500), nullable=False),
        sa.Column("formato_mime", sa.String(200), nullable=False),
        sa.Column("tamano_bytes", sa.BigInteger(), nullable=False),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("acta", sa.String(200), nullable=True),
        sa.Column("fecha_acta", sa.Date(), nullable=True),
        sa.Column("aprobado_por_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("aprobado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="vigente"),
        sa.Column("reemplaza_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("instrumentos_aprobados.id"), nullable=True),
        sa.Column("motivo_anulacion", sa.Text(), nullable=True),
        sa.Column("anulado_por_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("anulado_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_instrumentos_aprobados_fondo_id", "instrumentos_aprobados", ["fondo_id"])
    op.create_index("ix_instrumentos_aprobados_recurso_id", "instrumentos_aprobados", ["recurso_id"])
    # Una sola versión vigente por tipo y nivel.
    op.create_index("uq_instrumento_vigente", "instrumentos_aprobados", ["tipo", "recurso_id"], unique=True,
                    postgresql_where=sa.text("estado = 'vigente'"))


def downgrade() -> None:
    op.drop_table("instrumentos_aprobados")
    # La clave del segundo factor queda cifrada: volver a guardarla en claro sería
    # deshacer una medida de seguridad. Quien baje la versión debe restablecer el
    # segundo factor de las cuentas.
