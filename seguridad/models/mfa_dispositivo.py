from django.db import models


class SegMfaDispositivo(models.Model):
    """
    Navegador donde el usuario eligió "recordar este dispositivo".

    Mientras la cookie firmada siga viva, ese navegador salta el segundo paso. Es la
    contraparte de mantener el refresh token corto: en vez de alargar la ventana de un
    token robado, se le da al usuario una excepción explícita y revocable.
    """

    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.CASCADE,
        db_column='usuario_id',
        related_name='dispositivos_mfa',
    )
    # SHA-256 del token que viaja en la cookie. Se guarda el hash y no el token para que
    # un dump de la base no permita fabricar cookies válidas.
    hash_token = models.CharField(max_length=64, unique=True)
    user_agent = models.TextField(null=True)
    ip = models.GenericIPAddressField(null=True)
    ultimo_uso = models.DateTimeField(null=True)
    expira = models.DateTimeField(db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seg_mfa_dispositivo'
        verbose_name = 'Dispositivo MFA'
        verbose_name_plural = 'Dispositivos MFA'
        ordering = ['-ultimo_uso']

    def __str__(self):
        return f'{self.usuario_id} ({self.ip})'
