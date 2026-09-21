import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from utilidades.excepciones import con_detail, manejador_excepciones

RAIZ = Path(settings.BASE_DIR)


class ConDetailTests(SimpleTestCase):

    def test_un_dict_con_detail_pasa_tal_cual(self):
        cuerpo = {'detail': 'Ya existe.', 'codigo': 'duplicado'}
        self.assertEqual(con_detail(cuerpo), cuerpo)

    def test_una_lista_de_mensajes_se_vuelve_detail(self):
        self.assertEqual(con_detail(['El documento 7 ya fue enviado.']),
                         {'detail': 'El documento 7 ya fue enviado.'})

    def test_varios_mensajes_se_unen(self):
        self.assertEqual(con_detail(['Uno.', 'Dos.']), {'detail': 'Uno. Dos.'})

    def test_un_error_por_campo_conserva_el_campo_y_gana_detail(self):
        self.assertEqual(con_detail({'ids': ['Este campo es requerido.']}), {
            'detail': 'ids: Este campo es requerido.',
            'ids': ['Este campo es requerido.'],
        })

    def test_non_field_errors_va_sin_prefijo(self):
        self.assertEqual(con_detail({'non_field_errors': ['No cuadra.']})['detail'], 'No cuadra.')

    def test_un_error_anidado_lleva_la_ruta(self):
        cuerpo = {'detalles': [{}, {'impuestos': [{'tributo': ['No admitido.']}]}]}
        self.assertEqual(con_detail(cuerpo)['detail'], 'detalles.impuestos.tributo: No admitido.')

    def test_sin_mensajes_usa_el_generico(self):
        self.assertEqual(con_detail({'documento': 7})['detail'], 'La petición no se pudo procesar.')
        self.assertEqual(con_detail(None)['detail'], 'La petición no se pudo procesar.')


class _Serializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class _Vista(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = []
    error = None

    def post(self, request):
        if self.error is not None:
            raise self.error
        _Serializer(data=request.data).is_valid(raise_exception=True)


class ManejadorExcepcionesTests(SimpleTestCase):
    """El manejador registrado en settings, a través de una vista real de DRF."""

    def _llamar(self, error=None, datos=None):
        vista = _Vista.as_view(error=error)
        return vista(APIRequestFactory().post('/', datos or {}, format='json'))

    def test_esta_registrado_en_settings(self):
        self.assertEqual(
            settings.REST_FRAMEWORK['EXCEPTION_HANDLER'],
            'utilidades.excepciones.manejador_excepciones',
        )
        self.assertTrue(callable(manejador_excepciones))

    def test_validation_error_con_texto(self):
        respuesta = self._llamar(ValidationError('El documento 7 ya fue enviado electrónicamente.'))
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data, {'detail': 'El documento 7 ya fue enviado electrónicamente.'})

    def test_error_de_serializer(self):
        respuesta = self._llamar()
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['detail'], 'ids: Este campo es requerido.')
        self.assertIn('ids', respuesta.data)

    def test_not_found_ya_trae_detail(self):
        respuesta = self._llamar(NotFound('No existe.'))
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(respuesta.data, {'detail': 'No existe.'})


class RespuestasDeErrorTests(SimpleTestCase):
    """
    Guarda sobre el código: toda `Response(...)` de error armada a mano con un
    dict literal lleva `detail`. Esas respuestas no pasan por el manejador de
    excepciones, así que es la única forma de que no se escape ninguna.

    Un cuerpo que no es un dict literal (una variable) no se puede revisar acá:
    quien lo arme tiene que pasarlo por `con_detail`.
    """

    CARPETAS_EXCLUIDAS = {'migrations', '.git', '__pycache__', 'node_modules'}

    def _es_error(self, nodo):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, int):
            return nodo.value >= 400
        if isinstance(nodo, ast.Attribute) and nodo.attr.startswith('HTTP_'):
            return int(nodo.attr.split('_')[1]) >= 400
        return False

    def test_toda_respuesta_de_error_literal_lleva_detail(self):
        faltantes = []
        for archivo in RAIZ.rglob('*.py'):
            if self.CARPETAS_EXCLUIDAS & set(archivo.relative_to(RAIZ).parts):
                continue
            if archivo.name.startswith('test'):
                continue
            arbol = ast.parse(archivo.read_text(encoding='utf-8'))
            for nodo in ast.walk(arbol):
                if not isinstance(nodo, ast.Call):
                    continue
                nombre = getattr(nodo.func, 'id', None) or getattr(nodo.func, 'attr', None)
                if nombre not in ('Response', 'JsonResponse'):
                    continue
                estado = next((k.value for k in nodo.keywords if k.arg == 'status'), None)
                if estado is None or not self._es_error(estado):
                    continue
                cuerpo = nodo.args[0] if nodo.args else None
                if not isinstance(cuerpo, ast.Dict):
                    continue
                claves = {k.value for k in cuerpo.keys if isinstance(k, ast.Constant)}
                if 'detail' not in claves:
                    faltantes.append(f'{archivo.relative_to(RAIZ)}:{nodo.lineno}')

        self.assertEqual(faltantes, [], 'Respuestas de error sin `detail`')
