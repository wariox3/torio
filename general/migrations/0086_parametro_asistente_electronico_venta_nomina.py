from django.db import migrations, models

# Hubo dos versiones de la 0085 con el mismo nombre: la primera (31d7467) dejó la
# columna como `gen_asistente_electronico` y llegó a ejecutarse en el servidor; la
# segunda (be53126) la editó para dejar `_venta` y `_nomina`. Django da la 0085 por
# aplicada en ambos casos, así que un schema puede estar en cualquiera de los dos
# estados, y uno creado desde cero con esta historia queda como la primera. Por eso
# el SQL es condicional y el estado de Django va aparte: el resultado es el mismo
# venga de donde venga. El valor no se invierte otra vez; eso ya lo hizo la 0085.
ADELANTE = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'gen_parametro'
          AND column_name = 'gen_asistente_electronico'
    ) THEN
        ALTER TABLE gen_parametro RENAME COLUMN gen_asistente_electronico TO gen_asistente_electronico_venta;
    END IF;
END $$;
ALTER TABLE gen_parametro ADD COLUMN IF NOT EXISTS gen_asistente_electronico_nomina boolean NOT NULL DEFAULT true;
"""

ATRAS = """
ALTER TABLE gen_parametro DROP COLUMN IF EXISTS gen_asistente_electronico_nomina;
ALTER TABLE gen_parametro RENAME COLUMN gen_asistente_electronico_venta TO gen_asistente_electronico;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('general', '0085_parametro_asistente_electronico'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(sql=ADELANTE, reverse_sql=ATRAS)],
            state_operations=[
                migrations.RenameField(
                    model_name='genparametro',
                    old_name='gen_asistente_electronico',
                    new_name='gen_asistente_electronico_venta',
                ),
                migrations.AddField(
                    model_name='genparametro',
                    name='gen_asistente_electronico_nomina',
                    field=models.BooleanField(db_default=True, default=True),
                ),
            ],
        ),
    ]
