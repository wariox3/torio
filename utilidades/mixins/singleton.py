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
"""
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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'campos', str,
                description=(
                    'Campos separados por coma, ej: gen_uvt,hum_salario_minimo. '
                    'Obligatorio: no hay lectura completa, y pedir todo exige '
                    'nombrarlo todo.'
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

        permitidos = {f.name for f in self.modelo_singleton._meta.concrete_fields}
        invalidos = [c for c in solicitados if c not in permitidos]
        if invalidos:
            return Response(
                {'detail': f'Campos no válidos: {", ".join(invalidos)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self._obtener_instancia()  # garantiza que la fila exista
        # quita duplicados preservando el orden solicitado
        unicos = list(dict.fromkeys(solicitados))
        datos = self.modelo_singleton.objects.filter(id=self.id_singleton).values(*unicos).first()
        return Response(datos)
