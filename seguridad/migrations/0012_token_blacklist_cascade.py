"""
Cambia las constraints FK de `rest_framework_simplejwt.token_blacklist` a
`ON DELETE CASCADE` a nivel de base de datos, para que borrar un `SegUsuario`
directamente con SQL (no solo desde el ORM) elimine en cascada sus
`OutstandingToken`/`BlacklistedToken` asociados.

Django emite los FK por defecto como `NO ACTION` (el `on_delete=CASCADE` del
modelo es a nivel de aplicación), por eso un `DELETE FROM seg_usuario` falla.

Buscamos el nombre actual de cada constraint dinámicamente porque Django lo
genera con un hash que depende del entorno.
"""
from django.db import migrations


_ALTER_OUTSTANDING_TO_CASCADE = """
DO $$
DECLARE
    cname TEXT;
BEGIN
    SELECT con.conname INTO cname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
    WHERE rel.relname = 'token_blacklist_outstandingtoken'
      AND att.attname = 'user_id'
      AND con.contype = 'f';

    IF cname IS NOT NULL THEN
        EXECUTE 'ALTER TABLE token_blacklist_outstandingtoken DROP CONSTRAINT ' || quote_ident(cname);
    END IF;

    ALTER TABLE token_blacklist_outstandingtoken
        ADD CONSTRAINT token_blacklist_outstandingtoken_user_id_cascade_fk
        FOREIGN KEY (user_id) REFERENCES seg_usuario(id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
END $$;
"""

_ALTER_OUTSTANDING_TO_RESTRICT = """
DO $$
DECLARE
    cname TEXT;
BEGIN
    SELECT con.conname INTO cname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
    WHERE rel.relname = 'token_blacklist_outstandingtoken'
      AND att.attname = 'user_id'
      AND con.contype = 'f';

    IF cname IS NOT NULL THEN
        EXECUTE 'ALTER TABLE token_blacklist_outstandingtoken DROP CONSTRAINT ' || quote_ident(cname);
    END IF;

    ALTER TABLE token_blacklist_outstandingtoken
        ADD CONSTRAINT token_blacklist_outstandingtoken_user_id_fk
        FOREIGN KEY (user_id) REFERENCES seg_usuario(id)
        DEFERRABLE INITIALLY DEFERRED;
END $$;
"""

_ALTER_BLACKLISTED_TO_CASCADE = """
DO $$
DECLARE
    cname TEXT;
BEGIN
    SELECT con.conname INTO cname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
    WHERE rel.relname = 'token_blacklist_blacklistedtoken'
      AND att.attname = 'token_id'
      AND con.contype = 'f';

    IF cname IS NOT NULL THEN
        EXECUTE 'ALTER TABLE token_blacklist_blacklistedtoken DROP CONSTRAINT ' || quote_ident(cname);
    END IF;

    ALTER TABLE token_blacklist_blacklistedtoken
        ADD CONSTRAINT token_blacklist_blacklistedtoken_token_id_cascade_fk
        FOREIGN KEY (token_id) REFERENCES token_blacklist_outstandingtoken(id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
END $$;
"""

_ALTER_BLACKLISTED_TO_RESTRICT = """
DO $$
DECLARE
    cname TEXT;
BEGIN
    SELECT con.conname INTO cname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
    WHERE rel.relname = 'token_blacklist_blacklistedtoken'
      AND att.attname = 'token_id'
      AND con.contype = 'f';

    IF cname IS NOT NULL THEN
        EXECUTE 'ALTER TABLE token_blacklist_blacklistedtoken DROP CONSTRAINT ' || quote_ident(cname);
    END IF;

    ALTER TABLE token_blacklist_blacklistedtoken
        ADD CONSTRAINT token_blacklist_blacklistedtoken_token_id_fk
        FOREIGN KEY (token_id) REFERENCES token_blacklist_outstandingtoken(id)
        DEFERRABLE INITIALLY DEFERRED;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('seguridad', '0011_alter_segrol_activo_alter_segusuario_idioma_and_more'),
        ('token_blacklist', '0013_alter_blacklistedtoken_options_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql=_ALTER_OUTSTANDING_TO_CASCADE,
            reverse_sql=_ALTER_OUTSTANDING_TO_RESTRICT,
        ),
        migrations.RunSQL(
            sql=_ALTER_BLACKLISTED_TO_CASCADE,
            reverse_sql=_ALTER_BLACKLISTED_TO_RESTRICT,
        ),
    ]
