from datetime import date

from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from general.models import (
    GenCiudad,
    GenContacto,
    GenEstado,
    GenIdentificacion,
    GenPais,
    GenTipoPersona,
)
from humano.models import HumContrato, HumContratoTipo, HumGrupo
from humano.views.contrato import HumContratoViewSet


class _ContratoViewSinPermisos(HumContratoViewSet):
    """Variante de la vista sin auth/permiso/throttle para probar los actions aislados."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class ValidacionContratoTests(TenantTestCase):
    """Un contacto no puede tener dos contratos abiertos ni contratos con fechas cruzadas."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.telefono = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.factory = APIRequestFactory()

        pais = GenPais.objects.create(id=1, nombre='Colombia')
        estado = GenEstado.objects.create(id=1, nombre='Cundinamarca', pais=pais)
        ciudad = GenCiudad.objects.create(id=1, nombre='Bogotá', estado=estado)
        identificacion = GenIdentificacion.objects.create(id=1, nombre='CC')
        tipo_persona = GenTipoPersona.objects.create(id=1, nombre='Natural')
        self.contacto = GenContacto.objects.create(
            numero_identificacion='123',
            nombre_corto='Empleado',
            direccion='Calle 1',
            telefono='1',
            correo='e@e.com',
            identificacion=identificacion,
            ciudad=ciudad,
            tipo_persona=tipo_persona,
            empleado=True,
        )
        self.contacto2 = GenContacto.objects.create(
            numero_identificacion='456',
            nombre_corto='Otro',
            direccion='Calle 2',
            telefono='2',
            correo='o@o.com',
            identificacion=identificacion,
            ciudad=ciudad,
            tipo_persona=tipo_persona,
            empleado=True,
        )
        self.contrato_tipo = HumContratoTipo.objects.create(id=1, nombre='Fijo')
        self.grupo = HumGrupo.objects.create(nombre='Grupo 1')

    def _crear_contrato(self, **overrides):
        return HumContrato.objects.create(**{
            'fecha_desde': date(2026, 1, 1),
            'fecha_hasta': date(2026, 6, 30),
            'contrato_tipo': self.contrato_tipo,
            'contacto': self.contacto,
            'grupo': self.grupo,
            'estado_terminado': True,
            **overrides,
        })

    def _post(self, **overrides):
        view = _ContratoViewSinPermisos.as_view({'post': 'create'})
        payload = {
            'fecha_desde': '2026-07-01',
            'fecha_hasta': '2026-12-31',
            'contrato_tipo': self.contrato_tipo.id,
            'contacto': self.contacto.id,
            'grupo': self.grupo.id,
            **overrides,
        }
        return view(self.factory.post('/contrato/', payload, format='json'))

    def test_crea_contrato_sin_conflicto(self):
        response = self._post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(HumContrato.objects.count(), 1)

    def test_crea_contrato_despues_de_uno_terminado(self):
        # Terminado y sin cruce de fechas: se permite.
        self._crear_contrato()

        response = self._post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(HumContrato.objects.count(), 2)

    def test_rechaza_si_contacto_tiene_contrato_sin_terminar(self):
        self._crear_contrato(estado_terminado=False)

        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        self.assertEqual(HumContrato.objects.count(), 1)

    def test_rechaza_fechas_cruzadas(self):
        # Terminado, pero el rango se solapa con el nuevo (2026-07-01 a 2026-12-31).
        self._crear_contrato(fecha_hasta=date(2026, 8, 31))

        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        self.assertEqual(HumContrato.objects.count(), 1)

    def test_rechaza_cruce_por_un_solo_dia(self):
        self._crear_contrato(fecha_hasta=date(2026, 7, 1))

        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)

    def test_permite_contrato_de_otro_contacto(self):
        # Mismo rango de fechas y sin terminar, pero de otro contacto.
        self._crear_contrato(estado_terminado=False, fecha_hasta=date(2026, 12, 31))

        response = self._post(contacto=self.contacto2.id)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(HumContrato.objects.count(), 2)

    def test_rechaza_fecha_hasta_anterior_a_desde(self):
        response = self._post(fecha_desde='2026-12-31', fecha_hasta='2026-07-01')

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)

    def test_actualizar_no_choca_consigo_mismo(self):
        contrato = self._crear_contrato(estado_terminado=False)

        view = _ContratoViewSinPermisos.as_view({'patch': 'partial_update'})
        request = self.factory.patch('/contrato/', {'salario': 100}, format='json')
        response = view(request, pk=contrato.pk)

        self.assertEqual(response.status_code, 200)
        contrato.refresh_from_db()
        self.assertEqual(contrato.salario, 100)
