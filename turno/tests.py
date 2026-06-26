from datetime import date, time

from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from general.models import (
    GenCiudad,
    GenContacto,
    GenDocumento,
    GenDocumentoDetalle,
    GenDocumentoTipo,
    GenEstado,
    GenIdentificacion,
    GenPais,
    GenTipoPersona,
)
from humano.models import HumContrato, HumContratoTipo, HumGrupo
from turno.models import TurProgramacion, TurTurno
from turno.views.programacion import TurProgramacionViewSet


class _ViewSinPermisos(TurProgramacionViewSet):
    """Variante de la vista sin auth/permiso/throttle para probar el action aislado."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class AplicarProgramacionTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.telefono = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = _ViewSinPermisos.as_view({'post': 'aplicar_programacion'})

        pais = GenPais.objects.create(id=1, nombre='Colombia')
        estado = GenEstado.objects.create(id=1, nombre='Cundinamarca', pais=pais)
        ciudad = GenCiudad.objects.create(id=1, nombre='Bogotá', estado=estado)
        identificacion = GenIdentificacion.objects.create(id=1, nombre='CC')
        tipo_persona = GenTipoPersona.objects.create(id=1, nombre='Natural')
        contacto = GenContacto.objects.create(
            numero_identificacion='123',
            nombre_corto='Empleado',
            direccion='Calle 1',
            telefono='1',
            correo='e@e.com',
            identificacion=identificacion,
            ciudad=ciudad,
            tipo_persona=tipo_persona,
        )
        contrato_tipo = HumContratoTipo.objects.create(id=1, nombre='Fijo')
        grupo = HumGrupo.objects.create(nombre='Grupo 1')
        self.contrato = HumContrato.objects.create(
            fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 12, 31),
            contrato_tipo=contrato_tipo,
            contacto=contacto,
            grupo=grupo,
            habilitado_turno=True,
        )

        documento_tipo = GenDocumentoTipo.objects.create(nombre='Programación')
        documento = GenDocumento.objects.create(documento_tipo=documento_tipo)
        self.detalle = GenDocumentoDetalle.objects.create(documento=documento)

        self.turno = TurTurno.objects.create(
            nombre='Diurno',
            codigo='D',
            hora_inicio=time(6, 0),
            hora_fin=time(14, 0),
            horas=8,
            horas_diurnas=8,
            horas_nocturnas=0,
        )

    def _payload(self, **overrides):
        data = {
            'contrato_id': self.contrato.id,
            'anio': 2026,
            'mes': 6,
            'documento_detalle_id': self.detalle.id,
            'dias': [
                {'dia': 1, 'turno_codigo': self.turno.codigo},
                {'dia': 2, 'turno_codigo': None},
            ],
        }
        data.update(overrides)
        return data

    def _post(self, data):
        request = self.factory.post('/aplicar-programacion/', data, format='json')
        return self.view(request)

    def test_crea_programacion(self):
        response = self._post(self._payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'creados': 2, 'actualizados': 0})
        self.assertEqual(TurProgramacion.objects.count(), 2)

        dia1 = TurProgramacion.objects.get(fecha=date(2026, 6, 1))
        self.assertEqual(dia1.turno_id, self.turno.id)
        self.assertEqual(dia1.horas, self.turno.horas)
        self.assertEqual(dia1.documento_detalle_id, self.detalle.id)

        dia2 = TurProgramacion.objects.get(fecha=date(2026, 6, 2))
        self.assertIsNone(dia2.turno_id)  # descanso
        self.assertEqual(dia2.horas, 0)

    def test_segunda_llamada_hace_upsert(self):
        self._post(self._payload())
        response = self._post(self._payload())

        self.assertEqual(response.data, {'creados': 0, 'actualizados': 2})
        self.assertEqual(TurProgramacion.objects.count(), 2)

    def test_contrato_no_habilitado(self):
        self.contrato.habilitado_turno = False
        self.contrato.save(update_fields=['habilitado_turno'])

        response = self._post(self._payload())

        self.assertEqual(response.status_code, 400)
        self.assertIn('contrato_id', response.data)
        self.assertEqual(TurProgramacion.objects.count(), 0)

    def test_documento_detalle_requerido(self):
        data = self._payload()
        del data['documento_detalle_id']

        response = self._post(data)

        self.assertEqual(response.status_code, 400)
        self.assertIn('documento_detalle_id', response.data)

    def test_contrato_inexistente(self):
        response = self._post(self._payload(contrato_id=999999))

        self.assertEqual(response.status_code, 404)

    def test_dia_fuera_del_mes(self):
        response = self._post(self._payload(
            mes=2, dias=[{'dia': 30, 'turno_codigo': self.turno.codigo}],
        ))

        self.assertEqual(response.status_code, 400)
        self.assertIn('dias', response.data)

    def test_turno_inexistente(self):
        response = self._post(self._payload(
            dias=[{'dia': 1, 'turno_codigo': 'XXX'}],
        ))

        self.assertEqual(response.status_code, 400)
        self.assertIn('dias', response.data)
