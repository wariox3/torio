"""
Los pendientes se ven por grupo (`CtnPendienteTipo.grupo`) y la invitación ya
solo lleva grupos: se eliminan `CtnInvitacionAplicacion` y `CtnAplicacion`.

Depende de `seguridad/0032`, que borra `SegUsuarioClienteAplicacion`, la otra
tabla con FK a `ctn_aplicacion`.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenedor', '0059_invitacion_aplicacion'),
        ('seguridad', '0032_permisos_en_membresia'),
    ]

    operations = [
        migrations.AddField(
            model_name='ctnpendientetipo',
            name='grupo',
            # El default solo llena el tipo que ya exista: 1 «Periodo anterior
            # abierto» → 7 Contabilidad. El campo queda sin default.
            field=models.ForeignKey(
                default=7, on_delete=django.db.models.deletion.PROTECT, to='auth.group',
            ),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name='ctnpendientetipo',
            name='aplicacion',
        ),
        migrations.RemoveField(
            model_name='ctninvitacion',
            name='aplicaciones',
        ),
        migrations.DeleteModel(
            name='CtnInvitacionAplicacion',
        ),
        migrations.DeleteModel(
            name='CtnAplicacion',
        ),
    ]
