"""
La autorización dentro de un contenedor pasa a la membresía, en el público:
`SegUsuarioCliente.is_superuser` y `SegUsuarioClienteGrupo`. Se elimina
`SegUsuarioClienteAplicacion`: el menú sale de los grupos.

Solo estructura: los datos (quién es superusuario, qué grupos tiene cada
miembro) se pasan a mano. Hasta entonces `is_superuser` queda en False.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('seguridad', '0031_elimina_usuario_aplicacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='segusuariocliente',
            name='is_superuser',
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.CreateModel(
            name='SegUsuarioClienteGrupo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grupo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='auth.group')),
                ('usuario_cliente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grupos', to='seguridad.segusuariocliente')),
            ],
            options={
                'verbose_name': 'Usuario-Cliente-Grupo',
                'verbose_name_plural': 'Usuario-Cliente-Grupos',
                'db_table': 'seg_usuario_cliente_grupo',
                'constraints': [models.UniqueConstraint(fields=('usuario_cliente', 'grupo'), name='seg_usuario_cliente_grupo_unico')],
            },
        ),
        migrations.DeleteModel(
            name='SegUsuarioClienteAplicacion',
        ),
    ]
