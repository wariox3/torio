# Creación de contenedores

Estado: **implementado**. Vista `contenedor/views/cliente.py` (`create`, `estado`,
`reintentar`), tarea `contenedor/tasks.py` (`crear_contenedor`), guarda en
`seguridad/middleware.py`, con tests en `contenedor/tests_creacion.py` y el caso del
middleware en `contenedor/tests_aislamiento.py` (`ContenedorNoListoTests`). La tarea la
atiende el worker `torio-celery` (`DESPLIEGUE.md` §8.1).

## 1. Por qué

Un contenedor es un schema de PostgreSQL con 126 migraciones y unas 4.550 filas de
catálogos. Antes, `POST /contenedor/cliente/` hacía todo eso dentro de un
`@transaction.atomic`, y eso tenía cuatro problemas:

1. **Nadie podía iniciar sesión mientras alguien creaba un contenedor.** Las migraciones
   del tenant crean FKs hacia tablas del público —`UserTenantPermissions.profile`,
   `GenDocumento.usuario` y `ConMovimiento.usuario` hacia `seg_usuario`, y los grupos y
   permisos hacia `auth_group` y `auth_permission`—. Crear una FK deja la tabla referida
   con `ShareRowExclusiveLock`, que PostgreSQL no suelta hasta el COMMIT y que choca con
   cualquier `INSERT` o `UPDATE`. Medido: la creación tardaba **10 s** con las tres tablas
   bloqueadas, y el login hace `UPDATE seg_usuario` (`update_last_login`).
2. **Dos creaciones a la vez iban en fila y ocupaban a gunicorn.** Con `--workers 2` y
   `--timeout 60`, dos creaciones dejaban la API sin quién atendiera, y cinco o seis en
   cola llegaban al timeout: gunicorn mataba el worker y el cliente recibía un 502.
3. **Dos creaciones con el mismo nombre** pasaban las dos la validación; la segunda
   esperaba los 10 s de la primera en el índice único y terminaba en un 500.
4. **Los catálogos se cargaban en un hilo** sin reintentos, que el reciclaje de gunicorn
   (`--max-requests`) o un `reload` podían cortar, y el fallo solo quedaba en el log.

## 2. Cómo funciona

```
Front                     API (gunicorn)                   Worker torio-celery (cola crear_contenedor)
  │  POST /cliente/  ────►  en ~50 ms, schema público:
  │                         CtnCliente (estado=creando)
  │                         CREATE SCHEMA (vacío)
  │                         CtnDominio, SegUsuarioCliente,
  │                         CtnSuscripcion
  │                         on_commit → encola ─────────────►  1. CREATE SCHEMA IF NOT EXISTS
  │  ◄── 202 {id, estado: "creando"}                          2. migraciones, una transacción cada una
  │                                                           3. UserTenantPermissions del owner
  │  GET /cliente/<id>/estado/  (cada 2 s)                    4. catálogos + semillas (--inicial)
  │  ◄── {estado: "creando", paso: "migraciones"}             5. estado = listo
  │  ◄── {estado: "listo", paso: null}  → entra con X-Tenant
```

### `CtnCliente.estado`

| Valor | Qué significa | `X-Tenant` |
|---|---|---|
| `creando` | Registrado; la tarea lo está construyendo o está en cola | 409 |
| `listo` | Construido y sembrado | normal |
| `error` | La tarea agotó sus reintentos, o RabbitMQ no respondió al encolar | 409 |

- **El default es `listo`**, no `creando`. Todo lo que crea un contenedor con `save()`
  —`TenantTestCase`, el escenario de `tests_aislamiento`, el shell, el admin— lo deja
  completo en ese mismo llamado (`auto_create_schema`). Solo la vista difiere la
  construcción, y es ella la que marca `creando` a propósito. Con default `creando`, el
  middleware bloquearía todos esos contenedores.
- **No es `activo`.** Ese dice si el contenedor está habilitado; este, si terminó de
  construirse.

## 3. El request

`CtnClienteViewSet.create`, en un `atomic` que dura milisegundos:

- **Valida el nombre** contra `CtnCliente.SCHEMA_NAME_VALIDO`
  (`^(?!pg_)[a-z][a-z0-9_]{0,62}$`). No sirve el `is_valid_schema_name` de django-tenants:
  es `^(?!pg_).{1,63}$`, que acepta comillas, y el nombre va interpolado en
  `CREATE SCHEMA "<nombre>"`. Antes de este cambio, ese era un camino de **inyección de
  SQL** para cualquier usuario autenticado.
- **Rechaza un schema huérfano** (`schema_exists`): uno que existe sin su `CtnCliente`
  trae datos de otro.
- **Uno en creación por usuario**, contado en la base, con `select_for_update` sobre la
  fila del usuario para que dos POST suyos simultáneos no pasen los dos. El throttle
  `crear_contenedor` (5/hora) también existe, pero cuenta en Redis y con Redis caído deja
  pasar todo (`IGNORE_EXCEPTIONS`).
- **Guarda con `auto_create_schema = False` en la instancia**, no en la clase: el `save()`
  de django-tenants migraría ahí mismo. El `IntegrityError` de dos nombres iguales a la
  vez sale como 400, y ahora al instante: la fila se confirma en milisegundos.
- **Crea el schema vacío.** Podría hacerlo solo la tarea, pero `migrate_schemas` de cada
  deploy recorre todos los `CtnCliente` y se cae con uno que no tenga schema, como uno
  que quedó en `error` porque RabbitMQ no respondió. `CREATE SCHEMA` no toca ninguna
  tabla, así que no bloquea nada.
- **Crea la membresía del owner**, pero no sus permisos. `UserTenantPermissions` vive en
  el schema del tenant, que todavía no tiene tablas; lo crea la tarea. Esta es la única
  excepción a la regla de `add_user` de escribir las dos filas juntas, y es segura porque
  hasta `listo` el middleware no deja entrar a nadie. A cambio, el contenedor aparece en
  `lista-usuario` desde el primer segundo, con su `estado`.
- **Encola con `on_commit`.** Antes del COMMIT, el worker no vería el contenedor. Si
  RabbitMQ no responde, lo pasa a `error` (y no lo deja en `creando`, de donde solo se
  sale a los 30 minutos).

## 4. La tarea

`contenedor.tasks.crear_contenedor(cliente_id)`. Con `acks_late` puede correr dos veces,
y un worker puede morir a mitad, así que **cada paso se puede repetir y la tarea retoma
donde quedó**:

| Paso | Por qué se puede repetir |
|---|---|
| Toma el candado del contenedor, o sale | Dos ejecuciones a la vez para el mismo contenedor (ver abajo) |
| Sale si no está en `creando` | Una entrega repetida de uno ya listo o fallido no hace nada |
| `CREATE SCHEMA IF NOT EXISTS` | — |
| `migrate_schemas --schema <nombre>`, **fuera de un `atomic`** | Cada migración hace su COMMIT y queda en `django_migrations` del schema; al repetir, solo corren las que faltan |
| `UserTenantPermissions` del owner | `get_or_create` |
| `cargar_datos_tenant --schema <nombre> --inicial` | Ya era idempotente |
| `estado = listo` | `update` filtrado por `estado=creando` |

**Lo central es el segundo paso.** Sin el `atomic` de afuera, cada migración suelta sus
locks al terminar, y el `ShareRowExclusiveLock` sobre `seg_usuario` dura milisegundos en
vez de toda la creación. Medido contra la base de desarrollo: durante una creación
completa de 10,9 s, 159 `UPDATE` a `seg_usuario` esperaron **como máximo 69 ms** (mediana
8 ms). Antes esperaban los 10 s.

**Fallas.** Reintenta 3 veces, a los 30 s, 1 min y 2 min, porque lo que suele fallar acá
es la base y se arregla solo. Agotados los reintentos, `estado = error` y el traceback al
log y a Sentry. El `soft_time_limit` de 10 minutos convierte una migración colgada en una
falla normal, que se reintenta; el `time_limit` de 11 mata el proceso si ni eso alcanza.

**Avance.** Cada paso se anota en Redis (`contenedor:<id>:paso`, una hora), y
`GET /contenedor/cliente/<id>/estado/` lo devuelve. Es lo único de este diseño que vive en
Redis: si se cae, el front ve el `estado` sin `paso`. El `estado` va en la base porque con
`IGNORE_EXCEPTIONS` un Redis caído responde vacío, y un contenedor a medio crear pasaría
el middleware.

### El worker

Cola propia, `crear_contenedor`, atendida por el mismo `torio-celery` de las
notificaciones (`DESPLIEGUE.md` §8.1), que tiene dos procesos. En desarrollo, la cola va
en el `-Q` del worker de siempre (`torioapp/celery.py`).

- **Por qué no uno aparte.** El problema de fondo —el lock sobre `seg_usuario`— lo
  resuelve que cada migración haga su COMMIT, no el worker: dos creaciones en paralelo
  apenas se estorban. Un worker propio sería un servicio más que vigilar y una conexión
  más a CloudAMQP.
- **El costo.** Una ráfaga de altas puede ocupar los dos procesos y demorar las
  notificaciones unos 20 s por contenedor; no se pierden. Con el throttle y el límite de
  uno en creación por usuario, hace falta que muchos usuarios creen a la vez. Si pasa
  seguido, se le da a `crear_contenedor` un worker propio moviendo la cola de `-Q`, sin
  tocar código.
- **El candado.** Con dos procesos, dos ejecuciones para el **mismo** contenedor pueden
  coincidir —un reintento doble de uno atascado, una re-entrega de `acks_late`— y
  migrarían el mismo schema a la vez. `_candado` toma un `pg_try_advisory_lock` por
  contenedor, y la que no lo consigue sale sin hacer nada. Va en una conexión propia:
  `migrate_schemas` cierra la de Django al terminar, lo que soltaría un lock de sesión a
  mitad de camino; y si el proceso muere, PostgreSQL lo suelta solo.

**Deploys.** `migrate` recorre todos los tenants y no puede migrar el mismo schema que
una creación en curso. Por eso el script de actualización detiene `torio-celery` antes de
`migrate` y lo arranca al final (§10); `stop` espera a que termine la tarea que tenga
entre manos, y las que lleguen mientras tanto esperan en RabbitMQ.

## 5. Endpoints

| Endpoint | Quién | Qué |
|---|---|---|
| `POST /contenedor/cliente/` | autenticado | 202 con el contenedor en `creando`. 400 nombre inválido o ya registrado; 409 si ya tiene uno en creación |
| `GET /contenedor/cliente/<id>/estado/` | miembro | `{estado, paso}`. `paso` solo en `creando`, y puede venir `null` |
| `POST /contenedor/cliente/<id>/reintentar/` | owner | Si está en `error`, o en `creando` hace más de 30 min: lo vuelve a encolar (202). 409 si está listo o se sigue creando |
| `DELETE /contenedor/cliente/<id>/` | superusuario; en `error`, owner | 409 en `creando`: sería tirarle el schema debajo a la tarea |
| `PUT/PATCH /contenedor/cliente/<id>/` | superusuario | 409 si no está `listo` |

- **`reintentar` y `DELETE` en `error` autorizan por owner**, no por `es_superusuario`:
  esa consulta lee `UserTenantPermissions` en el schema del tenant, que en uno fallido
  puede no tener tablas.
- **Reintentar dos veces uno atascado** encola dos tareas, y no pasa nada: si coinciden,
  el candado deja pasar solo a una, y si no, la segunda lo encuentra `listo`.

## 6. Lo que se ajustó alrededor

Todo lo que entra a un schema de tenant tiene que ignorar a los que no están listos:

- **`TenantHeaderMiddleware`**: 409 con `{detail, estado}`, antes de autenticar.
- **`cargar_datos_tenant` sin `--schema`**: solo los `listo`. Con `--schema` sí entra,
  porque así lo llama la tarea.
- **Webhook de rededoc**: uno que no está listo cuenta como cliente desconocido (404), y
  rededoc reintenta.
- **Invitaciones**: no se invita a uno que no está listo (400). Aceptar escribiría
  `UserTenantPermissions` en un schema sin tablas.

## 7. Para el front

- `POST` responde **202** y el contenedor todavía no se puede usar: consultar `estado/`
  hasta `listo`, mostrando `paso`.
- `lista-usuario` trae `estado`: los que están en `creando` o `error` se muestran con su
  acción (esperar, reintentar, eliminar) en vez de dejar entrar.
- Cualquier petición con `X-Tenant` puede responder **409** con `estado`.
