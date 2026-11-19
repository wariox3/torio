import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('general', '0109_usuario_configuracion'),
        ('inventario', '0002_invexistencia'),
        ('venta', '0003_turno_usuario_correo'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='GenUsuarioConfiguracion',
            new_name='GenConfiguracionUsuario',
        ),
        migrations.AlterModelTable(
            name='genconfiguracionusuario',
            table='gen_configuracion_usuario',
        ),
        migrations.AlterModelOptions(
            name='genconfiguracionusuario',
            options={'verbose_name': 'Configuración de usuario', 'verbose_name_plural': 'Configuraciones de usuario'},
        ),
        migrations.AlterField(
            model_name='genconfiguracionusuario',
            name='sede',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='configuraciones_usuario_sede_rel', to='general.gensede'),
        ),
        migrations.AlterField(
            model_name='genconfiguracionusuario',
            name='almacen',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='configuraciones_usuario_almacen_rel', to='inventario.invalmacen'),
        ),
        migrations.AlterField(
            model_name='genconfiguracionusuario',
            name='caja',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='configuraciones_usuario_caja_rel', to='venta.vencaja'),
        ),
    ]
