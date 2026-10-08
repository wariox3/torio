from django.db import migrations, models


class Migration(migrations.Migration):
    """
    `gen_factura_electronica_activa` pasa a `gen_asistente_electronico_venta`, con
    el sentido invertido: activa=False (lo que tienen todos hoy) es asistente=True,
    pendiente. Se renombra y se invierte en vez de borrar y crear para que un
    tenant que ya estuviera activo quede con el asistente terminado. La inversión
    es su propia inversa, así que la migración se puede deshacer.

    `gen_asistente_electronico_nomina` es nuevo y arranca pendiente en todos.
    """

    dependencies = [
        ('general', '0084_parametro_electronico_habilitado'),
    ]

    operations = [
        migrations.RenameField(
            model_name='genparametro',
            old_name='gen_factura_electronica_activa',
            new_name='gen_asistente_electronico_venta',
        ),
        migrations.RunSQL(
            sql='UPDATE gen_parametro SET gen_asistente_electronico_venta = NOT gen_asistente_electronico_venta',
            reverse_sql='UPDATE gen_parametro SET gen_asistente_electronico_venta = NOT gen_asistente_electronico_venta',
        ),
        migrations.AlterField(
            model_name='genparametro',
            name='gen_asistente_electronico_venta',
            field=models.BooleanField(db_default=True, default=True),
        ),
        migrations.AddField(
            model_name='genparametro',
            name='gen_asistente_electronico_nomina',
            field=models.BooleanField(db_default=True, default=True),
        ),
    ]
