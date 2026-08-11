# Bitácora de ingresos

Estado: **implementado** — modelo `seguridad/models/acceso.py` (migración `0020_acceso`),
servicio `seguridad/acceso.py`, enganches en `seguridad/views/autenticacion.py`, endpoint
`GET /seguridad/acceso/` y admin de solo lectura, con tests en `seguridad/tests.py`
(`RegistroDeAccesoTests`, `IpDelRequestTests`).

## 1. Por qué

Antes de esto, del login solo quedaba `last_login`: se sabía cuándo entró una cuenta por
última vez, no desde dónde, ni cuántas veces le fallaron la clave antes, ni si alguien
estaba probando correos al azar. Lo único parecido era `SegMfaDesafio.ip` con su contador
de intentos, que cubre solo el segundo paso y se borra cuando el desafío vence
(`seguridad/mfa.py`).

Eso dejaba invisibles dos cosas: una fuerza bruta en curso, y el dueño de una cuenta
comprometida que no tenía forma de notar un ingreso ajeno.

`SegAcceso` vive en el schema público, junto al login: se escribe antes de resolver
cualquier tenant. El registro es **de la cuenta, no de la organización** — una misma
cuenta puede pertenecer a varios contenedores, y el propietario de uno de ellos no ve los
accesos de sus miembros. Es la misma propiedad que sostiene el diseño del MFA
(`docs/mfa.md`).

## 2. Qué se registra

Una fila por intento, en los dos pasos del login. Como el login tiene dos pasos, un mismo
ingreso con MFA deja **dos filas**: son dos eventos distintos.

| `resultado` | Cuándo |
|---|---|
| `ok` | Se emitieron cookies. Único punto: `_emitir_sesion`, así que cubre las dos rutas |
| `clave` | Credenciales inválidas — incluye el correo que no existe |
| `no_verificado` | Clave correcta pero `is_verified=False` |
| `mfa_pendiente` | Clave correcta, desafío abierto, segundo paso sin resolver |
| `mfa_fallido` | Código inválido, desafío vencido o bloqueado por intentos |

Más `ip`, `user_agent`, `metodo_mfa`, y tres banderas: `dispositivo_recordado` (entró
saltando el segundo paso por la cookie), `codigo_respaldo` (entró con un código de
respaldo, o sea que perdió su método habitual) y el `email` **tecleado**.

### Decisiones que no son obvias

- **Se guarda el intento contra un correo que no existe**, con `usuario=None` y el correo
  tal como se tecleó. Es lo único que permite ver una enumeración de usuarios; sin eso la
  tabla sirve como historial de "dónde entré" y para nada más. La respuesta HTTP no
  cambia: sigue siendo el mismo 401 para una clave mala y para un correo inventado — lo
  que se registra adentro no se filtra hacia afuera.
- **`mfa_pendiente` es la fila más valiosa.** Sin ella, quien tiene la clave correcta y se
  frena ante el segundo factor no deja ningún rastro: entrar es lo único que quedaría
  registrado, y justamente eso no pasó.
- **La FK al usuario es `SET_NULL`, no `CASCADE`.** Borrar la cuenta no debe borrar su
  auditoría; por eso el `email` se guarda siempre, aunque el usuario haya quedado ligado.
- **El insert no va dentro de un `try/except`.** Si no se puede escribir la bitácora es
  porque la base no responde, y entonces el login tampoco iba a funcionar. Tragarse el
  error dejaría ingresos sin registrar justo cuando algo anda mal.
- **El admin es de solo lectura** (`has_add/change/delete_permission` en `False`): un
  registro de auditoría editable desde el admin deja de ser un registro de auditoría.

## 3. La IP

`ip_del_request()` en `seguridad/acceso.py` es ahora la única fuente de la IP, y la
comparten las tres tablas que la guardan: `SegAcceso`, `SegMfaDesafio` y
`SegMfaDispositivo`.

Detrás de nginx o Cloudflare, `REMOTE_ADDR` es la del proxy y toda la bitácora apunta al
mismo lado. `X-Forwarded-For` da la real, pero solo se le puede creer si hay un proxy que
lo reescriba: con el servicio expuesto directo, cualquiera manda el header que quiera y
falsea su IP. Por eso `CONFIAR_EN_PROXY` (en el `.env`) arranca en `False` y se prende en
el despliegue que sí tiene proxy adelante.

## 4. Consulta

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/seguridad/acceso/` | Historial de la cuenta autenticada, del más reciente al más viejo, paginado de a 25 |

El filtro sale de `request.user` y nunca de un parámetro, así que no hay forma de pedir el
historial ajeno. No devuelve `email` ni `usuario`: la lista ya es de la cuenta
autenticada. Incluye los intentos fallidos, que son justamente los que el usuario necesita
ver para darse cuenta de que alguien está probando su clave.

Para staff, el admin del schema público (`seguridad/admin.py`), con filtros por resultado y
método, y búsqueda por correo e IP.

## 5. Lo que no cubre

- **Los 429 del throttle no quedan registrados**: DRF corta la petición antes de que
  llegue a la vista. Es la deuda del cache que ya está anotada en `docs/mfa.md` §9 — sin
  Redis, el throttle además cuenta por worker de gunicorn.
- **No hay purga.** La tabla crece sin tope; con el volumen actual eso no es problema en
  meses, pero es una decisión que hay que revisar, no un olvido.
- No se registran el logout ni el refresh, solo los intentos de ingreso.
- No hay notificación por correo de "ingreso desde un dispositivo nuevo": la bitácora hay
  que ir a mirarla.
