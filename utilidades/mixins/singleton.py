"""
Mixin para modelos de fila única (singleton) por tenant.

`GenConfiguracion` y `GenParametro` son la misma forma: una sola fila con
`id=1` en el schema del tenant. Lo que cambia entre ellos es si además se puede
escribir, y eso lo agrega cada ViewSet por su cuenta.

**No hay lectura completa.** `campos` es la única forma de leer, y exige decir
qué se quiere. La razón es que un singleton de configuración solo crece: nace con
cinco columnas y termina con cincuenta, y entre ellas aparece alguna grande —el
logotipo de la empresa llegó a pesar 70 veces más que todos los demás campos
juntos—. Con una lectura completa disponible, toda pantalla la usa, y a nadie le
consta cuánto está trayendo ni cuándo empezó a doler.

Quien de verdad necesite todo lo pide entero y explícito
(`?campos=a,b,c,...`): sigue siendo posible, pero es una decisión visible en el
llamado y no el camino de menor resistencia.

Además de las columnas, `campos` acepta los campos de solo lectura del serializer
que leen de un relacionado (`source='ven_item_administracion.nombre'`): salen en
la misma consulta, con un JOIN. Qué se puede pedir lo dice el serializer, no una
convención de nombres.
"""
from django.db.models import F
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response


class SingletonMixin:
    """
    Requiere `modelo_singleton` (la clase del modelo) y `serializer_class`.
    La fila se crea al primer acceso: el tenant recién creado todavía no la tiene.
    """

    modelo_singleton = None
    id_singleton = 1

    def _obtener_instancia(self):
        instancia, _ = self.modelo_singleton.objects.get_or_create(id=self.id_singleton)
        return instancia

    def _campos_relacionados(self):
        """
        Los campos del serializer que se leen de un relacionado, con su ruta del
        ORM: `{'ven_item_administracion_nombre': 'ven_item_administracion__nombre'}`.
        Solo los de solo lectura con `source` anidado; los demás son columnas.
        """
        return {
            nombre: campo.source.replace('.', '__')
            for nombre, campo in self.get_serializer_class()().fields.items()
            if campo.read_only and '.' in (campo.source or '')
        }

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'campos', str,
                description=(
                    'Campos separados por coma, ej: gen_uvt,hum_salario_minimo. '
                    'Obligatorio: no hay lectura completa, y pedir todo exige '
                    'nombrarlo todo. Además de las columnas acepta los campos de '
                    'un relacionado que expone el serializer, ej: '
                    'ven_item_administracion_nombre.'
                ),
            ),
        ],
    )
    @action(detail=False, methods=['get'])
    def campos(self, request):
        solicitados = []
        for valor in request.query_params.getlist('campos'):
            solicitados.extend(c.strip() for c in valor.split(',') if c.strip())

        if not solicitados:
            return Response(
                {'detail': 'Debe indicar al menos un campo en el parámetro "campos".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        columnas = {f.name for f in self.modelo_singleton._meta.concrete_fields}
        relacionados = self._campos_relacionados()
        invalidos = [c for c in solicitados if c not in columnas and c not in relacionados]
        if invalidos:
            return Response(
                {'detail': f'Campos no válidos: {", ".join(invalidos)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self._obtener_instancia()  # garantiza que la fila exista
        # quita duplicados preservando el orden solicitado
        unicos = list(dict.fromkeys(solicitados))
        datos = self.modelo_singleton.objects.filter(id=self.id_singleton).values(
            *(c for c in unicos if c in columnas),
            **{c: F(relacionados[c]) for c in unicos if c not in columnas},
        ).first()
        return Response({c: datos[c] for c in unicos})
