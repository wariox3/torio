from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0033_invitacion_add_usuario'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Limpiar filas sin datos reales
        migrations.RunSQL('DELETE FROM ctn_invitacion;', migrations.RunSQL.noop),
        # 2. Quitar unique_together antiguo (cliente, correo) antes de tocar los campos
        migrations.AlterUniqueTogether(
            name='ctninvitacion',
            unique_together=set(),
        ),
        # 3. usuario (nullable FK al invitado) → usuario_invitado
        migrations.RenameField(
            model_name='ctninvitacion',
            old_name='usuario',
            new_name='usuario_invitado',
        ),
        # 4. invitado_por → usuario (quien envía)
        migrations.RenameField(
            model_name='ctninvitacion',
            old_name='invitado_por',
            new_name='usuario',
        ),
        # 5. Quitar nullable de usuario_invitado
        migrations.AlterField(
            model_name='ctninvitacion',
            name='usuario_invitado',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='invitaciones_recibidas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # 6. Eliminar correo
        migrations.RemoveField(
            model_name='ctninvitacion',
            name='correo',
        ),
        # 7. Nuevo unique_together (cliente, usuario_invitado)
        migrations.AlterUniqueTogether(
            name='ctninvitacion',
            unique_together={('cliente', 'usuario_invitado')},
        ),
    ]
