from datetime import date, time

from django_tenants.test.cases import TenantTestCase
from rest_framework.exceptions import ValidationError

from general.models import (
    GenDocumento,
    GenDocumentoDetalle,
    GenDocumentoTipo,
    GenFestivo,
)
from general.servicios import documento as documento_servicio


class GenerarDocumentoTests(TenantTestCase):
    """
    Generación mensual: los detalles del destino se acotan a la ventana del mes y
    los que no se solapan con él no se generan.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.telefono = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.tipo_origen = GenDocumentoTipo.objects.create(nombre='Contrato')
        self.tipo_destino = GenDocumentoTipo.objects.create(nombre='Programación')
        self.documento = GenDocumento.objects.create(
            documento_tipo=self.tipo_origen, fecha=date(2026, 1, 1),
        )

    def _detalle(self, fecha_desde, fecha_hasta, documento=None, **overrides):
        datos = {
            'documento': documento or self.documento,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            # Turno diurno de 8h todos los días de la semana por defecto.
            'hora_desde': time(6, 0),
            'hora_hasta': time(14, 0),
            'lunes': True, 'martes': True, 'miercoles': True, 'jueves': True,
            'viernes': True, 'sabado': True, 'domingo': True,
        }
        datos.update(overrides)
        return GenDocumentoDetalle.objects.create(**datos)

    def _generar(self, anio=2026, mes=6):
        return documento_servicio.generar(
            documento_tipo_origen=self.tipo_origen,
            documento_tipo_destino_id=self.tipo_destino.id,
            anio=anio,
            mes=mes,
        )

    def test_acota_fechas_al_mes(self):
        # Arranca a mitad del mes y termina mucho después: se recorta al fin de mes.
        self._detalle(date(2026, 6, 15), date(2026, 12, 30))

        generados = self._generar()

        self.assertEqual(len(generados), 1)
        detalle = generados[0].documentos_detalles_documento_rel.get()
        self.assertEqual(detalle.fecha_desde, date(2026, 6, 15))
        self.assertEqual(detalle.fecha_hasta, date(2026, 6, 30))

    def test_acota_fecha_desde_anterior_al_mes(self):
        # Empezó antes del periodo: fecha_desde se corre al primer día del mes.
        self._detalle(date(2026, 1, 1), date(2026, 12, 30))

        generados = self._generar()

        detalle = generados[0].documentos_detalles_documento_rel.get()
        self.assertEqual(detalle.fecha_desde, date(2026, 6, 1))
        self.assertEqual(detalle.fecha_hasta, date(2026, 6, 30))

    def test_rango_dentro_del_mes_se_conserva(self):
        self._detalle(date(2026, 6, 10), date(2026, 6, 20))

        generados = self._generar()

        detalle = generados[0].documentos_detalles_documento_rel.get()
        self.assertEqual(detalle.fecha_desde, date(2026, 6, 10))
        self.assertEqual(detalle.fecha_hasta, date(2026, 6, 20))

    def test_no_genera_detalle_que_empieza_despues_del_mes(self):
        # Empieza en julio y se genera junio: no aplica.
        self._detalle(date(2026, 7, 1), date(2026, 12, 30))
        # Uno vigente para que el documento sí se genere.
        vigente = self._detalle(date(2026, 6, 1), date(2026, 6, 30))

        generados = self._generar()

        detalles = list(generados[0].documentos_detalles_documento_rel.all())
        self.assertEqual(len(detalles), 1)
        self.assertEqual(detalles[0].documento_detalle_afectado_id, vigente.id)

    def test_no_genera_detalle_que_termino_antes_del_mes(self):
        self._detalle(date(2026, 1, 1), date(2026, 5, 20))
        vigente = self._detalle(date(2026, 6, 1), date(2026, 6, 30))

        generados = self._generar()

        detalles = list(generados[0].documentos_detalles_documento_rel.all())
        self.assertEqual(len(detalles), 1)
        self.assertEqual(detalles[0].documento_detalle_afectado_id, vigente.id)

    def test_documento_sin_detalles_vigentes_no_se_genera(self):
        self._detalle(date(2026, 7, 1), date(2026, 12, 30))

        with self.assertRaises(ValidationError):
            self._generar()

        self.assertEqual(GenDocumento.objects.filter(documento_tipo=self.tipo_destino).count(), 0)
        # El origen tampoco se toca.
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.fecha, date(2026, 1, 1))

    def test_detalle_sin_fechas_aborta(self):
        self._detalle(date(2026, 6, 1), date(2026, 6, 30))
        self._detalle(None, None)

        with self.assertRaises(ValidationError):
            self._generar()

        # Transacción revertida: no quedó nada generado.
        self.assertEqual(GenDocumento.objects.filter(documento_tipo=self.tipo_destino).count(), 0)

    def test_detalle_sin_horario_aborta(self):
        self._detalle(date(2026, 6, 1), date(2026, 6, 30), hora_desde=None, hora_hasta=None)

        with self.assertRaises(ValidationError):
            self._generar()

        self.assertEqual(GenDocumento.objects.filter(documento_tipo=self.tipo_destino).count(), 0)

    def test_calcula_horas_diurnas_todo_el_mes(self):
        # Turno 06:00-14:00 (8h diurnas), todos los días marcados, junio = 30 días.
        self._detalle(date(2026, 6, 1), date(2026, 6, 30))

        generados = self._generar()

        detalle = generados[0].documentos_detalles_documento_rel.get()
        self.assertEqual(detalle.dias, 30)
        self.assertEqual(detalle.horas_diurnas, 240)   # 8h × 30
        self.assertEqual(detalle.horas_nocturnas, 0)
        self.assertEqual(detalle.horas, 240)

    def test_calcula_horas_reparte_diurnas_y_nocturnas(self):
        # Turno 18:00-06:00 (12h): 1h diurna [18-19) + 11h nocturnas, cruza medianoche.
        self._detalle(
            date(2026, 6, 1), date(2026, 6, 30),
            hora_desde=time(18, 0), hora_hasta=time(6, 0),
        )

        generados = self._generar()

        detalle = generados[0].documentos_detalles_documento_rel.get()
        self.assertEqual(detalle.dias, 30)
        self.assertEqual(detalle.horas_diurnas, 30)    # 1h × 30
        self.assertEqual(detalle.horas_nocturnas, 330)  # 11h × 30
        self.assertEqual(detalle.horas, 360)

    def test_cuenta_solo_dias_de_semana_marcados(self):
        # Solo lunes marcados. Junio 2026 tiene 5 lunes (1, 8, 15, 22, 29).
        self._detalle(
            date(2026, 6, 1), date(2026, 6, 30),
            lunes=True, martes=False, miercoles=False, jueves=False,
            viernes=False, sabado=False, domingo=False,
        )

        generados = self._generar()

        detalle = generados[0].documentos_detalles_documento_rel.get()
        self.assertEqual(detalle.dias, 5)
        self.assertEqual(detalle.horas_diurnas, 40)    # 8h × 5

    def test_festivo_manda_sobre_dia_de_semana(self):
        # Lunes marcado pero festivo=False: un lunes festivo no cuenta.
        # Junio 2026: los lunes son 1, 8, 15, 22, 29; marcamos el 15 como festivo.
        GenFestivo.objects.create(id=1, fecha=date(2026, 6, 15), nombre='Festivo')
        self._detalle(
            date(2026, 6, 1), date(2026, 6, 30),
            lunes=True, martes=False, miercoles=False, jueves=False,
            viernes=False, sabado=False, domingo=False, festivo=False,
        )

        generados = self._generar()

        detalle = generados[0].documentos_detalles_documento_rel.get()
        # 5 lunes menos el 15 (festivo, no cobrado) = 4.
        self.assertEqual(detalle.dias, 4)

    def test_festivo_cuenta_cuando_flag_activo(self):
        GenFestivo.objects.create(id=1, fecha=date(2026, 6, 15), nombre='Festivo')
        self._detalle(
            date(2026, 6, 1), date(2026, 6, 30),
            lunes=True, martes=False, miercoles=False, jueves=False,
            viernes=False, sabado=False, domingo=False, festivo=True,
        )

        generados = self._generar()

        detalle = generados[0].documentos_detalles_documento_rel.get()
        # 4 lunes ordinarios + el 15 festivo (festivo=True) = 5.
        self.assertEqual(detalle.dias, 5)
