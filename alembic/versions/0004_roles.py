"""roles configurables

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-30 20:15:41.544134

Crea la tabla de roles con los cuatro roles base del diseño y convierte la
columna usuarios.rol (antes una lista fija) en una referencia a esa tabla,
sin perder el rol de ninguna cuenta.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRABAJO = ("ingesta", "descripcion", "vocabularios", "instrumentos", "preservacion")


def _p(ingesta="ninguno", descripcion="ninguno", vocabularios="ninguno", instrumentos="ninguno",
       preservacion="ninguno", catalogo="leer", auditoria="propia"):
    return {"ingesta": ingesta, "descripcion": descripcion, "vocabularios": vocabularios, "instrumentos": instrumentos,
            "preservacion": preservacion, "catalogo": catalogo, "auditoria": auditoria}


TODO_ESCRIBIR = dict.fromkeys(TRABAJO, "escribir")
TODO_LEER = dict.fromkeys(TRABAJO, "leer")

# Los cuatro roles base del diseño (no se modifican).
BASE = [
    ("administrador", "Administrador", "Acceso completo, gestión de usuarios, roles y configuración.",
     _p(**TODO_ESCRIBIR, auditoria="todo")),
    ("archivista", "Archivista", "Trabajo completo en ingesta, descripción, vocabularios, instrumentos y preservación.",
     _p(**TODO_ESCRIBIR)),
    ("revisor", "Revisor", "Solo consulta de los módulos de trabajo (alcance provisional).", _p(**TODO_LEER)),
    ("consulta", "Consulta", "Solo el catálogo de instrumentos, en modo lectura (usuario investigador).",
     _p(auditoria="ninguno")),
]

# Roles de referencia de los sistemas de gestión y descripción archivística
# (AtoM, ArchivesSpace, Archivematica, Modelo de requisitos SGDEA del AGN).
# Vienen creados y la administradora puede ajustarlos o desactivarlos.
REFERENCIA = [
    ("coordinador_archivo", "Coordinador de archivo",
     "Jefe o responsable del archivo: trabajo en todos los módulos y auditoría de todo el equipo, sin administrar "
     "usuarios. Equivale a «Repository manager» (ArchivesSpace) y «Editor» (AtoM).",
     _p(**TODO_ESCRIBIR, auditoria="todo")),
    ("digitalizador", "Auxiliar de digitalización e ingesta",
     "Carga y verifica los archivos (ingesta); consulta lo descrito. Equivale al rol de producción/captura del "
     "Modelo SGDEA y a «Basic data entry» (ArchivesSpace).",
     _p(ingesta="escribir", descripcion="leer")),
    ("descriptor", "Descriptor / catalogador",
     "Describe, controla autoridades y genera instrumentos; consulta la ingesta. Equivale a «Contributor» (AtoM) y "
     "«Advanced data entry» (ArchivesSpace).",
     _p(ingesta="leer", descripcion="escribir", vocabularios="escribir", instrumentos="escribir", preservacion="leer")),
    ("preservacion_digital", "Responsable de preservación digital",
     "Vigila integridad y formatos, y aprueba migraciones (funciones de Planeación de la preservación y Administración "
     "de datos de OAIS). Equivale a «Manager» (Archivematica).",
     _p(ingesta="leer", descripcion="leer", instrumentos="leer", preservacion="escribir")),
    ("auditor", "Auditor",
     "Control interno: consulta todos los módulos y la auditoría completa, sin modificar nada. Rol de auditoría del "
     "Modelo de requisitos SGDEA.",
     _p(**TODO_LEER, auditoria="todo")),
]


def upgrade() -> None:
    roles = op.create_table(
        'roles',
        sa.Column('clave', sa.String(length=40), nullable=False),
        sa.Column('nombre', sa.String(length=80), nullable=False),
        sa.Column('descripcion', sa.String(length=300), nullable=True),
        sa.Column('base', sa.Boolean(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('permisos', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('creado_por_id', sa.UUID(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], name='fk_rol_creado_por'),
        sa.PrimaryKeyConstraint('clave'),
        sa.UniqueConstraint('nombre'),
    )
    op.bulk_insert(roles, [{"clave": c, "nombre": n, "descripcion": d, "base": True, "activo": True, "permisos": p}
                           for c, n, d, p in BASE]
                   + [{"clave": c, "nombre": n, "descripcion": d, "base": False, "activo": True, "permisos": p}
                      for c, n, d, p in REFERENCIA])
    op.alter_column('usuarios', 'rol', type_=sa.String(length=40), postgresql_using='rol::text',
                    existing_nullable=False)
    op.execute("DROP TYPE IF EXISTS rol_usuario")
    op.create_foreign_key('fk_usuario_rol', 'usuarios', 'roles', ['rol'], ['clave'])


def downgrade() -> None:
    op.drop_constraint('fk_usuario_rol', 'usuarios', type_='foreignkey')
    # Las cuentas con un rol creado a mano vuelven a «consulta».
    op.execute("UPDATE usuarios SET rol = 'consulta' WHERE rol NOT IN ('archivista', 'revisor', 'consulta', 'administrador')")
    op.execute("CREATE TYPE rol_usuario AS ENUM ('archivista', 'revisor', 'consulta', 'administrador')")
    op.alter_column('usuarios', 'rol', type_=postgresql.ENUM(name='rol_usuario', create_type=False),
                    postgresql_using='rol::rol_usuario', existing_nullable=False)
    op.drop_table('roles')
