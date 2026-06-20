import httpx
from decouple import config


class Wolframio:

    def consumir_post(self, data, url):
        env = config('ENV')
        if env == 'prod':
            url_base = 'https://rededoc.co' + url
        elif env == 'test':
            url_base = 'https://prueba.rededoc.co' + url
        else:
            url_base = 'https://prueba.rededoc.co' + url
        response = httpx.post(url_base, json=data)
        return {'status': response.status_code, 'datos': response.json()}

    def contacto_consulta_nit(self, datos):
        respuesta = self.consumir_post(datos, '/api/contacto/consultanit')
        status = respuesta['status']
        cuerpo = respuesta['datos']
        if status == 200:
            return {'error': False, 'datos': cuerpo}
        if status == 404:
            return {'error': True, 'mensaje': 'No existe la ruta del servicio Wolframio'}
        if status == 500:
            detalle = cuerpo.get('detail', '')
            return {
                'error': True,
                'mensaje': f'Ocurrió un error grave en el servicio Wolframio, notifique a su proveedor. {detalle}'.strip(),
            }
        return {'error': True, 'mensaje': cuerpo.get('mensaje', f'Error inesperado ({status})')}
