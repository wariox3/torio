from rest_framework import serializers

from contabilidad.models import ConCentroCosto
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
    DOCUMENTO_CLASE_NOTA_AJUSTE,
    DOCUMENTO_CLASES_CON_RESOLUCION,
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
                    # La factura de venta y el documento soporte se numeran
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
