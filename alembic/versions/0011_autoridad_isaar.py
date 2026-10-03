"""vocabularios: ficha de autoridad ISAAR (CPF) en cuatro áreas, grupo, mecanismo con versión,
hitos institucionales, lugar ampliado, jerarquía SKOS de tipos de actividad y relaciones fechadas

Revision ID: 0011
Revises: 0010

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NIVEL = ('minimo', 'completo')
TIPO_NOMBRE = ('paralela', 'normalizada', 'otra', 'historica')
TIPO_HITO = ('creacion', 'reforma', 'traslado', 'supresion', 'otro')
ESTADO = ('vigente', 'anulado')


def upgrade() -> None:
    nivel = postgresql.ENUM(*NIVEL, name='nivel_detalle', create_type=False)
    sa.Enum(*NIVEL, name='nivel_detalle').create(op.get_bind(), checkfirst=True)
    for nombre, valores in (('tipo_nombre_entidad', TIPO_NOMBRE), ('tipo_hito', TIPO_HITO),
                            ('estado_registro', ESTADO)):
        sa.Enum(*valores, name=nombre).create(op.get_bind(), checkfirst=True)

    # Área de identificación, descripción y control (ISAAR-CPF), lugar y mecanismo.
    columnas = [
        sa.Column('version', sa.String(length=120), nullable=True),
        sa.Column('existencia_edtf', sa.String(length=200), nullable=True),
        sa.Column('existencia_inicio', sa.Date(), nullable=True),
        sa.Column('existencia_fin', sa.Date(), nullable=True),
        sa.Column('historia', sa.Text(), nullable=True),
        sa.Column('estatuto_juridico', sa.String(length=20), nullable=True),
        sa.Column('estructura', sa.Text(), nullable=True),
        sa.Column('contexto_general', sa.Text(), nullable=True),
        sa.Column('reglas', sa.String(length=200), nullable=True),
        sa.Column('fuentes', sa.Text(), nullable=True),
        sa.Column('nivel_detalle', nivel, server_default='minimo', nullable=False),
        sa.Column('latitud', sa.Float(), nullable=True),
        sa.Column('longitud', sa.Float(), nullable=True),
        sa.Column('tipo_lugar', sa.String(length=30), nullable=True),
        sa.Column('concepto_superior_id', sa.UUID(), nullable=True),
    ]
    for c in columnas:
        op.add_column('entidades_vocabulario', c)
    op.create_foreign_key('fk_vocabulario_concepto_superior', 'entidades_vocabulario', 'entidades_vocabulario',
                          ['concepto_superior_id'], ['id'])
    op.create_index('ix_vocabulario_nivel_detalle', 'entidades_vocabulario', ['nivel_detalle'])
    op.create_index('ix_vocabulario_concepto_superior', 'entidades_vocabulario', ['concepto_superior_id'])
    op.create_check_constraint('ck_vocabulario_latitud', 'entidades_vocabulario',
                               'latitud IS NULL OR (latitud BETWEEN -90 AND 90)')
    op.create_check_constraint('ck_vocabulario_longitud', 'entidades_vocabulario',
                               'longitud IS NULL OR (longitud BETWEEN -180 AND 180)')
    op.create_check_constraint('ck_vocabulario_no_es_su_propio_superior', 'entidades_vocabulario',
                               'concepto_superior_id IS NULL OR concepto_superior_id <> id')

    # Relaciones fechadas (vigencia de una relación entre agentes) y con nota.
    op.add_column('relaciones', sa.Column('fecha_edtf', sa.String(length=200), nullable=True))
    op.add_column('relaciones', sa.Column('nota', sa.String(length=500), nullable=True))

    estado = postgresql.ENUM(*ESTADO, name='estado_registro', create_type=False)
    op.create_table(
        'nombres_entidad',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('entidad_id', sa.UUID(), nullable=False),
        sa.Column('tipo', postgresql.ENUM(*TIPO_NOMBRE, name='tipo_nombre_entidad', create_type=False), nullable=False),
        sa.Column('nombre', sa.String(length=300), nullable=False),
        sa.Column('idioma', sa.String(length=12), nullable=True),
        sa.Column('regla', sa.String(length=120), nullable=True),
        sa.Column('vigencia_edtf', sa.String(length=200), nullable=True),
        sa.Column('inicio', sa.Date(), nullable=True),
        sa.Column('fin', sa.Date(), nullable=True),
        sa.Column('estado', estado, server_default='vigente', nullable=False),
        sa.Column('creado_por_id', sa.UUID(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['entidad_id'], ['entidades_vocabulario.id']),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_nombres_entidad_entidad', 'nombres_entidad', ['entidad_id'])
    op.create_table(
        'identificadores_entidad',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('entidad_id', sa.UUID(), nullable=False),
        sa.Column('esquema', sa.String(length=40), nullable=False),
        sa.Column('valor', sa.String(length=200), nullable=False),
        sa.Column('estado', estado, server_default='vigente', nullable=False),
        sa.Column('creado_por_id', sa.UUID(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['entidad_id'], ['entidades_vocabulario.id']),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_identificadores_entidad_entidad', 'identificadores_entidad', ['entidad_id'])
    op.create_index('ux_identificador_vigente', 'identificadores_entidad', ['entidad_id', 'esquema', 'valor'],
                    unique=True, postgresql_where=sa.text("estado = 'vigente'"))
    op.create_table(
        'hitos',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('fondo_id', sa.UUID(), nullable=False),
        sa.Column('agente_id', sa.UUID(), nullable=False),
        sa.Column('tipo', postgresql.ENUM(*TIPO_HITO, name='tipo_hito', create_type=False), nullable=False),
        sa.Column('descripcion', sa.String(length=500), nullable=False),
        sa.Column('edtf', sa.String(length=200), nullable=False),
        sa.Column('inicio', sa.Date(), nullable=True),
        sa.Column('fin', sa.Date(), nullable=True),
        sa.Column('estado', estado, server_default='vigente', nullable=False),
        sa.Column('agente_original_id', sa.UUID(), nullable=True),
        sa.Column('creado_por_id', sa.UUID(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['fondo_id'], ['recursos_documentales.id']),
        sa.ForeignKeyConstraint(['agente_id'], ['entidades_vocabulario.id']),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_hitos_agente', 'hitos', ['agente_id'])


def downgrade() -> None:
    op.drop_table('hitos')
    op.drop_index('ux_identificador_vigente', table_name='identificadores_entidad')
    op.drop_table('identificadores_entidad')
    op.drop_table('nombres_entidad')
    op.drop_column('relaciones', 'nota')
    op.drop_column('relaciones', 'fecha_edtf')
    op.drop_constraint('ck_vocabulario_no_es_su_propio_superior', 'entidades_vocabulario')
    op.drop_constraint('ck_vocabulario_longitud', 'entidades_vocabulario')
    op.drop_constraint('ck_vocabulario_latitud', 'entidades_vocabulario')
    op.drop_index('ix_vocabulario_concepto_superior', table_name='entidades_vocabulario')
    op.drop_index('ix_vocabulario_nivel_detalle', table_name='entidades_vocabulario')
    op.drop_constraint('fk_vocabulario_concepto_superior', 'entidades_vocabulario', type_='foreignkey')
    for c in ('concepto_superior_id', 'tipo_lugar', 'longitud', 'latitud', 'nivel_detalle', 'fuentes', 'reglas',
              'contexto_general', 'estructura', 'estatuto_juridico', 'historia', 'existencia_fin',
              'existencia_inicio', 'existencia_edtf', 'version'):
        op.drop_column('entidades_vocabulario', c)
    for nombre in ('estado_registro', 'tipo_hito', 'tipo_nombre_entidad', 'nivel_detalle'):
        sa.Enum(name=nombre).drop(op.get_bind(), checkfirst=True)
