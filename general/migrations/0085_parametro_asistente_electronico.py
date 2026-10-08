from django.db import migrations, models


class Migration(migrations.Migration):
    """
    `gen_factura_electronica_activa` pasa a `gen_asistente_electronico`, con el
    sentido invertido: activa=False (lo que tienen todos hoy) es asistente=True,
    pendiente. Se renombra y se invierte en vez de borrar y crear para que un
    tenant que ya estuviera activo quede con el asistente terminado. La inversión
    es su propia inversa, así que la migración se puede deshacer.
    """

    dependencies = [
        ('general', '0084_parametro_electronico_habilitado'),
    ]

    operations = [
        migrations.RenameField(
            model_name='genparametro',
            old_name='gen_factura_electronica_activa',
            new_name='gen_asistente_electronico',
        ),
        migrations.RunSQL(
            sql='UPDATE gen_parametro SET gen_asistente_electronico = NOT gen_asistente_electronico',
            reverse_sql='UPDATE gen_parametro SET gen_asistente_electronico = NOT gen_asistente_electronico',
        ),
        migrations.AlterField(
            model_name='genparametro',
            name='gen_asistente_electronico',
            field=models.BooleanField(db_default=True, default=True),
        ),
    ]
