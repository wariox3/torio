from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import CharField, Sum
from django.db.models.functions import Cast, TruncMonth
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from contabilidad.servicios import depreciacion as depreciacion_servicio
from contabilidad.models import ConCentroCosto
from general.models import GenDocumento, GenResolucion, GenSede
from general.serializers import (
    GenDocumentoCrearSerializer,
    GenDocumentoExportarSerializer,
    GenDocumentoGenerarRecurrenteSerializer,
    GenDocumentoImportarSerializer,
    GenDocumentoReferenciaSeleccionarSerializer,
    GenDocumentoSerializer,
)
from general.servicios import cartera as cartera_servicio
from general.servicios import contabilizar as contabilizar_servicio
from general.servicios import documento as documento_servicio
from general.servicios import documento_imprimir
from general.servicios import factura_electronica as factura_electronica_servicio
from general.servicios import venta as venta_servicio
from seguridad.permissions import EsMiembroDelTenant, SuscripcionVigente, TienePermisoModelo
from utilidades.filtros import aplicar_filtros
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.mixins.filtros import BusquedaRequest
from utilidades.paginacion import SeleccionarPaginacion


class DocumentoAccionRequestSerializer(serializers.Serializer):
    """Un documento sobre el que actuar. El id va crudo al servicio, que es quien
    resuelve la fila con `select_for_update` y responde 404 si no existe."""

    id = serializers.IntegerField(min_value=1, help_text='Id del documento.')


class DocumentoIdsRequestSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text='Ids de los documentos a procesar.',
    )


class DocumentoActualizarElectronicoRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, help_text='Id del documento.')
    numero = serializers.IntegerField(min_value=1, required=False)
    resolucion = serializers.PrimaryKeyRelatedField(
        queryset=GenResolucion.objects.all(), required=False,
    )
    fecha = serializers.DateField(required=False)
    fecha_vence = serializers.DateField(required=False)


class DocumentoActualizarContabilidadDetalleSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, help_text='Id del detalle.')
    centro_costo = serializers.PrimaryKeyRelatedField(
        queryset=ConCentroCosto.objects.all(), allow_null=True,
    )


class DocumentoActualizarContabilidadRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, help_text='Id del documento.')
    sede = serializers.PrimaryKeyRelatedField(
        queryset=GenSede.objects.all(), required=False, allow_null=True,
    )
    detalles = DocumentoActualizarContabilidadDetalleSerializer(many=True, required=False)


_SELECCIONAR_REFERENCIA_PARAMS = [
    OpenApiParameter('contacto_id', int, required=True, description='Contacto dueño de los documentos'),
    OpenApiParameter(
        'documento_clase_id', int, required=True,
        description='Clase de los documentos a referenciar (100 factura venta, 300 compra)',
    ),
    OpenApiParameter('search', str, description='Buscar por número'),
    OpenApiParameter('con_pendiente', bool, description='Solo los que tienen saldo pendiente'),
    OpenApiParameter('electronico', bool, description='Solo los validados por la DIAN'),
]


@extend_schema(tags=['Documento'])
class GenDocumentoViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    ImportarExcelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenDocumentoSerializer
    serializer_class_exportar = GenDocumentoExportarSerializer
    serializer_class_importar = GenDocumentoImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_serializer_class(self):
        if self.action == 'create':
            return GenDocumentoCrearSerializer
        return GenDocumentoSerializer

    def get_queryset(self):
        select = GenDocumentoSerializer.select_related_lista
        return GenDocumento.objects.select_related(*select)

    def update(self, request, *args, **kwargs):
        instancia = self.get_object()
        if not instancia.es_mutable():
            raise ValidationError('El documento no es modificable.')
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            try:
                documento = GenDocumento.objects.select_for_update().get(pk=kwargs['pk'])
            except GenDocumento.DoesNotExist:
                raise NotFound('Documento no encontrado.')
            if not documento.es_mutable():
                raise ValidationError('El documento no es modificable.')
            documento.documentos_detalles_documento_rel.all().delete()
            # Un documento modificable puede tener pagos registrados, y la FK los
            # protege: sin esto el borrado falla con `ProtectedError`.
            documento.documentos_pagos_documento.all().delete()
            documento.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _queryset_imprimir(self, request):
        filtros = request.data.get('filtros') or []
        if not filtros:
            raise ValidationError('Debe enviar al menos un filtro para imprimir.')
        campos_filtrables = self._config_lista('campos_filtrables', set())
        qs = self.get_queryset().select_related(
            # `cuenta_banco__cuenta` y el documento afectado los lee el formato
            # del egreso y del pago; sin esto serían una consulta por línea impresa.
            'documento_tipo', 'contacto', 'cuenta_banco__cuenta',
            # Lo que lee la factura de venta: su resolución, cómo se paga y los
            # datos del adquiriente.
            'resolucion', 'metodo_pago', 'plazo_pago', 'cuenta_banco__cuenta_banco_tipo',
            'contacto__identificacion', 'contacto__ciudad',
        ).prefetch_related(
            'documentos_detalles_documento_rel__item',
            'documentos_detalles_documento_rel__cuenta',
            'documentos_detalles_documento_rel__contacto',
            'documentos_detalles_documento_rel__documento_afectado',
        )
        qs = aplicar_filtros(qs, filtros, campos_filtrables)
        if qs.count() > 50:
            raise ValidationError(
                'No se pueden imprimir más de 50 documentos a la vez. Afine los filtros.'
            )
        return qs

    @extend_schema(
        summary='Obsoleto: use documento/generar-recurrente/',
        description=(
            'Reemplazado por `documento/generar-recurrente/`, que recibe los ids y '
            'resuelve solo qué hacer con cada uno según su tipo. La generación de '
            'contratos de servicio (tipo 34) vive ahora ahí.'
        ),
        request=None,
        responses={400: OpenApiTypes.OBJECT},
        deprecated=True,
    )
    @action(detail=False, methods=['post'])
    def generar(self, request):
        raise ValidationError(
            {'detail': 'Endpoint retirado. Use documento/generar-recurrente/.'}
        )

    @extend_schema(request=DocumentoAccionRequestSerializer, responses=GenDocumentoSerializer)
    @extend_schema(
        summary='Generar documentos desde plantillas recurrentes',
        description=(
            'Genera un documento nuevo del `documento_tipo_destino` indicado desde cada '
            'plantilla recurrente, para el periodo `anio`/`mes`.\n\n'
            'Las plantillas se eligen con `documento_tipo_origen` (todas las de ese '
            'tipo), con `documento_ids`, o con los dos a la vez, donde los ids acotan '
            'la selección del tipo. Hay que mandar al menos uno de los dos.\n\n'
            '- **16 y 32** (factura de venta y de compra recurrente): se copian enteras '
            'con sus detalles e impuestos. Se emiten **con fecha de hoy** y vencen a los '
            'días del plazo de pago del origen.\n'
            '- **34** (contrato de servicio): los detalles se recortan a la ventana del '
            'periodo y se les recalculan horas, diurnas, nocturnas y días contra el '
            'calendario real con sus festivos.\n\n'
            'Solo se toman las plantillas con fecha hasta el último día del periodo, y '
            'cada una que genera avanza su fecha al primer día del mes siguiente: volver '
            'a generar el mismo periodo no la toma otra vez.\n\n'
            'El documento nuevo nace sin numerar y sin aprobar. Es una sola transacción: '
            'si un documento falla, no se crea ninguno.\n\n'
            'Responde `{"generados": <n>}` con la cantidad creada.'
        ),
        request=GenDocumentoGenerarRecurrenteSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'], url_path='generar-recurrente')
    def generar_recurrente(self, request):
        serializer = GenDocumentoGenerarRecurrenteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        tipo_origen = datos.get('documento_tipo_origen')
        generados = documento_servicio.generar_recurrente(
            documento_tipo_destino_id=datos['documento_tipo_destino'].pk,
            anio=datos['anio'],
            mes=datos['mes'],
            documento_ids=datos.get('documento_ids'),
            documento_tipo_origen_id=tipo_origen.pk if tipo_origen else None,
        )
        return Response({'generados': len(generados)}, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Validar la cartera',
        description=(
            'Recalcula desde su origen `pago`, `afectado` y `pendiente` de los '
            'documentos de cuentas por cobrar (`tipo: "cobrar"`) o por pagar '
            '(`tipo: "pagar"`) y corrige los que no coinciden con lo guardado; los '
            'que cuadran no se tocan. Lo puede correr cualquier miembro del '
            'contenedor.\n\n'
            'Responde `{"ejecutado": true}` cuando el proceso termina.'
        ),
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
    )
    @action(
        detail=False, methods=['post'], url_path='cartera-validar',
        permission_classes=[EsMiembroDelTenant, SuscripcionVigente],
    )
    def cartera_validar(self, request):
        tipo = request.data.get('tipo')
        if tipo not in cartera_servicio.TIPOS:
            raise ValidationError({'detail': 'El tipo debe ser "cobrar" o "pagar".'})
        cartera_servicio.validar(tipo)
        return Response({'ejecutado': True}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Validar la depreciación de los activos',
        description=(
            'Recalcula desde su origen `depreciacion_acumulada` y '
            '`depreciacion_saldo` de todos los activos —lo acumulado es la suma de '
            'sus líneas de depreciación en documentos aprobados y sin anular— y '
            'corrige los que no coinciden con lo guardado; los que cuadran no se '
            'tocan. Lo puede correr cualquier miembro del contenedor.\n\n'
            'Responde `{"ejecutado": true}` cuando el proceso termina.'
        ),
        request=None,
        responses=OpenApiTypes.OBJECT,
    )
    @action(
        detail=False, methods=['post'], url_path='depreciacion-validar',
        permission_classes=[EsMiembroDelTenant, SuscripcionVigente],
    )
    def depreciacion_validar(self, request):
        depreciacion_servicio.recalcular_activos()
        return Response({'ejecutado': True}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Resumen de la cartera',
        description=(
            'Cifras del tablero de cuentas por cobrar (`?tipo=cobrar`) o por pagar '
            '(`?tipo=pagar`), sobre los mismos documentos de los informes '
            '`cobrar_pendiente` y `pagar_pendiente`. Un documento sin `fecha_vence` '
            'vence en su `fecha`.\n\n'
            '- `total_pendiente`, `total_pendiente_vencido` (vence antes de hoy) y '
            '`total_pendiente_vigente` (vence hoy o después); los dos últimos suman '
            'el primero.'
        ),
        parameters=[
            OpenApiParameter(
                'tipo', OpenApiTypes.STR, required=True, enum=['cobrar', 'pagar'],
                description='Lado de la cartera.',
            ),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    @action(
        detail=False, methods=['get'], url_path='cartera-resumen',
        permission_classes=[EsMiembroDelTenant, SuscripcionVigente],
    )
    def cartera_resumen(self, request):
        tipo = request.query_params.get('tipo')
        if tipo not in cartera_servicio.TIPOS:
            raise ValidationError({'detail': 'El tipo debe ser "cobrar" o "pagar".'})
        return Response(cartera_servicio.resumen(tipo), status=status.HTTP_200_OK)

    @extend_schema(
        summary='Resumen de ventas',
        description=(
            'Venta neta del periodo en curso para el tablero: documentos de venta '
            'aprobados y no anulados, por su `fecha`; la nota crédito resta.\n\n'
            '- `?periodo=mes`: el mes actual, un punto por día en `serie`.\n'
            '- `?periodo=anio`: el año actual, un punto por mes en `serie`.\n\n'
            'Los días o meses sin ventas salen en cero. `totales` suma la serie.'
        ),
        parameters=[
            OpenApiParameter(
                'periodo', OpenApiTypes.STR, required=True, enum=list(venta_servicio.PERIODOS),
                description='Rango de `fecha` a resumir.',
            ),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    @action(
        detail=False, methods=['get'], url_path='venta-resumen',
        permission_classes=[EsMiembroDelTenant, SuscripcionVigente],
    )
    def venta_resumen(self, request):
        periodo = request.query_params.get('periodo')
        if periodo not in venta_servicio.PERIODOS:
            raise ValidationError({'detail': 'El periodo debe ser "mes" o "anio".'})
        return Response(venta_servicio.resumen(periodo), status=status.HTTP_200_OK)

    @extend_schema(
        summary='Documentos que puede referenciar una nota',
        description=(
            'Documentos aprobados y no anulados de un contacto y una clase, para el '
            'selector de `documento_referencia` de una nota crédito o débito. '
            'Del más reciente al más antiguo.'
        ),
        parameters=_SELECCIONAR_REFERENCIA_PARAMS,
        responses=GenDocumentoReferenciaSeleccionarSerializer(many=True),
    )
    @action(
        detail=False, methods=['get'], url_path='seleccionar-referencia',
        pagination_class=SeleccionarPaginacion,
    )
    def seleccionar_referencia(self, request):
        parametros = {}
        for parametro in ('contacto_id', 'documento_clase_id'):
            valor = request.query_params.get(parametro, '').strip()
            if not valor:
                raise ValidationError({'detail': f'El parámetro {parametro} es obligatorio.'})
            try:
                parametros[parametro] = int(valor)
            except ValueError:
                raise ValidationError({'detail': f'El parámetro {parametro} debe ser un número entero.'})

        qs = GenDocumento.objects.select_related('documento_tipo', 'resolucion').filter(
            contacto_id=parametros['contacto_id'],
            documento_tipo__documento_clase_id=parametros['documento_clase_id'],
            estado_aprobado=True,
            estado_anulado=False,
        ).order_by('-fecha', '-numero', '-id')

        if request.query_params.get('con_pendiente', '').lower() == 'true':
            qs = qs.filter(pendiente__gt=0)
        if request.query_params.get('electronico', '').lower() == 'true':
            qs = qs.filter(estado_electronico=True)

        search = request.query_params.get('search', '').strip()
        if search:
            if not search.isdigit():
                raise ValidationError({'detail': 'El parámetro search debe ser un número.'})
            qs = qs.annotate(numero_texto=Cast('numero', CharField())).filter(
                numero_texto__startswith=search,
            )

        pagina = self.paginate_queryset(qs)
        serializer = GenDocumentoReferenciaSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['post'])
    def aprobar(self, request):
        serializer = DocumentoAccionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documento = documento_servicio.aprobar(serializer.validated_data['id'])
        salida = GenDocumentoSerializer(documento)
        return Response(salida.data, status=status.HTTP_200_OK)

    @extend_schema(request=DocumentoAccionRequestSerializer, responses=GenDocumentoSerializer)
    @action(detail=False, methods=['post'])
    def desaprobar(self, request):
        serializer = DocumentoAccionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documento = documento_servicio.desaprobar(serializer.validated_data['id'])
        salida = GenDocumentoSerializer(documento)
        return Response(salida.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Anular un documento',
        description=(
            'Deja un documento aprobado sin valor: revierte lo que hizo la aprobación '
            '(cartera, afectaciones, nota crédito e inventario) y pone en cero los '
            'valores del documento, sus detalles y sus impuestos. Conserva el número '
            'y el aprobado.\n\n'
            'No se anula un documento sin aprobar, ya anulado, contabilizado (hay que '
            'descontabilizarlo primero), enviado electrónicamente, ni uno que otro '
            'documento vigente esté afectando. Tampoco si revertir su inventario deja '
            'en negativo un item que no lo admite.\n\n'
            'Responde el documento anulado.'
        ),
        request=DocumentoAccionRequestSerializer,
        responses=GenDocumentoSerializer,
    )
    @action(detail=False, methods=['post'])
    def anular(self, request):
        serializer = DocumentoAccionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documento = documento_servicio.anular(serializer.validated_data['id'])
        salida = GenDocumentoSerializer(documento)
        return Response(salida.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Corregir los datos electrónicos de un documento',
        description=(
            'Cambia el `numero`, la `resolucion`, la `fecha` o la `fecha_vence` de un '
            'documento, aunque esté aprobado. Solo se cambia lo que se envíe, y hay '
            'que enviar al menos uno.\n\n'
            'No se corrige un documento anulado, contabilizado ni ya enviado '
            'electrónicamente. El número tiene que caer en el rango de la resolución '
            'que quede y no repetirse en otro documento del mismo tipo y resolución; '
            'en la factura de venta la fecha tiene que estar dentro de la vigencia. '
            'La fecha de vencimiento no puede ser anterior a la fecha.\n\n'
            'El consecutivo del tipo de documento no se mueve. `fecha_contable` sigue '
            'a `fecha` si venían iguales.\n\n'
            'Responde el documento actualizado; un rechazo responde 400 con el motivo '
            'en `detail`.'
        ),
        request=DocumentoActualizarElectronicoRequestSerializer,
        responses=GenDocumentoSerializer,
    )
    @action(detail=False, methods=['post'], url_path='actualizar-electronico')
    def actualizar_electronico(self, request):
        serializer = DocumentoActualizarElectronicoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = dict(serializer.validated_data)
        documento_id = datos.pop('id')
        if not datos:
            return Response(
                {'detail': 'Debe enviar numero, resolucion, fecha o fecha_vence.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        documento = documento_servicio.actualizar_electronico(documento_id, datos)
        salida = GenDocumentoSerializer(self.get_queryset().get(pk=documento.pk))
        return Response(salida.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Corregir los datos contables de un documento',
        description=(
            'Cambia la `sede` del documento y el `centro_costo` de los detalles que '
            'se envíen en `detalles`, aunque el documento esté aprobado o ya enviado '
            'electrónicamente. Hay que enviar `sede`, `detalles` o los dos; ambos '
            'aceptan `null` para quitar el valor.\n\n'
            'No se corrige un documento anulado ni contabilizado: hay que '
            'descontabilizarlo primero.\n\n'
            'Responde el documento actualizado. Si algún detalle no pertenece al '
            'documento no se cambia nada y responde 400 con `detail` y, en '
            '`errores`, la posición y el id de cada uno.'
        ),
        request=DocumentoActualizarContabilidadRequestSerializer,
        responses=GenDocumentoSerializer,
    )
    @action(detail=False, methods=['post'], url_path='actualizar-contabilidad')
    def actualizar_contabilidad(self, request):
        serializer = DocumentoActualizarContabilidadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = dict(serializer.validated_data)
        documento_id = datos.pop('id')
        if 'sede' not in datos and not datos.get('detalles'):
            return Response(
                {'detail': 'Debe enviar sede o detalles.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            documento = documento_servicio.actualizar_contabilidad(documento_id, datos)
        except documento_servicio.DetallesAjenos as e:
            return Response(
                {'detail': str(e), 'errores': e.errores},
                status=status.HTTP_400_BAD_REQUEST,
            )
        salida = GenDocumentoSerializer(self.get_queryset().get(pk=documento.pk))
        return Response(salida.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Cargar la depreciación del periodo',
        description=(
            'Carga en un documento de depreciación (tipo 23) una línea por cada activo '
            'que todavía tenga saldo por depreciar en el mes de la fecha del documento.\n\n'
            'El mes es comercial, de 30 días: el activo que estuvo el mes completo '
            'deprecia su cuota entera, y el que se activó o se dio de baja dentro del mes '
            'deprecia la parte proporcional a los días que estuvo. Ningún activo deprecia '
            'más que el saldo que le queda.\n\n'
            'El documento tiene que estar modificable y **sin detalles**: el cargue no '
            'descuenta el saldo del activo, así que recargar sobre un documento ya cargado '
            'depreciaría el mismo periodo dos veces. Para volver a cargar hay que borrar '
            'primero los detalles.\n\n'
            'Responde el documento con su `total` ya actualizado.'
        ),
        request=DocumentoAccionRequestSerializer,
        responses=GenDocumentoSerializer,
    )
    @action(detail=False, methods=['post'], url_path='cargar-activo')
    def cargar_activo(self, request):
        serializer = DocumentoAccionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documento = depreciacion_servicio.cargar_activos(serializer.validated_data['id'])
        salida = GenDocumentoSerializer(documento)
        return Response(salida.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Contabilizar documentos',
        description=(
            'Genera los movimientos contables de cada documento aprobado y lo marca '
            'como contabilizado. El lote va en una sola transacción: si un documento '
            'falla, no queda ninguno contabilizado.'
        ),
        request=DocumentoIdsRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'])
    def contabilizar(self, request):
        serializer = DocumentoIdsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cantidad = contabilizar_servicio.contabilizar(serializer.validated_data['ids'])
        return Response({'contabilizados': cantidad}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Descontabilizar documentos',
        description=(
            'Borra los movimientos contables de cada documento y le quita el '
            'contabilizado. Mismo criterio de transacción que `contabilizar`.'
        ),
        request=DocumentoIdsRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'])
    def descontabilizar(self, request):
        serializer = DocumentoIdsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cantidad = contabilizar_servicio.descontabilizar(serializer.validated_data['ids'])
        return Response({'descontabilizados': cantidad}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Emitir documentos electrónicos',
        description=(
            'Crea cada documento en el servicio de facturación electrónica. Cada '
            'uno va por su cuenta: el que no pasa las validaciones, o el que el '
            'servicio rechaza, no detiene a los demás. Responde 200 con `emitidos` y '
            '`con_error`, los ids de cada grupo.\n\n'
            'Los motivos no vienen en la respuesta: el documento queda con '
            '`estado_electronico_error` y sus errores se leen en '
            '`documento-electronico-error/lista/`, filtrando por `documento_id`. Cada '
            'intento reemplaza los errores del anterior. Un documento que ya estaba '
            'enviado se salta.\n\n'
            'Solo responde error lo que no es de ningún documento: 400 si la empresa '
            'no ha terminado el asistente o no tiene emisor, 404 si un id no existe y '
            '502 si el servicio no responde.'
        ),
        request=DocumentoIdsRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'])
    def emitir(self, request):
        serializer = DocumentoIdsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            datos = factura_electronica_servicio.emitir(serializer.validated_data['ids'])
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Notificar documentos electrónicos',
        description=(
            'Le entrega cada documento a su adquiriente: genera la representación '
            'gráfica y se la manda al servicio de facturación electrónica, que arma '
            'el zip con el documento validado y lo envía por correo.\n\n'
            'Solo se notifican documentos que la DIAN ya validó. Uno ya notificado '
            'se puede volver a notificar, para reenviarlo. Antes de enviar el '
            'primero se valida el lote completo; si uno no cumple, no se envía '
            'ninguno.\n\n'
            'El envío no es atómico: si el servicio rechaza un documento, los '
            'anteriores ya quedaron notificados, y el error los lista en `notificados`.'
        ),
        request=DocumentoIdsRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'])
    def notificar(self, request):
        serializer = DocumentoIdsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            notificados = factura_electronica_servicio.notificar(serializer.validated_data['ids'])
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response({'notificados': notificados}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Registro de envíos de un documento electrónico',
        description=(
            'El registro de los correos con que se le entregó el documento a su '
            'adquiriente, consultado en el servicio de correo. Responde `log`.\n\n'
            'Solo para documentos ya notificados: uno que no lo esté responde 400.'
        ),
        request=DocumentoAccionRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'], url_path='electronico-log')
    def electronico_log(self, request):
        serializer = DocumentoAccionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            log = factura_electronica_servicio.electronico_log(serializer.validated_data['id'])
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response({'log': log}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Descargar el XML de un documento electrónico',
        description=(
            'El XML firmado del documento, descargado del servicio de facturación '
            'electrónica. Responde el archivo, con el prefijo y el número del '
            'documento como nombre.\n\n'
            'Solo para documentos ya enviados electrónicamente: uno que no lo esté, '
            'o cuyo XML todavía no esté firmado, responde 400 con el motivo en '
            '`detail`. Si el servicio no responde, 502.'
        ),
        request=DocumentoAccionRequestSerializer,
        responses={(200, 'application/xml'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['post'], url_path='electronico-xml')
    def electronico_xml(self, request):
        serializer = DocumentoAccionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            contenido, nombre = factura_electronica_servicio.electronico_xml(
                serializer.validated_data['id'],
            )
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        response = HttpResponse(contenido, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response

    @extend_schema(request=BusquedaRequest, responses={(200, 'application/pdf'): OpenApiTypes.BINARY})
    @action(detail=False, methods=['post'])
    def imprimir(self, request):
        contenido, nombre = documento_imprimir.imprimir(self._queryset_imprimir(request))
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{nombre}"'
        return response

    @extend_schema(request=BusquedaRequest, responses={(200, 'application/zip'): OpenApiTypes.BINARY})
    @action(detail=False, methods=['post'], url_path='imprimir-zip')
    def imprimir_zip(self, request):
        contenido, nombre = documento_imprimir.imprimir_zip(self._queryset_imprimir(request))
        response = HttpResponse(contenido, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response

    @extend_schema(
        parameters=[
            OpenApiParameter('fecha_desde', OpenApiTypes.DATE, description='Fecha desde (AAAA-MM-DD)'),
            OpenApiParameter('fecha_hasta', OpenApiTypes.DATE, description='Fecha hasta (AAAA-MM-DD)'),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='analitica-horas')
    def analitica_horas(self, request):
        # Recuerda: en el modelo `horas` = planeado y `horas_programadas` = ejecutado.
        # Validación de parámetros inline.
        fecha_desde = None
        fecha_hasta = None
        valor = request.query_params.get('fecha_desde')
        if valor:
            try:
                fecha_desde = datetime.strptime(valor.strip(), '%Y-%m-%d').date()
            except ValueError:
                raise ValidationError({'fecha_desde': 'Formato inválido, use AAAA-MM-DD.'})
        valor = request.query_params.get('fecha_hasta')
        if valor:
            try:
                fecha_hasta = datetime.strptime(valor.strip(), '%Y-%m-%d').date()
            except ValueError:
                raise ValidationError({'fecha_hasta': 'Formato inválido, use AAAA-MM-DD.'})
        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            raise ValidationError({'fecha_desde': 'No puede ser mayor que fecha_hasta.'})

        # Solo documentos tipo 35 y válidos (aprobados y no anulados).
        qs = GenDocumento.objects.filter(
            documento_tipo_id=35, estado_aprobado=True, estado_anulado=False
        )
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)

        # Una sola query: suma por mes en la BD.
        filas = (
            qs.annotate(periodo=TruncMonth('fecha'))
            .values('periodo')
            .annotate(
                planeadas=Sum('horas'),
                ejecutadas=Sum('horas_programadas'),
                planeadas_diurnas=Sum('horas_diurnas'),
                ejecutadas_diurnas=Sum('horas_diurnas_programadas'),
                planeadas_nocturnas=Sum('horas_nocturnas'),
                ejecutadas_nocturnas=Sum('horas_nocturnas_programadas'),
            )
            .order_by('periodo')
        )

        cero = Decimal('0')

        def cumplimiento(ejecutadas, planeadas):
            if not planeadas:
                return None
            return round(float(ejecutadas / planeadas * 100), 1)

        serie = []
        tot_plan = tot_ejec = cero
        tot_plan_diu = tot_ejec_diu = cero
        tot_plan_noc = tot_ejec_noc = cero
        for fila in filas:
            planeadas = fila['planeadas'] or cero
            ejecutadas = fila['ejecutadas'] or cero
            tot_plan += planeadas
            tot_ejec += ejecutadas
            tot_plan_diu += fila['planeadas_diurnas'] or cero
            tot_ejec_diu += fila['ejecutadas_diurnas'] or cero
            tot_plan_noc += fila['planeadas_nocturnas'] or cero
            tot_ejec_noc += fila['ejecutadas_nocturnas'] or cero
            serie.append({
                'periodo': fila['periodo'].strftime('%Y-%m'),
                'planeadas': planeadas,
                'ejecutadas': ejecutadas,
                'cumplimiento': cumplimiento(ejecutadas, planeadas),
            })

        resumen = {
            'horas_planeadas': tot_plan,
            'horas_ejecutadas': tot_ejec,
            'cumplimiento': cumplimiento(tot_ejec, tot_plan),
            'desviacion': tot_ejec - tot_plan,
            'diurnas': {'planeadas': tot_plan_diu, 'ejecutadas': tot_ejec_diu},
            'nocturnas': {'planeadas': tot_plan_noc, 'ejecutadas': tot_ejec_noc},
        }

        return Response({
            'resumen': resumen,
            'serie': serie,
            'agrupado_por': 'mes',
        })
