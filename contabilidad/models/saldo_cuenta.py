from django.db import models


class ConSaldoCuenta(models.Model):
    """
    Movimiento consolidado de un periodo por cuenta.

    Es una tabla derivada: todo lo que está acá se puede reconstruir sumando
    `con_movimiento`. Existe para que el saldo anterior de un informe no tenga
    que barrer el histórico completo de movimientos: un tenant con 20 millones
    de movimientos tiene apenas unos miles de filas acá (cuentas con movimiento
    × 13 periodos al año).

    Guarda el **movimiento del periodo**, no el saldo acumulado. El acumulado se
    leería de una sola fila, pero obliga a reescribir todas las filas
    posteriores de la cuenta cada vez que aparece un movimiento retroactivo, y
    en contabilidad eso es rutina. Con el movimiento por periodo, un ajuste en
    2024-03 ensucia una sola fila, y el saldo anterior se calcula sumando los
    periodos previos: unos miles de filas, no millones.

    No lleva centro de costo ni tercero: consolida la cuenta completa. Un
    informe filtrado por esas dimensiones no puede usar esta tabla y tiene que
    agregar sobre `con_movimiento`.

    Nada escribe esta tabla todavía. La consolidación va en la transacción que
    bloquea un periodo — un periodo bloqueado es inmutable, así que su fila es
    definitiva — y desbloquear tiene que borrarla. Mientras eso no exista, y
    mientras no se impida crear movimientos en un periodo bloqueado, la tabla no
    es fuente confiable de nada.
    """

    debito = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    credito = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    periodo = models.ForeignKey(
        'contabilidad.ConPeriodo', on_delete=models.PROTECT,
        related_name='saldos_periodo_rel',
    )
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta', on_delete=models.PROTECT,
        related_name='saldos_cuenta_rel',
    )

    class Meta:
        db_table = 'con_saldo_cuenta'
        ordering = ['-id']
        verbose_name = 'Saldo de cuenta'
        verbose_name_plural = 'Saldos de cuenta'
        constraints = [
            # Una cuenta tiene un solo consolidado por periodo. Sin la
            # restricción, dos consolidaciones simultáneas del mismo periodo
            # crean dos filas y el saldo anterior queda contado doble.
            models.UniqueConstraint(
                fields=['periodo', 'cuenta'],
                name='con_saldo_cuenta_periodo_cuenta_unico',
            ),
        ]

    def __str__(self):
        return f'{self.periodo_id} - {self.cuenta_id}: {self.debito} / {self.credito}'
