from django.db import migrations

# 0062 convirtió `fecha` de date a timestamptz: cada movimiento quedó a la
# medianoche de la sesión (UTC), que en Bogotá es las 7 p. m. del día anterior.
# Se le pone la hora real del pago: la de Wompi (`fecha_transaccion`) y, si el
# evento no la trajo, la hora en que llegó (`fecha`, nunca nula). Todo
# movimiento tiene evento (OneToOne no nulo), así que ninguno queda sin hora.
SQL = """
UPDATE ctn_movimiento m
SET fecha = COALESCE(e.fecha_transaccion, e.fecha)
FROM ctn_evento_pago e
WHERE e.id = m.evento_pago_id
"""


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0062_movimiento_fecha_hora'),
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=migrations.RunSQL.noop),
    ]
