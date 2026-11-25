"""
Reglas de estructura del PUC para `ConCuenta`. Las comparten crear, editar e
importar, para que una cuenta quede igual venga de donde venga.

En `con_cuenta` solo viven subcuentas (6 dígitos) y auxiliares (8, 10…): clase,
grupo y cuenta (1, 2 y 4 dígitos) son los catálogos `ConCuentaClase`,
`ConCuentaGrupo` y `ConCuentaCuenta`, y su PK es el prefijo del código.

Jerarquía: solo las hojas mueven. Una auxiliar exige que su padre (el código sin
los dos últimos dígitos) exista en `con_cuenta`; al crearla, el padre deja de
permitir movimiento. Si el padre ya se usa en algún lado (movimientos, ítems,
formas de pago, conceptos de nómina…) no se apaga, porque todo eso dejaría de
contabilizar: hay que trasladar o cambiar esas referencias primero.

Los errores son `CuentaInvalida` con un mensaje para el usuario: el serializer lo
devuelve en `detail` y el importar en el error de la fila.
"""
import re

from contabilidad.models import (
    ConCuenta,
    ConCuentaClase,
    ConCuentaCuenta,
    ConCuentaGrupo,
    ConCuentaSubcuenta,
)

LONGITUD_MINIMA = 6
LONGITUD_MAXIMA = ConCuenta._meta.get_field('codigo').max_length
_DIGITOS = re.compile(r'[0-9]+')


class CuentaInvalida(ValueError):
    pass


def normalizar_codigo(valor):
    """El código como texto. Una celda numérica de Excel llega como 110505.0."""
    if valor is None:
        return ''
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def validar_formato(codigo):
    if not codigo:
        raise CuentaInvalida('El código es obligatorio')
    # `isdigit()` acepta dígitos Unicode como '²', que `int()` no convierte.
    if not _DIGITOS.fullmatch(codigo):
        raise CuentaInvalida(f'El código {codigo} solo puede tener dígitos')
    if codigo[0] == '0':
        raise CuentaInvalida(f'El código {codigo} no puede empezar en 0: no existe la clase 0')
    if len(codigo) < LONGITUD_MINIMA:
        raise CuentaInvalida(
            f'El código {codigo} tiene {len(codigo)} dígitos: las cuentas se crean desde '
            f'la subcuenta ({LONGITUD_MINIMA} dígitos); clase, grupo y cuenta vienen del PUC'
        )
    if len(codigo) % 2:
        raise CuentaInvalida(
            f'El código {codigo} tiene {len(codigo)} dígitos: debe tener un número par '
            f'(6, 8, 10…)'
        )
    if len(codigo) > LONGITUD_MAXIMA:
        raise CuentaInvalida(f'El código {codigo} supera los {LONGITUD_MAXIMA} dígitos')


def cargar_catalogos(codigos):
    """Los ids de los catálogos que necesitan estos códigos, una query por nivel.
    Los códigos deben venir ya validados con `validar_formato`."""
    return {
        'clase': set(ConCuentaClase.objects.filter(
            id__in={int(c[:1]) for c in codigos}).values_list('id', flat=True)),
        'grupo': set(ConCuentaGrupo.objects.filter(
            id__in={int(c[:2]) for c in codigos}).values_list('id', flat=True)),
        'cuenta': set(ConCuentaCuenta.objects.filter(
            id__in={int(c[:4]) for c in codigos}).values_list('id', flat=True)),
        'subcuenta': set(ConCuentaSubcuenta.objects.filter(
            id__in={int(c[:6]) for c in codigos}).values_list('id', flat=True)),
    }


def derivar(codigo, catalogos):
    """Nivel y FKs de catálogo del código. Clase, grupo y cuenta tienen que existir;
    la subcuenta no, porque cada empresa puede abrir subcuentas propias."""
    clase, grupo, cuenta, subcuenta = (
        int(codigo[:1]), int(codigo[:2]), int(codigo[:4]), int(codigo[:6]),
    )
    for etiqueta, valor, clave in (
        ('la clase', clase, 'clase'),
        ('el grupo', grupo, 'grupo'),
        ('la cuenta', cuenta, 'cuenta'),
    ):
        if valor not in catalogos[clave]:
            raise CuentaInvalida(f'No existe {etiqueta} {valor} del PUC para el código {codigo}')
    return {
        'nivel': len(codigo) // 2 + 1,  # 6 → 4 (subcuenta), 8 → 5, 10 → 6…
        'cuenta_clase_id': clase,
        'cuenta_grupo_id': grupo,
        'cuenta_cuenta_id': cuenta,
        'cuenta_subcuenta_id': subcuenta if subcuenta in catalogos['subcuenta'] else None,
    }


def codigo_padre(codigo):
    """El código de la cuenta de la que cuelga en `con_cuenta`; None para una subcuenta."""
    return codigo[:-2] if len(codigo) > LONGITUD_MINIMA else None


def tiene_hijas(cuenta):
    return ConCuenta.objects.filter(
        codigo__startswith=cuenta.codigo,
    ).exclude(pk=cuenta.pk).exists()


def usos(cuenta_ids):
    """
    {cuenta_id: [dónde se usa, …]} de las cuentas que algo referencia.

    Recorre todas las FKs hacia `ConCuenta` en vez de una lista a mano: una FK
    nueva queda cubierta sola. Una query por relación.
    """
    cuenta_ids = set(cuenta_ids)
    resultado = {}
    if not cuenta_ids:
        return resultado
    for relacion in ConCuenta._meta.related_objects:
        campo = relacion.field
        usadas = relacion.related_model.objects.filter(
            **{f'{campo.name}__in': cuenta_ids},
        ).values_list(campo.attname, flat=True).distinct()
        etiqueta = str(relacion.related_model._meta.verbose_name_plural).lower()
        for cuenta_id in usadas:
            lugares = resultado.setdefault(cuenta_id, [])
            if etiqueta not in lugares:
                lugares.append(etiqueta)
    return resultado


def validar_padre(padre, codigo, padre_usos):
    """Lo que exige el padre de una auxiliar. `padre_usos` es `usos()` del padre
    (lista vacía si no se usa); solo importa si el padre permite movimiento."""
    if padre.permite_movimiento and padre_usos:
        raise CuentaInvalida(
            f'La cuenta {padre.codigo} permite movimiento y ya se usa en: '
            f'{", ".join(padre_usos)}. Traslade o cambie esas referencias antes de '
            f'crearle la auxiliar {codigo}'
        )


def mensaje_padre_inexistente(codigo):
    return f'No existe la cuenta {codigo_padre(codigo)}: créela antes que su auxiliar {codigo}'


def apagar_movimiento(cuenta_ids):
    """Las cuentas que acaban de recibir una auxiliar dejan de permitir movimiento."""
    if cuenta_ids:
        ConCuenta.objects.filter(
            pk__in=cuenta_ids, permite_movimiento=True,
        ).update(permite_movimiento=False)
