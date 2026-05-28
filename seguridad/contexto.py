import contextvars

_usuario_actual = contextvars.ContextVar('usuario_actual', default=None)


def obtener_usuario_actual():
    """Retorna el usuario autenticado del request en curso, o None si no hay."""
    return _usuario_actual.get()
