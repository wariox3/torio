"""
Logotipo de la empresa: validación, normalización y guardado.

Vive en `GenConfiguracion.gen_empresa_logotipo`, como PNG en base64. La decisión
de guardarlo en la fila y no en B2 está razonada en el modelo; acá lo que importa
es que este módulo es el **único** que escribe ese campo, y por eso es el único
lugar donde hay que mirar para saber qué contiene.

Se normaliza al subir y no al imprimir. Un formato que dibuja el logo no debería
tener que decodificar lo que el usuario haya subido —un JPEG de 4 MB sacado del
celular, un PNG de 3000 px— ni preguntarse por su formato: recibe siempre un PNG
de a lo sumo 400 px de lado. El costo se paga una vez, al cargarlo, y no en cada
impresión.
"""
import base64

from utilidades.imagenes import (
    LADO_MAXIMO_LOGOTIPO,
    a_bytes_png,
    abrir_imagen,
    redimensionar,
    validar_archivo_imagen,
)


def procesar(archivo) -> str:
    """
    Devuelve el PNG en base64 listo para guardar.

    Lanza `ValueError` si la imagen no sirve —formato, tamaño o contenido que no
    corresponde—, con el mismo criterio que la foto de perfil.
    """
    validar_archivo_imagen(archivo)
    # `abrir_imagen` compone la transparencia sobre blanco. Para un logo impreso
    # sobre la hoja es lo correcto: el PDF no tiene fondo propio contra el que
    # componer, y un alfa descartado sin componer saldría en negro.
    imagen = redimensionar(abrir_imagen(archivo), LADO_MAXIMO_LOGOTIPO)
    return base64.b64encode(a_bytes_png(imagen)).decode('ascii')


def cargar(archivo, configuracion):
    """Procesa el archivo y lo guarda en la configuración. Devuelve la configuración."""
    configuracion.gen_empresa_logotipo = procesar(archivo)
    configuracion.save(update_fields=['gen_empresa_logotipo'])
    return configuracion


def quitar(configuracion):
    """
    Deja la configuración sin logotipo. Devuelve la configuración.

    Es idempotente: quitar el logotipo de un tenant que no tiene ninguno no es un
    error, es el estado que se pedía. Un botón de la pantalla no debería fallar
    por llegar dos veces.
    """
    configuracion.gen_empresa_logotipo = None
    configuracion.save(update_fields=['gen_empresa_logotipo'])
    return configuracion


def bytes_logotipo(configuracion) -> bytes | None:
    """
    Los bytes del PNG, o `None` si el tenant no cargó logotipo.

    Un base64 corrupto devuelve `None` en vez de estallar: un logo ilegible no es
    motivo para que no salga un certificado.
    """
    codificado = getattr(configuracion, 'gen_empresa_logotipo', None) if configuracion else None
    if not codificado:
        return None
    try:
        return base64.b64decode(codificado, validate=True)
    except Exception:
        return None
