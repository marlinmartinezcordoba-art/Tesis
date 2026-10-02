"""preservación OAIS: segunda copia, restauración y derechos

Revision ID: 0008
Revises: 0007

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUMS = {
    'motivo_segunda_copia': ('ingesta', 'migracion', 'reposicion', 'cambio_de_ubicacion', 'pendiente'),
    'estado_segunda_copia': ('sincronizada', 'alterada', 'ausente', 'reemplazada'),
    'resultado_segunda_copia': ('integra', 'alterada', 'ausente', 'sin_copia'),
    'entidad_derechos': ('instanciacion', 'recurso_documental'),
    'base_derechos': ('estatuto', 'licencia', 'derecho_de_autor', 'politica_institucional', 'otra'),
    'acceso_derechos': ('publico', 'clasificado', 'reservado'),
    'reproduccion_derechos': ('permitida', 'condicionada', 'no_permitida'),
}


def _enum(nombre: str):
    return postgresql.ENUM(*ENUMS[nombre], name=nombre, create_type=False)


def upgrade() -> None:
    for nombre, valores in ENUMS.items():
        sa.Enum(*valores, name=nombre).create(op.get_bind(), checkfirst=True)
    op.create_table('segundas_copias',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('instanciacion_id', sa.UUID(), nullable=False),
    sa.Column('ubicacion', sa.String(length=500), nullable=False),
    sa.Column('ruta', sa.String(length=500), nullable=False),
    sa.Column('algoritmo', sa.String(length=20), nullable=False),
    sa.Column('huella', sa.String(length=64), nullable=False),
    sa.Column('tamano_bytes', sa.BigInteger(), nullable=False),
    sa.Column('motivo', _enum('motivo_segunda_copia'), nullable=False),
    sa.Column('estado', _enum('estado_segunda_copia'), nullable=False),
    sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('creada_por_id', sa.UUID(), nullable=True),
    sa.Column('ultima_verificacion_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reemplazada_en', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['creada_por_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['instanciacion_id'], ['instanciaciones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_segundas_copias_instanciacion_id'), 'segundas_copias', ['instanciacion_id'], unique=False)
    op.create_index(op.f('ix_segundas_copias_estado'), 'segundas_copias', ['estado'], unique=False)
    op.create_table('restauraciones',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('instanciacion_id', sa.UUID(), nullable=False),
    sa.Column('segunda_copia_id', sa.UUID(), nullable=False),
    sa.Column('fecha', sa.DateTime(timezone=True), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=False),
    sa.Column('estado_previo', sa.String(length=20), nullable=False),
    sa.Column('huella_previa', sa.String(length=64), nullable=True),
    sa.Column('ruta_cuarentena', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['instanciacion_id'], ['instanciaciones.id'], ),
    sa.ForeignKeyConstraint(['segunda_copia_id'], ['segundas_copias.id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_restauraciones_instanciacion_id'), 'restauraciones', ['instanciacion_id'], unique=False)
    op.create_table('declaraciones_derechos',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('fondo_id', sa.UUID(), nullable=False),
    sa.Column('entidad_tipo', _enum('entidad_derechos'), nullable=False),
    sa.Column('entidad_id', sa.UUID(), nullable=False),
    sa.Column('base', _enum('base_derechos'), nullable=False),
    sa.Column('acceso', _enum('acceso_derechos'), nullable=False),
    sa.Column('reproduccion', _enum('reproduccion_derechos'), nullable=False),
    sa.Column('fundamento', sa.String(length=500), nullable=False),
    sa.Column('nota', sa.String(length=500), nullable=True),
    sa.Column('vigente_hasta', sa.Date(), nullable=True),
    sa.Column('vigente', sa.Boolean(), nullable=False),
    sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('creada_por_id', sa.UUID(), nullable=False),
    sa.Column('reemplazada_en', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['creada_por_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['fondo_id'], ['recursos_documentales.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_declaraciones_derechos_fondo_id'), 'declaraciones_derechos', ['fondo_id'], unique=False)
    op.create_index(op.f('ix_declaraciones_derechos_entidad_id'), 'declaraciones_derechos', ['entidad_id'], unique=False)
    op.create_index(op.f('ix_declaraciones_derechos_vigente'), 'declaraciones_derechos', ['vigente'], unique=False)
    op.add_column('verificaciones_integridad', sa.Column('segunda_copia_id', sa.UUID(), nullable=True))
    op.add_column('verificaciones_integridad', sa.Column('segunda_copia_resultado', _enum('resultado_segunda_copia'),
                                                         nullable=True))
    op.add_column('verificaciones_integridad', sa.Column('segunda_copia_huella', sa.String(length=64), nullable=True))
    op.create_foreign_key('fk_verificacion_segunda_copia', 'verificaciones_integridad', 'segundas_copias',
                          ['segunda_copia_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_verificacion_segunda_copia', 'verificaciones_integridad', type_='foreignkey')
    op.drop_column('verificaciones_integridad', 'segunda_copia_huella')
    op.drop_column('verificaciones_integridad', 'segunda_copia_resultado')
    op.drop_column('verificaciones_integridad', 'segunda_copia_id')
    op.drop_table('declaraciones_derechos')
    op.drop_table('restauraciones')
    op.drop_table('segundas_copias')
    for nombre in ENUMS:
        sa.Enum(name=nombre).drop(op.get_bind(), checkfirst=True)
