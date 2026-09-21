from django.db import migrations, models


class Migration(migrations.Migration):
    """
    `electronico_id` pasa a guardar el id del documento en rededoc, que es un UUID.

    PostgreSQL no convierte `integer` a `uuid`, así que los valores enteros que
    hubiera —ids del servicio electrónico anterior— se descartan: `USING NULL`.
    """

    dependencies = [
        ('general', '0078_gendocumentotipo_codigo'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    'ALTER TABLE gen_documento ALTER COLUMN electronico_id TYPE uuid USING NULL',
                    reverse_sql='ALTER TABLE gen_documento ALTER COLUMN electronico_id TYPE integer USING NULL',
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='gendocumento',
                    name='electronico_id',
                    field=models.UUIDField(null=True),
                ),
            ],
        ),
    ]
