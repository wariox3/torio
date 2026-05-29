from rest_framework import serializers

from general.models import GenCiudad, GenContacto, GenIdentificacion, GenTipoPersona


class GenContactoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de contactos y la lógica
    de upsert por cada fila.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.
    """

    model = GenContacto
    nombre_archivo = 'contactos'

    campos_excel = (
        ('identificacion.id', 'Tipo identificación'),
        ('numero_identificacion', 'Número identificación'),
        ('digito_verificacion', 'DV'),
        ('nombre_corto', 'Nombre corto'),
        ('nombre1', 'Primer nombre'),
        ('nombre2', 'Segundo nombre'),
        ('apellido1', 'Primer apellido'),
        ('apellido2', 'Segundo apellido'),
        ('direccion', 'Dirección'),
        ('ciudad.id', 'Ciudad'),
        ('tipo_persona.id', 'Tipo persona'),
        ('telefono', 'Teléfono'),
        ('celular', 'Celular'),
        ('correo', 'Correo'),
        ('cliente', 'Cliente'),
        ('proveedor', 'Proveedor'),
        ('empleado', 'Empleado'),
        ('conductor', 'Conductor'),
    )

    def procesar_fila(self, datos, fila):
        numero_id = datos.get('numero_identificacion')
        if not numero_id:
            raise ValueError('Falta número de identificación')

        identificacion = self._buscar_por_id(
            GenIdentificacion, datos.get('identificacion.id'), 'Tipo de identificación',
        )
        ciudad = self._buscar_por_id(GenCiudad, datos.get('ciudad.id'), 'Ciudad')
        tipo_persona = self._buscar_por_id(GenTipoPersona, datos.get('tipo_persona.id'), 'Tipo de persona')

        campos = {
            'identificacion': identificacion,
            'ciudad': ciudad,
            'tipo_persona': tipo_persona,
            'numero_identificacion': str(numero_id).strip(),
            'digito_verificacion': datos.get('digito_verificacion'),
            'nombre_corto': (datos.get('nombre_corto') or '').strip(),
            'nombre1': datos.get('nombre1'),
            'nombre2': datos.get('nombre2'),
            'apellido1': datos.get('apellido1'),
            'apellido2': datos.get('apellido2'),
            'direccion': (datos.get('direccion') or '').strip(),
            'telefono': (datos.get('telefono') or '').strip(),
            'celular': datos.get('celular'),
            'correo': (datos.get('correo') or '').strip(),
            'cliente': self._si_no(datos.get('cliente')),
            'proveedor': self._si_no(datos.get('proveedor')),
            'empleado': self._si_no(datos.get('empleado')),
            'conductor': self._si_no(datos.get('conductor')),
        }

        existente = GenContacto.objects.filter(
            identificacion=identificacion,
            numero_identificacion=campos['numero_identificacion'],
        ).first()
        if existente is not None:
            for k, v in campos.items():
                setattr(existente, k, v)
            existente.save()
            return 'actualizado'

        GenContacto.objects.create(**campos)
        return 'creado'

    @staticmethod
    def _buscar_por_id(modelo, valor, etiqueta):
        if valor in (None, ''):
            raise ValueError(f'Falta {etiqueta}')
        try:
            pk = int(valor)
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número (PK), recibido: "{valor}"')
        obj = modelo.objects.filter(pk=pk).first()
        if not obj:
            raise ValueError(f'{etiqueta} con id={pk} no existe')
        return obj

    @staticmethod
    def _si_no(v):
        if v is None or v == '':
            return False
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
