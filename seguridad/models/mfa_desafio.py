import uuid

from django.db import models

from seguridad.models.mfa_usuario import METODOS


class SegMfaDesafio(models.Model):
    """
    Segundo paso pendiente de un login con la clave ya validada.

    Va en base de datos y no en cache porque no hay `CACHES` configurado: el cache es
    `LocMemCache`, un espacio por proceso, inservible entre workers de gunicorn. Acá
    además queda el conteo de intentos —el freno real a la fuerza bruta sobre 6
    dígitos— y la traza para auditoría.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.CASCADE,
        db_column='usuario_id',
        related_name='desafios_mfa',
    )
    # Se copia del `SegMfaUsuario` al crear el desafío: si el usuario cambia de método
    # con un desafío en vuelo, ese desafío se resuelve como fue emitido.
    metodo = models.CharField(max_length=10, choices=METODOS)
    # SHA-256 del código enviado. Solo para el método correo: en TOTP el código no se
    # guarda en ningún lado, se recalcula a partir del secreto.
    hash_codigo = models.CharField(max_length=64, null=True)
    # Indexado porque cada desafío nuevo borra los vencidos; así no hace falta un cron.
    expira = models.DateTimeField(db_index=True)
    consumido = models.BooleanField(default=False, db_default=False)
    intentos = models.PositiveSmallIntegerField(default=0, db_default=0)
    ip = models.GenericIPAddressField(null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seg_mfa_desafio'
        verbose_name = 'Desafío MFA'
        verbose_name_plural = 'Desafíos MFA'

    def __str__(self):
        return f'{self.usuario_id} ({self.metodo})'
