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
    GenFestivo,
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


class _ProgramacionBaseTests(TenantTestCase):
    """Fixtures comunes (contrato, detalle, turno) para las pruebas de programación."""

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
        self.documento = GenDocumento.objects.create(documento_tipo=documento_tipo)
        self.detalle = GenDocumentoDetalle.objects.create(documento=self.documento)

        self.turno = TurTurno.objects.create(
            nombre='Diurno',
            codigo='D',
            hora_inicio=time(6, 0),
            hora_fin=time(14, 0),
            horas=8,
            horas_diurnas=8,
            horas_nocturnas=0,
        )


class CrearProgramacionTests(_ProgramacionBaseTests):
    def setUp(self):
        super().setUp()
        self.view = _ViewSinPermisos.as_view({'post': 'crear_programacion'})

    def _payload(self, **overrides):
        data = {
            'contrato_id': self.contrato.id,
            'documento_detalle_id': self.detalle.id,
            'items': [
                {'fecha': '2026-06-01', 'turno_codigo': self.turno.codigo},
                {'fecha': '2026-06-02', 'turno_codigo': None},
            ],
        }
        data.update(overrides)
        return data

    def _post(self, data):
        request = self.factory.post('/crear-programacion/', data, format='json')
        return self.view(request)

    def test_crea_programacion(self):
        response = self._post(self._payload())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, {'creados': 2})
        self.assertEqual(TurProgramacion.objects.count(), 2)

        dia1 = TurProgramacion.objects.get(fecha=date(2026, 6, 1))
        self.assertEqual(dia1.turno_id, self.turno.id)
        self.assertEqual(dia1.horas, self.turno.horas)
        self.assertEqual(dia1.documento_detalle_id, self.detalle.id)
        self.assertFalse(dia1.festivo)

        dia2 = TurProgramacion.objects.get(fecha=date(2026, 6, 2))
        self.assertIsNone(dia2.turno_id)  # descanso
        self.assertEqual(dia2.horas, 0)

        # Sumó las horas al detalle (solo dia1 tiene turno: 8h diurnas).
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.horas_programadas, self.turno.horas)
        self.assertEqual(self.detalle.horas_diurnas_programadas, self.turno.horas_diurnas)
        self.assertEqual(self.detalle.horas_nocturnas_programadas, 0)

    def test_marca_festivo(self):
        GenFestivo.objects.create(id=1, fecha=date(2026, 6, 1), nombre='Festivo')

        self._post(self._payload())

        self.assertTrue(TurProgramacion.objects.get(fecha=date(2026, 6, 1)).festivo)

    def test_elimina_programacion(self):
        self._post(self._payload())  # crea 2026-06-01 y 2026-06-02 en self.detalle
        # Programación del mismo contrato en OTRO documento_detalle: NO debe borrarse.
        otro_detalle = GenDocumentoDetalle.objects.create(documento=self.detalle.documento)
        TurProgramacion.objects.create(
            contrato=self.contrato, documento_detalle=otro_detalle, fecha=date(2026, 7, 1),
        )

        eliminar = _ViewSinPermisos.as_view({'post': 'eliminar_programacion'})
        request = self.factory.post('/eliminar-programacion/', {
            'contrato_id': self.contrato.id,
            'documento_detalle_id': self.detalle.id,
        }, format='json')
        response = eliminar(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'eliminados': 2})
        self.assertEqual(TurProgramacion.objects.count(), 1)  # queda la del otro detalle
        self.assertTrue(
            TurProgramacion.objects.filter(documento_detalle=otro_detalle).exists()
        )

        # Restó las horas del detalle (vuelve a 0).
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.horas_programadas, 0)
        self.assertEqual(self.detalle.horas_diurnas_programadas, 0)
        self.assertEqual(self.detalle.horas_nocturnas_programadas, 0)

    def test_fecha_repetida_en_request(self):
        response = self._post(self._payload(items=[
            {'fecha': '2026-06-01', 'turno_codigo': self.turno.codigo},
            {'fecha': '2026-06-01', 'turno_codigo': None},
        ]))

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        self.assertEqual(TurProgramacion.objects.count(), 0)

    def test_fecha_ya_existente(self):
        self._post(self._payload())  # crea 2026-06-01 (turno D) y 2026-06-02 (descanso)
        antes = TurProgramacion.objects.count()

        response = self._post(self._payload(items=[
            {'fecha': '2026-06-01', 'turno_codigo': self.turno.codigo},  # conflicto
            {'fecha': '2026-06-03', 'turno_codigo': self.turno.codigo},
        ]))

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        self.assertEqual(TurProgramacion.objects.count(), antes)  # no se insertó nada

        # Devuelve las programaciones en conflicto (solo la fecha en conflicto).
        existentes = response.data['existentes']
        self.assertEqual(len(existentes), 1)
        self.assertEqual(existentes[0]['fecha'], '2026-06-01')
        self.assertEqual(existentes[0]['turno_id'], self.turno.id)
        self.assertEqual(existentes[0]['turno_codigo'], self.turno.codigo)

    def test_turno_inexistente(self):
        response = self._post(self._payload(items=[
            {'fecha': '2026-06-01', 'turno_codigo': 'XXX'},
        ]))

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        self.assertEqual(TurProgramacion.objects.count(), 0)

    def test_contrato_no_habilitado(self):
        self.contrato.habilitado_turno = False
        self.contrato.save(update_fields=['habilitado_turno'])

        response = self._post(self._payload())

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        self.assertEqual(TurProgramacion.objects.count(), 0)

    def test_contrato_inexistente(self):
        response = self._post(self._payload(contrato_id=999999))

        self.assertEqual(response.status_code, 404)

    def test_documento_detalle_inexistente(self):
        response = self._post(self._payload(documento_detalle_id=999999))

        self.assertEqual(response.status_code, 404)

    def test_documento_detalle_requerido(self):
        data = self._payload()
        del data['documento_detalle_id']

        response = self._post(data)

        self.assertEqual(response.status_code, 400)
        self.assertIn('documento_detalle_id', response.data)


class ActualizarProgramacionTests(_ProgramacionBaseTests):
    def setUp(self):
        super().setUp()
        self.crear = _ViewSinPermisos.as_view({'post': 'crear_programacion'})
        self.actualizar = _ViewSinPermisos.as_view({'post': 'actualizar_programacion'})

        # Turno nocturno para probar cambios de turno.
        self.turno_noche = TurTurno.objects.create(
            nombre='Nocturno',
            codigo='N',
            hora_inicio=time(22, 0),
            hora_fin=time(6, 0),
            horas=10,
            horas_diurnas=0,
            horas_nocturnas=10,
        )

        # Estado inicial: 2026-06-01 turno D (8h diurnas), 2026-06-02 descanso.
        self.crear(self.factory.post('/crear-programacion/', {
            'contrato_id': self.contrato.id,
            'documento_detalle_id': self.detalle.id,
            'items': [
                {'fecha': '2026-06-01', 'turno_codigo': self.turno.codigo},
                {'fecha': '2026-06-02', 'turno_codigo': None},
            ],
        }, format='json'))

    def _post(self, items, **overrides):
        data = {
            'contrato_id': self.contrato.id,
            'documento_detalle_id': self.detalle.id,
            'items': items,
        }
        data.update(overrides)
        request = self.factory.post('/actualizar-programacion/', data, format='json')
        return self.actualizar(request)

    def test_agrega_y_elimina(self):
        # Mantiene 06-01 (D), quita 06-02 (descanso, 0h) y agrega 06-03 (D, +8h).
        response = self._post([
            {'fecha': '2026-06-01', 'turno_codigo': self.turno.codigo},
            {'fecha': '2026-06-03', 'turno_codigo': self.turno.codigo},
        ])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'creados': 1, 'actualizados': 0, 'eliminados': 1})

        fechas = set(TurProgramacion.objects.values_list('fecha', flat=True))
        self.assertEqual(fechas, {date(2026, 6, 1), date(2026, 6, 3)})

        # 06-01 (8h) + 06-03 (8h) = 16h diurnas en el detalle.
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.horas_programadas, 16)
        self.assertEqual(self.detalle.horas_diurnas_programadas, 16)
        self.assertEqual(self.detalle.horas_nocturnas_programadas, 0)

    def test_cambia_turno(self):
        # 06-01 pasa de D (8h diurnas) a N (10h nocturnas); 06-02 se conserva.
        response = self._post([
            {'fecha': '2026-06-01', 'turno_codigo': self.turno_noche.codigo},
            {'fecha': '2026-06-02', 'turno_codigo': None},
        ])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'creados': 0, 'actualizados': 1, 'eliminados': 0})

        dia1 = TurProgramacion.objects.get(fecha=date(2026, 6, 1))
        self.assertEqual(dia1.turno_id, self.turno_noche.id)
        self.assertEqual(dia1.horas, 10)
        self.assertEqual(dia1.horas_nocturnas, 10)

        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.horas_programadas, 10)
        self.assertEqual(self.detalle.horas_diurnas_programadas, 0)
        self.assertEqual(self.detalle.horas_nocturnas_programadas, 10)

    def test_propaga_al_documento(self):
        self._post([
            {'fecha': '2026-06-01', 'turno_codigo': self.turno.codigo},
            {'fecha': '2026-06-03', 'turno_codigo': self.turno.codigo},
        ])

        self.documento.refresh_from_db()
        self.assertEqual(self.documento.horas_programadas, 16)
        self.assertEqual(self.documento.horas_diurnas_programadas, 16)
        self.assertEqual(self.documento.horas_nocturnas_programadas, 0)

    def test_sin_cambios_no_altera_horas(self):
        response = self._post([
            {'fecha': '2026-06-01', 'turno_codigo': self.turno.codigo},
            {'fecha': '2026-06-02', 'turno_codigo': None},
        ])

        self.assertEqual(response.data, {'creados': 0, 'actualizados': 0, 'eliminados': 0})
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.horas_programadas, 8)

    def test_conflicto_con_otro_detalle(self):
        # El contrato ya tiene 06-05 ocupado en OTRO detalle.
        otro_detalle = GenDocumentoDetalle.objects.create(documento=self.documento)
        TurProgramacion.objects.create(
            contrato=self.contrato,
            documento_detalle=otro_detalle,
            fecha=date(2026, 6, 5),
            turno=self.turno,
            horas=8,
            horas_diurnas=8,
        )
        antes = TurProgramacion.objects.count()

        response = self._post([
            {'fecha': '2026-06-01', 'turno_codigo': self.turno.codigo},
            {'fecha': '2026-06-05', 'turno_codigo': self.turno.codigo},  # conflicto
        ])

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        self.assertEqual(len(response.data['existentes']), 1)
        self.assertEqual(response.data['existentes'][0]['fecha'], '2026-06-05')

        # No se aplicó ningún cambio.
        self.assertEqual(TurProgramacion.objects.count(), antes)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.horas_programadas, 8)

    def test_turno_inexistente(self):
        response = self._post([
            {'fecha': '2026-06-01', 'turno_codigo': 'XXX'},
        ])

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)

    def test_contrato_no_habilitado(self):
        self.contrato.habilitado_turno = False
        self.contrato.save(update_fields=['habilitado_turno'])

        response = self._post([
            {'fecha': '2026-06-01', 'turno_codigo': self.turno.codigo},
        ])

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
