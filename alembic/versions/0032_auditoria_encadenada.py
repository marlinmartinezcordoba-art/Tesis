"""auditoría encadenada (brecha RF-AUD-002): cada evento guarda la huella
SHA-256 de su contenido unida a la del evento anterior. Alterar, insertar o
quitar un evento en medio rompe la cadena desde ese punto, aunque alguien
desactive el disparador de solo anexar.

Revision ID: 0032
Revises: 0031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0032'
down_revision: Union[str, None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# El texto canónico de un evento: los mismos campos, en el mismo orden y con
# la misma forma en el disparador y en la verificación. jsonb::text es
# determinista (PostgreSQL normaliza el orden de las claves).
FUNCION_HUELLA = """
CREATE FUNCTION auditoria_huella(r registro_auditoria, anterior text) RETURNS text AS $$
    SELECT encode(sha256(convert_to(concat_ws('|',
        r.orden::text,
        to_char(r.fecha AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
        coalesce(r.usuario_id::text, ''), r.modulo, r.accion, coalesce(r.entidad_tipo, ''),
        coalesce(r.entidad_id, ''), coalesce(r.valor_anterior::text, ''), coalesce(r.valor_nuevo::text, ''),
        coalesce(r.detalle, ''), coalesce(r.ip, ''), coalesce(anterior, '')), 'UTF8')), 'hex');
$$ LANGUAGE sql IMMUTABLE;
"""

# Antes de insertar: bajo un candado de transacción (los eventos se encadenan
# de uno en uno), toma el último eslabón, numera el evento y calcula su huella.
FUNCION_ENCADENAR = """
CREATE FUNCTION auditoria_encadenar() RETURNS trigger AS $$
DECLARE
    ultimo registro_auditoria;
BEGIN
    PERFORM pg_advisory_xact_lock(724100);
    SELECT * INTO ultimo FROM registro_auditoria WHERE orden IS NOT NULL ORDER BY orden DESC LIMIT 1;
    NEW.orden := coalesce(ultimo.orden, 0) + 1;
    NEW.huella_anterior := ultimo.huella;
    NEW.huella := auditoria_huella(NEW, ultimo.huella);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.add_column('registro_auditoria', sa.Column('orden', sa.BigInteger(), nullable=True))
    op.add_column('registro_auditoria', sa.Column('huella_anterior', sa.String(64), nullable=True))
    op.add_column('registro_auditoria', sa.Column('huella', sa.String(64), nullable=True))
    op.execute(FUNCION_HUELLA)
    op.execute(FUNCION_ENCADENAR)
    # Los eventos que ya existían se encadenan una sola vez, en el orden en
    # que se registraron; es la única vez que esta migración los toca.
    op.execute("ALTER TABLE registro_auditoria DISABLE TRIGGER registro_auditoria_inmutable")
    op.execute("""
        DO $$
        DECLARE
            r registro_auditoria;
            n bigint := 0;
            previa text := NULL;
        BEGIN
            FOR r IN SELECT * FROM registro_auditoria ORDER BY id LOOP
                n := n + 1;
                r.orden := n;
                UPDATE registro_auditoria SET orden = n, huella_anterior = previa,
                       huella = auditoria_huella(r, previa) WHERE id = r.id;
                previa := auditoria_huella(r, previa);
            END LOOP;
        END $$;
    """)
    op.execute("ALTER TABLE registro_auditoria ENABLE TRIGGER registro_auditoria_inmutable")
    op.create_index('ix_registro_auditoria_orden', 'registro_auditoria', ['orden'], unique=True)
    op.execute("""
        CREATE TRIGGER registro_auditoria_encadenado
        BEFORE INSERT ON registro_auditoria
        FOR EACH ROW EXECUTE FUNCTION auditoria_encadenar();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER registro_auditoria_encadenado ON registro_auditoria")
    op.execute("DROP FUNCTION auditoria_encadenar()")
    op.drop_index('ix_registro_auditoria_orden', table_name='registro_auditoria')
    op.execute("DROP FUNCTION auditoria_huella(registro_auditoria, text)")
    op.drop_column('registro_auditoria', 'huella')
    op.drop_column('registro_auditoria', 'huella_anterior')
    op.drop_column('registro_auditoria', 'orden')
