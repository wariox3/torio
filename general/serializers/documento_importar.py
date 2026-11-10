import datetime

from rest_framework import serializers

from contabilidad.models import ConCentroCosto, ConCuenta
from general.models import (
    GenAsesor,
    GenContacto,
    GenDocumento,
    GenDocumentoConceptoCorreccion,
    GenDocumentoTipo,
    GenFormaPago,
    GenPlazoPago,
    GenSector,
)
from general.servicios.documento import (
    CONCEPTO_CORRECCION_OBLIGATORIO,
    DOCUMENTO_CLASE_DOCUMENTO_SOPORTE,
    DOCUMENTO_CLASE_FACTURA_POS,
    DOCUMENTO_CLASE_NOTA_AJUSTE,
    DOCUMENTO_CLASES_CON_RESOLUCION,
    _asignar_cartera,
)
from general.serializers.documento_detalle_importar import (
    ErroresFila,
    _decimal,
    _entero_o_none,
    _indice,
    _Problemas,
    _texto_o_none,
)


class GenDocumentoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de documentos y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])

    Las notas siguen las mismas reglas que al guardarlas por la API
    (`GenDocumentoSerializer`): concepto de corrección de su clase, obligatorio en
    la nota crédito y la de ajuste, y la de ajuste con el documento soporte que
    ajusta. Aprobada, ninguna de las dos cosas se puede completar y la nota
    nunca se emitiría.
    """

    model = GenDocumento
    nombre_archivo = 'documentos'

    campos_excel = (
        ('documento_tipo.id', 'Tipo documento'),
        ('fecha', 'Fecha'),
        ('fecha_contable', 'Fecha contable'),
        ('contacto.id', 'Contacto'),
        ('soporte', 'Soporte'),
        ('orden_compra', 'Orden compra'),
        ('remision', 'Remisión'),
        ('comentario', 'Comentario'),
        ('plazo_pago.id', 'Plazo pago'),
        ('forma_pago.id', 'Forma pago'),
        ('asesor.id', 'Asesor'),
        ('sector.id', 'Sector'),
        ('centro_costo.id', 'Centro de costo'),
        ('documento_concepto_correccion.id', 'Concepto corrección'),
        ('documento_referencia.id', 'Documento referencia'),
    )
    campos_requeridos = {'documento_tipo.id', 'fecha'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        Procesa todas las filas válidas en bulk:
          1. Pre-carga FKs en una query por modelo.
          2. Valida cada fila contra mapas en memoria (sin BD).
          3. `bulk_create` al final si no hay errores.

        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # 1) Pre-cargar FKs en mapas {id: instancia}
        ids_documento_tipo = self._ids_int(filas_validas, 'documento_tipo.id')
        ids_contacto = self._ids_int(filas_validas, 'contacto.id')
        ids_plazo_pago = self._ids_int(filas_validas, 'plazo_pago.id')
        ids_forma_pago = self._ids_int(filas_validas, 'forma_pago.id')
        ids_asesor = self._ids_int(filas_validas, 'asesor.id')
        ids_sector = self._ids_int(filas_validas, 'sector.id')
        ids_centro_costo = self._ids_int(filas_validas, 'centro_costo.id')
        ids_concepto = self._ids_int(filas_validas, 'documento_concepto_correccion.id')
        ids_referencia = self._ids_int(filas_validas, 'documento_referencia.id')

        mapa_documento_tipo = {o.id: o for o in GenDocumentoTipo.objects.filter(id__in=ids_documento_tipo)}
        mapa_contacto = {o.id: o for o in GenContacto.objects.filter(id__in=ids_contacto)}
        mapa_plazo_pago = {o.id: o for o in GenPlazoPago.objects.filter(id__in=ids_plazo_pago)}
        mapa_forma_pago = {o.id: o for o in GenFormaPago.objects.filter(id__in=ids_forma_pago)}
        mapa_asesor = {o.id: o for o in GenAsesor.objects.filter(id__in=ids_asesor)}
        mapa_sector = {o.id: o for o in GenSector.objects.filter(id__in=ids_sector)}
        mapa_centro_costo = {o.id: o for o in ConCentroCosto.objects.filter(id__in=ids_centro_costo)}
        mapa_concepto = {
            o.id: o for o in GenDocumentoConceptoCorreccion.objects.filter(id__in=ids_concepto)
        }
        mapa_referencia = {
            o.id: o for o in
            GenDocumento.objects.select_related('documento_tipo').filter(id__in=ids_referencia)
        }

        # 2) Construir instancias en memoria, recolectar errores
        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                dt_id = int(datos['documento_tipo.id'])
                documento_tipo = mapa_documento_tipo.get(dt_id)
                if documento_tipo is None:
                    raise ValueError(f'Tipo de documento con id={dt_id} no existe')

                contacto = self._fk_opcional(datos.get('contacto.id'), mapa_contacto, 'Contacto')
                plazo_pago = self._fk_opcional(datos.get('plazo_pago.id'), mapa_plazo_pago, 'Plazo pago')
                forma_pago = self._fk_opcional(datos.get('forma_pago.id'), mapa_forma_pago, 'Forma pago')
                asesor = self._fk_opcional(datos.get('asesor.id'), mapa_asesor, 'Asesor')
                sector = self._fk_opcional(datos.get('sector.id'), mapa_sector, 'Sector')
                centro_costo = self._fk_opcional(
                    datos.get('centro_costo.id'), mapa_centro_costo, 'Centro de costo')
                concepto = self._fk_opcional(
                    datos.get('documento_concepto_correccion.id'), mapa_concepto, 'Concepto corrección')
                referencia = self._fk_opcional(
                    datos.get('documento_referencia.id'), mapa_referencia, 'Documento referencia')

                clase_id = documento_tipo.documento_clase_id
                # La factura POS va siempre en un turno abierto de su cajero, que
                # el Excel no trae: se hace desde el punto de venta.
                if clase_id == DOCUMENTO_CLASE_FACTURA_POS:
                    raise ValueError('La factura POS no se importa: se hace desde un turno de caja.')
                if concepto is None and clase_id in CONCEPTO_CORRECCION_OBLIGATORIO:
                    raise ValueError(CONCEPTO_CORRECCION_OBLIGATORIO[clase_id])
                if concepto is not None and concepto.documento_clase_id != clase_id:
                    raise ValueError('El concepto de corrección no corresponde a este tipo de documento.')
                if clase_id == DOCUMENTO_CLASE_NOTA_AJUSTE:
                    if referencia is None:
                        raise ValueError('La nota de ajuste debe indicar el documento soporte que ajusta.')
                    if referencia.documento_tipo.documento_clase_id != DOCUMENTO_CLASE_DOCUMENTO_SOPORTE:
                        raise ValueError('La nota de ajuste solo puede ajustar un documento soporte.')

                fecha = datos.get('fecha')
                # Mismo default que en `GenDocumentoSerializer`: sin fecha contable
                # manda la del documento. `fecha` es obligatoria en la plantilla,
                # así que el importado nunca queda sin periodo que contabilizar.
                fecha_contable = self._fecha_o_none(datos.get('fecha_contable')) or fecha

                nuevos.append(GenDocumento(
                    documento_tipo=documento_tipo,
                    fecha=fecha,
                    fecha_contable=fecha_contable,
                    contacto=contacto,
                    soporte=self._texto_o_none(datos.get('soporte')),
                    orden_compra=self._texto_o_none(datos.get('orden_compra')),
                    remision=self._texto_o_none(datos.get('remision')),
                    comentario=self._texto_o_none(datos.get('comentario')),
                    plazo_pago=plazo_pago,
                    forma_pago=forma_pago,
                    asesor=asesor,
                    sector=sector,
                    centro_costo=centro_costo,
                    documento_concepto_correccion=concepto,
                    documento_referencia=referencia,
                    # La factura de venta, la POS y el documento soporte se numeran
                    # contra la resolución de su tipo, igual que al guardarlos por
                    # la API (`GenDocumentoSerializer._heredar_resolucion`). El
                    # Excel no trae resolución: los demás tipos quedan sin ella.
                    resolucion_id=(
                        documento_tipo.resolucion_id
                        if documento_tipo.documento_clase_id in DOCUMENTO_CLASES_CON_RESOLUCION
                        else None
                    ),
                ))
            except Exception as e:  # noqa: BLE001 — el error de la fila se reporta al usuario
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        # 3) Bulk create (solo si no hubo errores)
        if errores:
            return 0, errores

        if nuevos:
            GenDocumento.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    @staticmethod
    def _ids_int(filas_validas, campo):
        ids = set()
        for _, datos in filas_validas:
            valor = datos.get(campo)
            if valor in (None, ''):
                continue
            try:
                ids.add(int(valor))
            except (TypeError, ValueError):
                pass
        return ids

    @staticmethod
    def _fk_opcional(valor, mapa, etiqueta):
        if valor in (None, ''):
            return None
        try:
            pk = int(valor)
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número (PK), recibido: "{valor}"')
        obj = mapa.get(pk)
        if obj is None:
            raise ValueError(f'{etiqueta} con id={pk} no existe')
        return obj

    @staticmethod
    def _texto_o_none(v):
        if v is None or v == '':
            return None
        return str(v).strip()

    @staticmethod
    def _fecha_o_none(v):
        if v is None or v == '':
            return None
        return v


class GenDocumentoSaldoInicialImportarSerializer(serializers.Serializer):
    """
    Plantilla de los saldos iniciales: SALDO INICIAL CXC (clase 201) y CXP (401).

    Un saldo inicial es un documento abierto que se trae del sistema anterior: la
    factura que el cliente todavía debe, o la que se le debe al proveedor. No tiene
    líneas, así que el `total` viene en el Excel y no de `recalcular_totales`.
    Cada fila nace aprobada con su saldo (`_asignar_cartera`), igual que en itrio:
    no hay nada que revisar antes, y en borrador no se podría cobrar ni pagar.

    El tipo no viaja en el Excel: lo manda el front en `documento_tipo_id`. El
    contacto va por número de identificación y la cuenta por código, que es lo
    que el usuario tiene a mano; los ids no los conoce.

    Un saldo ya importado (mismo tipo, número y contacto) se rechaza: el importar
    solo crea.
    """

    model = GenDocumento
    nombre_archivo = 'saldos_iniciales'
    errores_completos = True

    campos_excel = (
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('fecha_vence', 'Fecha vence'),
        ('contacto.numero_identificacion', 'Contacto'),
        ('cuenta.codigo', 'Cuenta'),
        ('total', 'Total'),
        ('comentario', 'Comentario'),
    )
    campos_requeridos = {
        'numero', 'fecha', 'fecha_vence', 'contacto.numero_identificacion', 'cuenta.codigo', 'total',
    }

    # La cuenta de ejemplo según el lado: clientes nacionales o proveedores.
    CUENTA_EJEMPLO = {201: '130505', 401: '220505'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def __init__(self, documento_tipo, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.documento_tipo = documento_tipo
        cuenta = self.CUENTA_EJEMPLO.get(documento_tipo.documento_clase_id, '')
        self.valores_ejemplo = {
            'numero': (1001, 1002),
            'fecha': (datetime.date(2025, 11, 15), datetime.date(2025, 12, 20)),
            'fecha_vence': (datetime.date(2025, 12, 15), datetime.date(2026, 2, 18)),
            'contacto.numero_identificacion': ('123456789', '900123456'),
            'cuenta.codigo': (cuenta, cuenta),
            'total': (250000, 1200000),
            'comentario': ('', ''),
        }

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        contactos = _indice(
            filas_validas, 'contacto.numero_identificacion', GenContacto,
            'numero_identificacion', 'número de identificación',
        )
        cuentas = _indice(filas_validas, 'cuenta.codigo', ConCuenta, 'codigo', 'código')

        errores = []
        nuevos = []
        vistos = {}
        for idx, datos in filas_validas:
            problemas = _Problemas()
            contacto = problemas.intentar(
                lambda: contactos.obligatorio(datos.get('contacto.numero_identificacion'), 'Contacto'))
            cuenta = problemas.intentar(lambda: self._cuenta(datos.get('cuenta.codigo'), cuentas))
            numero = problemas.intentar(lambda: _entero_o_none(datos.get('numero'), 'Número'))
            total = problemas.intentar(lambda: _decimal(datos.get('total'), 'Total'))
            if total is not None and total <= 0:
                problemas.mensajes.append('Total debe ser mayor que cero')

            fecha = datos.get('fecha')
            fecha_vence = datos.get('fecha_vence')
            if fecha and fecha_vence and fecha_vence < fecha:
                problemas.mensajes.append('Fecha vence no puede ser anterior a la fecha')

            # El mismo saldo dos veces en el archivo.
            if numero is not None and contacto is not None:
                clave = (numero, contacto.pk)
                if clave in vistos:
                    problemas.mensajes.append(
                        f'El número {numero} de este contacto ya está en la fila {vistos[clave]}')
                else:
                    vistos[clave] = idx

            try:
                problemas.levantar()
            except ErroresFila as e:
                errores.extend({'fila': idx, 'mensaje': m} for m in e.mensajes)
                if len(errores) >= self.LIMITE_ERRORES:
                    break
                continue

            documento = GenDocumento(
                documento_tipo=self.documento_tipo,
                numero=numero,
                fecha=fecha,
                fecha_contable=fecha,
                fecha_vence=fecha_vence,
                contacto=contacto,
                cuenta=cuenta,
                subtotal=total,
                total=total,
                comentario=_texto_o_none(datos.get('comentario')),
                estado_aprobado=True,
            )
            _asignar_cartera(documento)
            nuevos.append((idx, documento))

        # Lo que ya está importado: mismo tipo, número y contacto.
        if nuevos and len(errores) < self.LIMITE_ERRORES:
            existentes = set(
                GenDocumento.objects.filter(
                    documento_tipo=self.documento_tipo,
                    numero__in={d.numero for _, d in nuevos},
                    contacto_id__in={d.contacto_id for _, d in nuevos},
                ).values_list('numero', 'contacto_id')
            )
            for idx, documento in nuevos:
                if (documento.numero, documento.contacto_id) in existentes:
                    errores.append({
                        'fila': idx,
                        'mensaje': f'Ya existe el saldo inicial número {documento.numero} de este contacto',
                    })

        if errores:
            errores.sort(key=lambda e: e['fila'])
            return 0, errores[:self.LIMITE_ERRORES]

        GenDocumento.objects.bulk_create(
            [documento for _, documento in nuevos], batch_size=self.BATCH_BULK_CREATE,
        )
        return len(nuevos), []

    @staticmethod
    def _cuenta(codigo, indice):
        cuenta = indice.obligatorio(codigo, 'Cuenta')
        if not cuenta.permite_movimiento:
            raise ValueError(f'La cuenta {cuenta.codigo} no permite movimientos')
        return cuenta


# Clase de documento → plantilla de importación. Una clase que no esté acá usa la
# general (`GenDocumentoImportarSerializer`), con el tipo como columna del Excel.
IMPORTAR_POR_CLASE = {
    201: GenDocumentoSaldoInicialImportarSerializer,
    401: GenDocumentoSaldoInicialImportarSerializer,
}
