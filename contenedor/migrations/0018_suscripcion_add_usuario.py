from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0017_suscripcion_cascade'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='ctnsuscripcion',
            name='usuario',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='suscripciones',
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
    ]
