import datetime
from collections import defaultdict
from decimal import Decimal

from rest_framework import serializers

from contabilidad.models import (
    ConCentroCosto,
    ConComprobante,
    ConCuenta,
    ConMovimiento,
    ConPeriodo,
)
from general.models import GenContacto
from general.serializers.documento_detalle_importar import (
    ErroresFila,
    _decimal,
    _entero_o_none,
    _indice,
    _mapa_fk,
    _PerfilContable,
    _Problemas,
    _texto_llave,
    _texto_o_none,
)
from seguridad.contexto import obtener_usuario_actual


class ConMovimientoImportarSerializer(serializers.Serializer):
    """
    Plantilla de los saldos iniciales del mayor.

    Es lo único que se importa directo a `ConMovimiento`: los demás movimientos
    los crea la contabilización de un documento. Por eso cada fila nace con
    `saldo_inicial = True`, y es lo que permite borrarla después con `eliminar`
    y `eliminar-masivo`.

    Las columnas son las de un asiento (`_PerfilContable`), con sus mismas reglas,
    para que el mayor no reciba lo que la contabilización rechazaría:

      * La cuenta va por código PUC, el contacto por número de identificación y el
        centro de costo por código; el comprobante por id.
      * Cada fila lleva débito o crédito, uno solo y mayor que cero; de ahí sale la
        naturaleza.
      * La cuenta debe permitir movimiento, y lo que exige (contacto, centro de
        costo, base) tiene que venir; lo que no exige, no.
      * El periodo sale de la fecha: debe existir y no estar bloqueado.
      * Cada (comprobante, número) debe cuadrar: débitos = créditos. Es el asiento
        que después borra `eliminar-masivo`, completo.

    Todo o nada: si una fila falla no se importa ninguna.
    """

    model = ConMovimiento
    nombre_archivo = 'movimientos_saldo_inicial'
    # Sin `errores_completos`: el cuadre se mide sobre el archivo entero, y si la
    # fase estructural dejara filas por fuera, un asiento sano saldría descuadrado.

    campos_excel = (
        ('comprobante.id', 'Comprobante'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('cuenta.codigo', 'Cuenta'),
        ('contacto.numero_identificacion', 'Contacto'),
        ('centro_costo.codigo', 'Centro de costo'),
        ('debito', 'Débito'),
        ('credito', 'Crédito'),
        ('base', 'Base'),
        ('detalle', 'Detalle'),
    )
    # Débito y crédito no se exigen por separado —una celda vacía vale cero—;
    # lo que se valida es el par.
    # El número es obligatorio porque (comprobante, número) es la llave con la que
    # se cuadra el asiento y con la que `eliminar-masivo` lo borra completo.
    campos_requeridos = {'comprobante.id', 'numero', 'fecha', 'cuenta.codigo'}

    valores_ejemplo = {
        'comprobante.id': (1, 1),
        'numero': (1, 1),
        'fecha': (datetime.date(2025, 12, 31), datetime.date(2025, 12, 31)),
        'cuenta.codigo': ('110505', '310505'),
        'contacto.numero_identificacion': ('', ''),
        'centro_costo.codigo': ('', ''),
        'debito': (1500000, 0),
        'credito': (0, 1500000),
        'base': (0, 0),
        'detalle': ('Saldo inicial caja', 'Saldo inicial capital'),
    }

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        comprobantes = _mapa_fk(filas_validas, 'comprobante.id', ConComprobante)
        cuentas = _indice(filas_validas, 'cuenta.codigo', ConCuenta, 'codigo', 'código')
        contactos = _indice(
            filas_validas, 'contacto.numero_identificacion', GenContacto,
            'numero_identificacion', 'número de identificación',
        )
        centros = _indice(filas_validas, 'centro_costo.codigo', ConCentroCosto, 'codigo', 'código')
        periodos = self._periodos(filas_validas)

        usuario = obtener_usuario_actual()
        correo = usuario.email if usuario is not None else None

        errores = []
        nuevos = []
        for idx, datos in filas_validas:
            try:
                nuevos.append((idx, self._construir(
                    datos, comprobantes, cuentas, contactos, centros, periodos, correo,
                )))
            except ErroresFila as e:
                errores.extend({'fila': idx, 'mensaje': m} for m in e.mensajes)
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        # Con filas malas el cuadre mediría un asiento incompleto: primero esas.
        if not errores:
            errores.extend(self._descuadres(nuevos))

        if errores:
            errores.sort(key=lambda e: e['fila'])
            return 0, errores[:self.LIMITE_ERRORES]

        ConMovimiento.objects.bulk_create(
            [movimiento for _, movimiento in nuevos], batch_size=self.BATCH_BULK_CREATE,
        )
        return len(nuevos), []

    def _construir(self, datos, comprobantes, cuentas, contactos, centros, periodos, correo):
        problemas = _Problemas()

        comprobante = problemas.intentar(lambda: self._comprobante(datos.get('comprobante.id'), comprobantes))
        cuenta = problemas.intentar(lambda: _PerfilContable._cuenta(datos.get('cuenta.codigo'), cuentas))
        naturaleza, valor = problemas.intentar(lambda: _PerfilContable._lado(datos), (None, None))
        contacto = problemas.intentar(
            lambda: contactos.opcional(datos.get('contacto.numero_identificacion'), 'Contacto'))
        centro_costo = problemas.intentar(
            lambda: centros.opcional(datos.get('centro_costo.codigo'), 'Centro de costo'))
        base = problemas.intentar(lambda: _decimal(datos.get('base'), 'Base'), Decimal('0'))
        numero = problemas.intentar(lambda: _entero_o_none(datos.get('numero'), 'Número'))

        fecha = self._fecha(datos.get('fecha'))
        periodo = problemas.intentar(lambda: self._periodo(fecha, periodos))

        # Lo que se mira es lo que trae el archivo, no lo que resolvió (ver
        # `_PerfilContable.construir`).
        if cuenta is not None:
            presentes = {
                'base': base != 0,
                'contacto': _texto_llave(datos.get('contacto.numero_identificacion')) != '',
                'centro_costo': _texto_llave(datos.get('centro_costo.codigo')) != '',
            }
            problemas.intentar(lambda: _PerfilContable._validar_exigencias(cuenta, presentes))

        problemas.levantar()

        debita = naturaleza == 'D'
        return ConMovimiento(
            comprobante=comprobante,
            numero=numero,
            fecha=fecha,
            periodo=periodo,
            cuenta=cuenta,
            contacto=contacto,
            centro_costo=centro_costo,
            naturaleza=naturaleza,
            debito=valor if debita else Decimal('0'),
            credito=Decimal('0') if debita else valor,
            base=base,
            detalle=_texto_o_none(datos.get('detalle')),
            saldo_inicial=True,
            usuario=correo,
        )

    # ---- helpers ----

    @staticmethod
    def _fecha(valor):
        # La fase estructural ya garantizó que es una fecha; Excel la entrega como datetime.
        return valor.date() if isinstance(valor, datetime.datetime) else valor

    def _periodos(self, filas_validas):
        ids = {
            ConPeriodo.calcular_id(fecha.year, fecha.month)
            for fecha in (self._fecha(datos.get('fecha')) for _, datos in filas_validas)
            if fecha
        }
        return {p.id: p for p in ConPeriodo.objects.filter(id__in=ids)}

    @staticmethod
    def _periodo(fecha, periodos):
        periodo_id = ConPeriodo.calcular_id(fecha.year, fecha.month)
        periodo = periodos.get(periodo_id)
        if periodo is None:
            raise ValueError(f'El periodo contable {periodo_id} no existe')
        if periodo.estado_bloqueado:
            raise ValueError(f'El periodo {periodo_id} está bloqueado')
        return periodo

    @staticmethod
    def _comprobante(valor, mapa):
        try:
            pk = int(valor)
        except (TypeError, ValueError):
            raise ValueError(f'Comprobante debe ser un número (ID), recibido: "{valor}"')
        comprobante = mapa.get(pk)
        if comprobante is None:
            raise ValueError(f'Comprobante con id={pk} no existe')
        return comprobante

    @staticmethod
    def _descuadres(nuevos):
        """
        Cada (comprobante, número) es un asiento y debe cuadrar.

        El error se reporta en la primera fila del grupo, porque el problema no es
        de una fila sino del conjunto.
        """
        grupos = defaultdict(lambda: {'fila': None, 'debito': Decimal('0'), 'credito': Decimal('0')})
        for idx, movimiento in nuevos:
            grupo = grupos[(movimiento.comprobante_id, movimiento.numero)]
            if grupo['fila'] is None:
                grupo['fila'] = idx
            grupo['debito'] += movimiento.debito
            grupo['credito'] += movimiento.credito

        errores = []
        for (comprobante_id, numero), grupo in grupos.items():
            if grupo['debito'] != grupo['credito']:
                diferencia = grupo['debito'] - grupo['credito']
                errores.append({
                    'fila': grupo['fila'],
                    'mensaje': (
                        f'El comprobante {comprobante_id} número {numero} está descuadrado: '
                        f'débito {grupo["debito"]} contra crédito {grupo["credito"]} '
                        f'(diferencia {diferencia})'
                    ),
                })
        return errores
