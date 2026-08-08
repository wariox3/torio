from django.db import models


class SegMfaCodigoRespaldo(models.Model):
    """
    Códigos de un solo uso para entrar sin el segundo factor habitual.

    Son la única vía self-service de recuperación: sin ellos el desbloqueo es
    intervención manual. Un "reset de MFA por correo" volvería el MFA cosmético,
    porque el correo es justamente el canal de recuperación de la clave.
    """

    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.CASCADE,
        db_column='usuario_id',
        related_name='codigos_respaldo',
    )
    # SHA-256 del código normalizado, no pbkdf2: son 10 caracteres base32 (~50 bits de
    # entropía), así que no hace falta un hash lento, y verificar 10 pbkdf2 en cada
    # intento sería gasto puro. El índice permite buscar por hash en vez de recorrerlos.
    hash_codigo = models.CharField(max_length=64, db_index=True)
    usado_en = models.DateTimeField(null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seg_mfa_codigo_respaldo'
        verbose_name = 'Código de respaldo MFA'
        verbose_name_plural = 'Códigos de respaldo MFA'
        ordering = ['id']

    def __str__(self):
        return f'{self.usuario_id} ({"usado" if self.usado_en else "disponible"})'
