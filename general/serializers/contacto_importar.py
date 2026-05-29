from rest_framework import serializers

from general.models import (
    GenBanco,
    GenCiudad,
    GenContacto,
    GenCuentaBancoClase,
    GenIdentificacion,
    GenPlazoPago,
    GenTipoPersona,
)


class GenContactoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de contactos y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
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
        ('correo_facturacion_electronica', 'Correo facturación electrónica'),
        ('plazo_pago.id', 'Plazo pago'),
        ('plazo_pago_proveedor.id', 'Plazo pago proveedor'),
        ('banco.id', 'Banco'),
        ('numero_cuenta', 'Número cuenta'),
        ('cuenta_banco_clase.id', 'Clase cuenta'),
        ('cliente', 'Cliente'),
        ('proveedor', 'Proveedor'),
        ('empleado', 'Empleado'),
        ('conductor', 'Conductor'),
    )
    campos_requeridos = {
        'identificacion.id', 'numero_identificacion', 'nombre_corto',
        'ciudad.id', 'tipo_persona.id', 'celular', 'correo',
    }

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        Procesa todas las filas válidas en bulk:
          1. Pre-carga FKs en una query por modelo.
          2. Pre-carga duplicados en BD en una query.
          3. Valida cada fila contra mapas en memoria (sin BD).
          4. `bulk_create` al final si no hay errores.

        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # 1) Pre-cargar FKs en mapas {id: instancia}
        ids_identificacion = self._ids_int(filas_validas, 'identificacion.id')
        ids_ciudad = self._ids_int(filas_validas, 'ciudad.id')
        ids_tipo_persona = self._ids_int(filas_validas, 'tipo_persona.id')
        ids_plazo_pago = (
            self._ids_int(filas_validas, 'plazo_pago.id')
            | self._ids_int(filas_validas, 'plazo_pago_proveedor.id')
        )
        ids_banco = self._ids_int(filas_validas, 'banco.id')
        ids_cuenta_banco_clase = self._ids_int(filas_validas, 'cuenta_banco_clase.id')

        mapa_identificacion = {
            o.id: o for o in GenIdentificacion.objects.filter(id__in=ids_identificacion)
        }
        mapa_ciudad = {o.id: o for o in GenCiudad.objects.filter(id__in=ids_ciudad)}
        mapa_tipo_persona = {
            o.id: o for o in GenTipoPersona.objects.filter(id__in=ids_tipo_persona)
        }
        mapa_plazo_pago = {
            o.id: o for o in GenPlazoPago.objects.filter(id__in=ids_plazo_pago)
        }
        mapa_banco = {o.id: o for o in GenBanco.objects.filter(id__in=ids_banco)}
        mapa_cuenta_banco_clase = {
            o.id: o for o in GenCuentaBancoClase.objects.filter(id__in=ids_cuenta_banco_clase)
        }

        # 2) Pre-cargar pares (identificacion_id, numero_identificacion) existentes en BD
        ya_existen = set(
            GenContacto.objects
            .filter(identificacion_id__in=ids_identificacion)
            .values_list('identificacion_id', 'numero_identificacion')
        )

        # 3) Construir instancias en memoria, recolectar errores
        errores = []
        nuevos = []
        vistos = set()  # duplicados intra-archivo

        for idx, datos in filas_validas:
            try:
                ident_id = int(datos['identificacion.id'])
                identificacion = mapa_identificacion.get(ident_id)
                if identificacion is None:
                    raise ValueError(f'Tipo de identificación con id={ident_id} no existe')

                ciudad_id = int(datos['ciudad.id'])
                ciudad = mapa_ciudad.get(ciudad_id)
                if ciudad is None:
                    raise ValueError(f'Ciudad con id={ciudad_id} no existe')

                tp_id = int(datos['tipo_persona.id'])
                tipo_persona = mapa_tipo_persona.get(tp_id)
                if tipo_persona is None:
                    raise ValueError(f'Tipo de persona con id={tp_id} no existe')

                plazo_pago = self._fk_opcional(datos.get('plazo_pago.id'), mapa_plazo_pago, 'Plazo pago')
                plazo_pago_proveedor = self._fk_opcional(
                    datos.get('plazo_pago_proveedor.id'), mapa_plazo_pago, 'Plazo pago proveedor',
                )
                banco = self._fk_opcional(datos.get('banco.id'), mapa_banco, 'Banco')
                cuenta_banco_clase = self._fk_opcional(
                    datos.get('cuenta_banco_clase.id'), mapa_cuenta_banco_clase, 'Clase cuenta',
                )

                numero = self._texto(datos.get('numero_identificacion'))
                clave = (ident_id, numero)

                if clave in vistos:
                    raise ValueError(
                        f'Tipo de identificación id={ident_id} y número {numero} '
                        f'están duplicados dentro del archivo'
                    )
                vistos.add(clave)

                if clave in ya_existen:
                    raise ValueError(
                        f'Ya existe un contacto con identificación id={ident_id} y número {numero}'
                    )

                nuevos.append(GenContacto(
                    identificacion=identificacion,
                    ciudad=ciudad,
                    tipo_persona=tipo_persona,
                    numero_identificacion=numero,
                    digito_verificacion=self._texto_o_none(datos.get('digito_verificacion')),
                    nombre_corto=self._texto(datos.get('nombre_corto')),
                    nombre1=self._texto_o_none(datos.get('nombre1')),
                    nombre2=self._texto_o_none(datos.get('nombre2')),
                    apellido1=self._texto_o_none(datos.get('apellido1')),
                    apellido2=self._texto_o_none(datos.get('apellido2')),
                    direccion=self._texto(datos.get('direccion')),
                    telefono=self._texto(datos.get('telefono')),
                    celular=self._texto(datos.get('celular')),
                    correo=self._texto(datos.get('correo')),
                    correo_facturacion_electronica=self._texto_o_none(datos.get('correo_facturacion_electronica')),
                    plazo_pago=plazo_pago,
                    plazo_pago_proveedor=plazo_pago_proveedor,
                    banco=banco,
                    numero_cuenta=self._texto_o_none(datos.get('numero_cuenta')),
                    cuenta_banco_clase=cuenta_banco_clase,
                    cliente=self._si_no(datos.get('cliente')),
                    proveedor=self._si_no(datos.get('proveedor')),
                    empleado=self._si_no(datos.get('empleado')),
                    conductor=self._si_no(datos.get('conductor')),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        # 4) Bulk create (solo si no hubo errores)
        if errores:
            return 0, errores

        if nuevos:
            GenContacto.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    @staticmethod
    def _ids_int(filas_validas, campo):
        """Extrae el conjunto de ids enteros para `campo` (ignora vacíos e inválidos)."""
        ids = set()
        for _, datos in filas_validas:
            valor = datos.get(campo)
            if valor in (None, ''):
                continue
            try:
                ids.add(int(valor))
            except (TypeError, ValueError):
                pass  # tipos inválidos ya fueron filtrados en la fase 1
        return ids

    @staticmethod
    def _fk_opcional(valor, mapa, etiqueta):
        if valor in (None, ''):
            return None
        try:
            pk = int(valor)
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número (PK), recibido: "{valor}"')
        obj = mapa.get(pk)
        if obj is None:
            raise ValueError(f'{etiqueta} con id={pk} no existe')
        return obj

    @staticmethod
    def _texto(v):
        if v is None:
            return ''
        return str(v).strip()

    @staticmethod
    def _texto_o_none(v):
        if v is None or v == '':
            return None
        return str(v).strip()

    @staticmethod
    def _si_no(v):
        if v is None or v == '':
            return False
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
