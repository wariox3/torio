from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0003_alter_ctncliente_owner'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ctncliente',
            name='schema_name',
            field=models.CharField(max_length=100, unique=True),
        ),
    ]
