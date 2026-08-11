from django.db import models

# Resultado de un intento de ingreso. El login tiene dos pasos, así que un mismo
# intento puede dejar dos filas: `mfa_pendiente` cuando la clave fue correcta y se
# abrió el desafío, y después `ok` o `mfa_fallido` según cómo termine el segundo paso.
RESULTADO_OK = 'ok'
RESULTADO_CLAVE = 'clave'
RESULTADO_NO_VERIFICADO = 'no_verificado'
RESULTADO_MFA_PENDIENTE = 'mfa_pendiente'
RESULTADO_MFA_FALLIDO = 'mfa_fallido'

RESULTADOS = [
    (RESULTADO_OK, 'Ingreso exitoso'),
    (RESULTADO_CLAVE, 'Credenciales inválidas'),
    (RESULTADO_NO_VERIFICADO, 'Cuenta no verificada'),
    (RESULTADO_MFA_PENDIENTE, 'Segundo factor pendiente'),
    (RESULTADO_MFA_FALLIDO, 'Segundo factor fallido'),
]


class SegAcceso(models.Model):
    """
    Bitácora de intentos de ingreso, exitosos y fallidos.

    Vive en el schema público junto al login: se escribe antes de resolver cualquier
    tenant, y una misma cuenta puede pertenecer a varios contenedores, así que el
    registro es de la cuenta y no de la organización.

    Se guardan también los intentos contra correos que no existen. Es lo que permite
    ver una enumeración de usuarios o una fuerza bruta en curso; sin eso la tabla solo
    sirve como historial de "dónde entré".
    """

    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.SET_NULL,
        db_column='usuario_id',
        related_name='accesos',
        null=True,
    )
    # El correo tecleado, siempre, aunque el usuario haya quedado ligado: es lo único
    # que queda de un intento contra una cuenta inexistente, y sobrevive al borrado de
    # la cuenta (por eso el FK es SET_NULL y no CASCADE: borrar al usuario no debe
    # borrar su auditoría).
    email = models.CharField(max_length=254)
    resultado = models.CharField(max_length=20, choices=RESULTADOS, db_index=True)
    ip = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(null=True)
    # Método del desafío, cuando el intento pasó por el segundo paso.
    metodo_mfa = models.CharField(max_length=10, null=True)
    # Entró saltando el segundo paso por la cookie de dispositivo recordado.
    dispositivo_recordado = models.BooleanField(default=False, db_default=False)
    # Entró con un código de respaldo: señal de que perdió acceso a su método habitual.
    codigo_respaldo = models.BooleanField(default=False, db_default=False)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'seg_acceso'
        verbose_name = 'Acceso'
        verbose_name_plural = 'Accesos'
        ordering = ['-fecha']
        indexes = [
            # El endpoint del usuario: sus últimos accesos.
            models.Index(fields=['usuario', '-fecha'], name='seg_acceso_usuario_fecha'),
            # Los dos que sirven para investigar: intentos contra un correo, e intentos
            # desde una IP.
            models.Index(fields=['email', '-fecha'], name='seg_acceso_email_fecha'),
            models.Index(fields=['ip', '-fecha'], name='seg_acceso_ip_fecha'),
        ]

    def __str__(self):
        return f'{self.email} — {self.resultado} ({self.fecha:%Y-%m-%d %H:%M})'
