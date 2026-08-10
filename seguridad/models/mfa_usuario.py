from django.db import models

# Métodos de segundo factor. `totp` es el estándar RFC 6238: el celular calcula el
# código a partir del secreto y la hora, sin hablar con el servidor. `correo` y `sms`
# generan el código acá y lo envían con Zinc, para quien no quiera instalar una app
# autenticadora.
#
# El motor del desafío es el mismo para los tres: solo cambia de dónde sale el código,
# y en los dos últimos, por dónde se manda.
METODO_TOTP = 'totp'
METODO_CORREO = 'correo'
METODO_SMS = 'sms'
# El orden es el que ve el usuario al elegir: primero los que no le exigen instalar nada,
# y entre esos el correo antes que el SMS, que es el único con costo por mensaje y el más
# débil de los tres (SIM swap).
METODOS = [
    (METODO_CORREO, 'Código por correo'),
    (METODO_SMS, 'Código por SMS'),
    (METODO_TOTP, 'App autenticadora'),
]

# Los que mandan el código desde el servidor y lo guardan hasheado en el desafío.
METODOS_ENVIADOS = (METODO_CORREO, METODO_SMS)


class SegMfaUsuario(models.Model):
    """
    Configuración de segundo factor de una cuenta.

    El MFA es del usuario, no del contenedor: vive en el schema público junto a
    `SegUsuario` y aplica igual en todos los contenedores a los que pertenezca,
    porque el login es uno solo y ocurre antes de resolver el tenant.
    """

    usuario = models.OneToOneField(
        'seguridad.SegUsuario',
        on_delete=models.CASCADE,
        db_column='usuario_id',
        related_name='mfa',
    )
    metodo = models.CharField(max_length=10, choices=METODOS, default=METODO_SMS, db_default=METODO_SMS)
    # Secreto base32 cifrado con Fernet (`MFA_ENCRYPTION_KEY`, separada de `SECRET_KEY`
    # para poder rotar la firma de los JWT sin invalidar todos los MFA). Solo aplica a
    # TOTP: el método correo no tiene secreto persistente.
    secreto = models.TextField(null=True)
    # Arranca en False: `configurar` deja la fila pendiente y solo `activar` la prende,
    # tras confirmar un código. Así nadie queda bloqueado por un enrolamiento a medias.
    activo = models.BooleanField(default=False, db_default=False)
    # Último contador TOTP consumido. Se acepta `valid_window=1` para tolerar el desfase
    # de reloj de los celulares, y esto impide que un código interceptado se reuse dentro
    # de su ventana.
    ultimo_contador = models.BigIntegerField(null=True)
    fecha_activacion = models.DateTimeField(null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seg_mfa_usuario'
        verbose_name = 'MFA de usuario'
        verbose_name_plural = 'MFA de usuarios'

    def __str__(self):
        return f'{self.usuario_id} ({self.metodo})'
