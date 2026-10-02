from datetime import date
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from general.models import (
    GenCiudad,
    GenConfiguracion,
    GenContacto,
    GenEstado,
    GenIdentificacion,
    GenPais,
    GenTipoPersona,
)
from humano.models import (
    HumContrato,
    HumContratoTipo,
    HumGrupo,
    HumNovedad,
    HumPagoTipo,
    HumPeriodo,
    HumProgramacion,
    HumProgramacionDetalle,
)
from humano.servicios import ProgramacionError, cargar_contratos, eliminar_detalles
from humano.serializers import HumProgramacionSerializer
from humano.views.contrato import HumContratoViewSet
from utilidades.fechas import dias_prestacionales


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
        tenant.celular = '0'
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


class CargarContratosTests(TenantTestCase):
    """`cargar_contratos`: un detalle por contrato del grupo según el tipo de pago."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        pais = GenPais.objects.create(id=1, nombre='Colombia')
        ciudad = GenCiudad.objects.create(
            id=1, nombre='Bogotá', estado=GenEstado.objects.create(id=1, nombre='Cundinamarca', pais=pais),
        )
        self.contacto = GenContacto.objects.create(
            numero_identificacion='123', nombre_corto='Empleado', direccion='Calle 1', telefono='1',
            correo='e@e.com', identificacion=GenIdentificacion.objects.create(id=1, nombre='CC'),
            ciudad=ciudad, tipo_persona=GenTipoPersona.objects.create(id=1, nombre='Natural'), empleado=True,
        )
        GenConfiguracion.objects.update_or_create(pk=1, defaults={
            'hum_factor': Decimal('8'),
            'hum_salario_minimo': Decimal('1423500'),
            'hum_auxilio_transporte': Decimal('200000'),
        })
        self.indefinido = HumContratoTipo.objects.create(id=1, nombre='Indefinido')
        self.fijo = HumContratoTipo.objects.create(id=2, nombre='Fijo')
        self.practica = HumContratoTipo.objects.create(id=5, nombre='Practica estudiantil')
        for id, nombre in ((1, 'Nomina'), (2, 'Prima'), (3, 'Cesantia')):
            HumPagoTipo.objects.create(id=id, nombre=nombre)
        self.grupo = HumGrupo.objects.create(nombre='Grupo 1')

    def _programacion(self, **overrides):
        return HumProgramacion.objects.create(**{
            'fecha_desde': date(2026, 3, 1), 'fecha_hasta': date(2026, 3, 15),
            'fecha_hasta_periodo': date(2026, 3, 15), 'dias_reales': 15,
            'grupo': self.grupo, 'pago_tipo_id': 1, **overrides,
        })

    def _contrato(self, **overrides):
        return HumContrato.objects.create(**{
            'fecha_desde': date(2026, 1, 1), 'fecha_hasta': date(2026, 1, 1),
            'salario': Decimal('2000000'), 'contrato_tipo': self.indefinido,
            'contacto': self.contacto, 'grupo': self.grupo, **overrides,
        })

    # ---- nómina ----

    def test_nomina_indefinido_quincena_completa(self):
        contrato = self._contrato()
        programacion = self._programacion()

        self.assertEqual(cargar_contratos(programacion), 1)

        detalle = HumProgramacionDetalle.objects.get(programacion=programacion)
        self.assertEqual(detalle.contrato_id, contrato.id)
        self.assertEqual((detalle.fecha_desde, detalle.fecha_hasta), (date(2026, 3, 1), date(2026, 3, 15)))
        self.assertEqual(detalle.dias, 15)
        self.assertEqual(detalle.diurna, 120)
        self.assertFalse(detalle.ingreso)
        programacion.refresh_from_db()
        self.assertEqual(programacion.contratos, 1)

    def test_nomina_ingreso_en_el_periodo(self):
        self._contrato(fecha_desde=date(2026, 3, 6))
        programacion = self._programacion()

        cargar_contratos(programacion)

        detalle = HumProgramacionDetalle.objects.get(programacion=programacion)
        self.assertTrue(detalle.ingreso)
        self.assertEqual(detalle.dias, 10)

    def test_nomina_resta_dias_de_novedad(self):
        contrato = self._contrato()
        HumNovedad.objects.create(contrato=contrato, fecha_desde=date(2026, 3, 10), fecha_hasta=date(2026, 3, 20))
        programacion = self._programacion()

        cargar_contratos(programacion)

        detalle = HumProgramacionDetalle.objects.get(programacion=programacion)
        self.assertEqual(detalle.dias_novedad, 6)
        self.assertEqual(detalle.dias, 9)

    def test_nomina_practica_no_cotiza_ni_recibe_transporte(self):
        self._contrato(contrato_tipo=self.practica, fecha_hasta=date(2026, 12, 31))
        programacion = self._programacion()

        cargar_contratos(programacion)

        detalle = HumProgramacionDetalle.objects.get(programacion=programacion)
        self.assertFalse(detalle.descuento_salud)
        self.assertFalse(detalle.descuento_pension)
        self.assertFalse(detalle.pago_auxilio_transporte)

    def test_nomina_contrato_fijo_vencido_sin_terminar_marca_error(self):
        self._contrato(contrato_tipo=self.fijo, fecha_hasta=date(2026, 2, 28))
        programacion = self._programacion()

        cargar_contratos(programacion)

        detalle = HumProgramacionDetalle.objects.get(programacion=programacion)
        self.assertTrue(detalle.error_terminacion)
        self.assertEqual(detalle.dias, 0)

    def test_no_duplica_contratos_ya_cargados(self):
        self._contrato()
        programacion = self._programacion()
        cargar_contratos(programacion)

        self.assertEqual(cargar_contratos(programacion), 0)
        self.assertEqual(HumProgramacionDetalle.objects.filter(programacion=programacion).count(), 1)

    def test_programacion_generada_no_carga(self):
        self._contrato()
        programacion = self._programacion(estado_generado=True)

        with self.assertRaises(ProgramacionError):
            cargar_contratos(programacion)
        self.assertFalse(HumProgramacionDetalle.objects.exists())

    def test_contratos_de_otro_grupo_no_entran(self):
        self._contrato(grupo=HumGrupo.objects.create(nombre='Otro'))
        self.assertEqual(cargar_contratos(self._programacion()), 0)

    # ---- prima y cesantía ----

    def test_prima_suma_auxilio_al_salario_promedio(self):
        self._contrato(auxilio_transporte=True)
        programacion = self._programacion(
            pago_tipo_id=2, fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 6, 30), fecha_hasta_periodo=date(2026, 6, 30),
        )

        cargar_contratos(programacion)

        detalle = HumProgramacionDetalle.objects.get(programacion=programacion)
        self.assertEqual(detalle.dias, 180)
        self.assertEqual(detalle.salario_promedio, Decimal('2200000'))

    def test_cesantia_sin_nomina_toma_el_salario_como_minimo(self):
        self._contrato()
        programacion = self._programacion(
            pago_tipo_id=3, fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 6, 30), fecha_hasta_periodo=date(2026, 6, 30),
        )

        cargar_contratos(programacion)

        detalle = HumProgramacionDetalle.objects.get(programacion=programacion)
        self.assertEqual(detalle.dias, 180)
        self.assertEqual(detalle.base_prestacion, 0)
        self.assertEqual(detalle.salario_promedio, Decimal('2000000'))

    def test_dias_prestacionales(self):
        self.assertEqual(dias_prestacionales(date(2026, 1, 1), date(2026, 6, 30)), 180)
        self.assertEqual(dias_prestacionales(date(2026, 1, 1), date(2026, 2, 28)), 60)
        self.assertEqual(dias_prestacionales(date(2026, 7, 1), date(2026, 12, 30)), 180)
        # 30/360: el 31 cuenta como 30.
        self.assertEqual(dias_prestacionales(date(2026, 1, 1), date(2026, 12, 31)), 360)
        self.assertEqual(dias_prestacionales(date(2026, 7, 1), date(2026, 12, 31)), 180)
        self.assertEqual(dias_prestacionales(date(2026, 1, 31), date(2026, 3, 31)), 61)
        # Febrero completa 30 solo en su último día: en bisiesto el 28 no lo es.
        self.assertEqual(dias_prestacionales(date(2028, 1, 1), date(2028, 2, 29)), 60)
        self.assertEqual(dias_prestacionales(date(2028, 1, 1), date(2028, 2, 28)), 58)

    # ---- eliminar detalles ----

    def _cargada(self, **overrides):
        self._contrato()
        self._contrato(contacto=GenContacto.objects.create(
            numero_identificacion='456', nombre_corto='Otro', direccion='Calle 2', telefono='2',
            correo='o@o.com', identificacion_id=1, ciudad_id=1, tipo_persona_id=1, empleado=True,
        ))
        programacion = self._programacion(**overrides)
        cargar_contratos(programacion)
        programacion.refresh_from_db()
        return programacion

    def test_eliminar_todos_los_detalles(self):
        programacion = self._cargada()

        self.assertEqual(eliminar_detalles(programacion), 2)
        programacion.refresh_from_db()
        self.assertEqual(programacion.contratos, 0)

    def test_eliminar_solo_los_indicados(self):
        programacion = self._cargada()
        detalle = HumProgramacionDetalle.objects.filter(programacion=programacion).first()

        self.assertEqual(eliminar_detalles(programacion, [detalle.id]), 1)
        programacion.refresh_from_db()
        self.assertEqual(programacion.contratos, 1)

    def test_eliminar_ignora_detalles_de_otra_programacion(self):
        programacion = self._cargada()
        otra = self._programacion()
        cargar_contratos(otra)
        ajeno = HumProgramacionDetalle.objects.filter(programacion=otra).first()

        self.assertEqual(eliminar_detalles(programacion, [ajeno.id]), 0)
        self.assertTrue(HumProgramacionDetalle.objects.filter(pk=ajeno.pk).exists())

    def test_no_elimina_en_programacion_generada_o_aprobada(self):
        programacion = self._cargada()
        for estado in ('estado_generado', 'estado_aprobado'):
            HumProgramacion.objects.filter(pk=programacion.pk).update(
                estado_generado=estado == 'estado_generado', estado_aprobado=estado == 'estado_aprobado',
            )

            with self.assertRaises(ProgramacionError):
                eliminar_detalles(programacion)
            self.assertEqual(HumProgramacionDetalle.objects.filter(programacion=programacion).count(), 2)


class PeriodoProgramacionTests(TenantTestCase):
    """`fecha_hasta_periodo`, `dias` y `dias_reales` los calcula el servidor."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.grupo = HumGrupo.objects.create(nombre='Grupo 1')
        HumPagoTipo.objects.create(id=1, nombre='Nomina')

    def _crear(self, fecha_desde, fecha_hasta, **extra):
        serializer = HumProgramacionSerializer(data={
            'fecha_desde': fecha_desde, 'fecha_hasta': fecha_hasta,
            'grupo': self.grupo.id, 'pago_tipo': 1, **extra,
        })
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def test_segunda_quincena_de_mes_de_31_cierra_el_31(self):
        programacion = self._crear('2026-03-16', '2026-03-30')

        self.assertEqual(programacion.fecha_hasta_periodo, date(2026, 3, 31))
        self.assertEqual(programacion.dias, 15)
        self.assertEqual(programacion.dias_reales, 15)

    def test_mes_de_30_cierra_en_la_fecha_hasta(self):
        programacion = self._crear('2026-04-16', '2026-04-30')

        self.assertEqual(programacion.fecha_hasta_periodo, date(2026, 4, 30))

    def test_febrero_completo_son_30_dias(self):
        programacion = self._crear('2026-02-01', '2026-02-28')

        self.assertEqual(programacion.fecha_hasta_periodo, date(2026, 2, 28))
        self.assertEqual(programacion.dias, 30)
        self.assertEqual(programacion.dias_reales, 28)

    def test_lo_que_mande_el_usuario_se_ignora(self):
        programacion = self._crear(
            '2026-03-01', '2026-03-15', fecha_hasta_periodo='2026-12-31', dias=99, dias_reales=99,
        )

        self.assertEqual(programacion.fecha_hasta_periodo, date(2026, 3, 15))
        self.assertEqual((programacion.dias, programacion.dias_reales), (15, 15))

    def test_editar_las_fechas_recalcula(self):
        programacion = self._crear('2026-03-01', '2026-03-15')

        serializer = HumProgramacionSerializer(programacion, data={'fecha_hasta': '2026-03-30'}, partial=True)
        serializer.is_valid(raise_exception=True)
        programacion = serializer.save()

        self.assertEqual(programacion.fecha_hasta_periodo, date(2026, 3, 31))
        self.assertEqual(programacion.dias, 30)

    def test_el_periodo_se_guarda(self):
        # `HumProgramacion.periodo` es el FK: un método con ese nombre lo tapaba y
        # el campo dejaba de existir para Django.
        HumPeriodo.objects.create(id=1, codigo='Q', nombre='Quincenal', dias=15)

        programacion = self._crear('2026-03-01', '2026-03-15', periodo=1)

        programacion.refresh_from_db()
        self.assertEqual(programacion.periodo_id, 1)

    def test_sin_periodo_toma_el_del_grupo(self):
        self.grupo.periodo = HumPeriodo.objects.create(id=1, codigo='Q', nombre='Quincenal', dias=15)
        self.grupo.save()

        self.assertEqual(self._crear('2026-03-01', '2026-03-15').periodo_id, 1)
        self.assertEqual(self._crear('2026-03-01', '2026-03-15', periodo=None).periodo_id, 1)

    def test_el_periodo_enviado_manda_sobre_el_del_grupo(self):
        self.grupo.periodo = HumPeriodo.objects.create(id=1, codigo='Q', nombre='Quincenal', dias=15)
        self.grupo.save()
        HumPeriodo.objects.create(id=2, codigo='M', nombre='Mensual', dias=30)

        self.assertEqual(self._crear('2026-03-01', '2026-03-30', periodo=2).periodo_id, 2)

    def test_grupo_sin_periodo_queda_sin_periodo(self):
        self.assertIsNone(self._crear('2026-03-01', '2026-03-15').periodo_id)

    def test_fecha_hasta_anterior_a_desde(self):
        serializer = HumProgramacionSerializer(data={
            'fecha_desde': '2026-03-15', 'fecha_hasta': '2026-03-01', 'grupo': self.grupo.id, 'pago_tipo': 1,
        })
        self.assertFalse(serializer.is_valid())
