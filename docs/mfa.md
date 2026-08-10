# MFA — Autenticación en dos pasos

Estado: **fase 1 completa, con SMS, correo y TOTP** — modelos (`seguridad/models/mfa_*.py`,
migraciones `0017_mfa` y `0018_mfa_sms`), motor (`seguridad/mfa.py`), endpoints de gestión
(`seguridad/views/mfa.py`) y login en dos pasos (`seguridad/views/autenticacion.py`), con 79
tests en `seguridad/tests.py`.

## 1. Alcance y decisiones de fondo

El MFA es **de la cuenta**, no del contenedor. Un usuario protege su `SegUsuario`, y esa
protección aplica igual en todos los contenedores a los que pertenezca, porque el login es
uno solo y ocurre en el schema público antes de resolver cualquier tenant.

Todo vive en `seguridad/`. Ningún modelo, campo ni endpoint toca `contenedor/` ni los
schemas de tenant.

Tres métodos, **elegibles por el usuario al momento de activar**. El orden es el que ve al
elegir —lo define `METODOS` y lo sirve `/seguridad/mfa/metodos/`—: primero los que no le
exigen instalar nada, y entre esos el correo antes que el SMS, que cuesta por mensaje.

| Método | Fricción | Seguridad | Costo |
|---|---|---|---|
| Código por correo (Zinc) | Ninguna | Media — protege contra clave filtrada, cae si le entran al correo | $0 |
| Código por SMS (Zinc) | Ninguna | La más baja — vulnerable a SIM swap | Por mensaje |
| TOTP (app autenticadora) | Alta la primera vez, nula después | La mejor | $0 |

El motor del desafío es el mismo para los tres; lo único que cambia es de dónde sale el
código: la app lo calcula, o el backend lo genera y lo despacha por `Zinc().correo()` o
`Zinc().sms()`. Los dos últimos comparten el camino de "código enviado"
(`METODOS_ENVIADOS`): se genera acá, se guarda hasheado en el desafío y se manda.

**Sobre el SMS**: es el eslabón más débil de los tres y el único con costo por mensaje. Se
incluye porque un MFA que la gente sí prende vale más que uno fuerte que nadie activa, pero
si se puede empujar a los usuarios hacia el correo o la app, mejor.

### Por qué TOTP además de correo y SMS

TOTP (RFC 6238) no depende de la entregabilidad de nada: el celular calcula
`HMAC(secreto, tiempo / 30s)` truncado a 6 dígitos, y el servidor hace la misma cuenta.
Funciona en modo avión. Sirve cualquier app estándar — Google Authenticator, Microsoft
Authenticator, Authy, 1Password, Bitwarden, o el llavero nativo de iOS y Android.

Se ofrecen correo y SMS como alternativa porque exigir "descargue una app y escanee este QR"
a una base de usuarios administrativos genera soporte, y la reacción típica a la fricción es
desactivar el MFA. Un MFA por correo activo es mejor que un TOTP que nadie prendió.

### El celular para el SMS

Sale de `SegUsuario.celular`, que es texto libre, mientras que `Zinc().sms()` exige diez
dígitos pelados. `celular_para_sms()` normaliza (quita espacios, guiones y el `+57`) y
devuelve `None` si no queda un número colombiano válido.

`configurar` rechaza el método SMS con 400 cuando no hay número usable: si no, el usuario
quedaría con una configuración pendiente que nunca podría confirmar. En cambio al enviar un
código ya en curso, un número inválido solo deja un warning en el log —el desafío existe y
le quedan los códigos de respaldo—, porque tumbar el login no le serviría de nada.

**Cambiar el celular con SMS activo exige el segundo factor.** `SegUsuarioViewSet.update`
pide `mfa_token` y `codigo` en el mismo payload —el `mfa_token` sale de
`/seguridad/mfa/desafio/`— y responde 400 con `codigo: 'mfa_requerido'` si faltan, para que
el front sepa abrir el diálogo. Dos razones: con la sesión secuestrada, cambiar el número
apuntaría los códigos al atacante y le entregaría la cuenta; y sin la validación de formato,
el propio titular podría dejarse sin recibir códigos tecleando mal. Reescribir el mismo
número con otro formato no pide nada, y con método correo o TOTP el celular no es un factor,
así que tampoco.

## 2. Modelos — `seguridad/models/`

Un archivo por modelo, exportados en `models/__init__.py`, como el resto de la app.

| Modelo | Tabla | Rol |
|---|---|---|
| `SegMfaUsuario` | `seg_mfa_usuario` | 1-1 con `SegUsuario`: `metodo`, `secreto` cifrado, `activo`, `ultimo_contador`, fechas |
| `SegMfaCodigoRespaldo` | `seg_mfa_codigo_respaldo` | Los 10 códigos, hash SHA-256 indexado, `usado_en` |
| `SegMfaDesafio` | `seg_mfa_desafio` | UUID, usuario, `metodo`, `hash_codigo` (solo correo y SMS), `expira`, `consumido`, `intentos`, `ip` |
| `SegMfaDispositivo` | `seg_mfa_dispositivo` | `hash_token`, `user_agent`, `ip`, `ultimo_uso`, `expira` |

Las constantes `METODO_SMS` / `METODO_CORREO` / `METODO_TOTP`, más `METODOS` y
`METODOS_ENVIADOS`, viven en `mfa_usuario.py`, junto al modelo que las define, como
`CAMPOS_ACCESO` en `usuario_cliente.py`. `mfa_desafio.py` las importa.

Las migraciones van en `seguridad/`: `0017_mfa` crea las tablas y `0018_mfa_sms` agrega el
método. Cero cambios de esquema en tenants: las cuatro tablas quedan solo en el schema
público.

El `metodo` se copia del `SegMfaUsuario` al `SegMfaDesafio` al crearlo: si el usuario cambia
de método con un desafío en vuelo, ese desafío se resuelve como fue emitido.

### Notas de diseño

- **`SegMfaDesafio` en BD, no en cache.** No hay `CACHES` configurado, así que el cache es
  `LocMemCache`: un espacio por proceso, inservible entre workers de gunicorn. En BD además
  queda el conteo de intentos por desafío (bloqueo a los 5) y la traza de auditoría.
- **`ultimo_contador`** impide reusar un código de 6 dígitos dentro de su ventana de 30 s.
  Es necesario porque se acepta `valid_window=1` (el código anterior y el siguiente) para
  tolerar el desfase de reloj de los celulares.
- **Códigos de respaldo con SHA-256, no pbkdf2.** Son 10 caracteres base32 ≈ 50 bits de
  entropía; verificar 10 hashes pbkdf2 en cada intento sería gasto puro. Se buscan por hash
  indexado.
- **Secreto cifrado con Fernet** y `MFA_ENCRYPTION_KEY` propia, separada de `SECRET_KEY`:
  permite rotar la firma de los JWT sin invalidar todos los MFA, y un dump de la base no
  alcanza para clonar los tokens de nadie.
- **El QR no se genera en el backend.** Se devuelve el URI
  `otpauth://totp/Torio:email?secret=...&issuer=Torio` y Angular lo pinta con `qrcode`.
  Menos dependencias, y el secreto no viaja como imagen.

## 3. Flujo de login en dos pasos

`POST /login/` se mantiene. Orden de validaciones: Turnstile → credenciales → `is_verified`
→ MFA. El desafío solo se crea con la contraseña ya validada, así que el endpoint no
funciona como oráculo de "esta cuenta existe y tiene MFA".

Si el usuario tiene MFA activo y no presenta una cookie de dispositivo recordado válido,
**no se emiten cookies JWT**:

```json
{ "mfa_requerido": true, "mfa_token": "<uuid del desafío firmado>", "metodo": "totp" }
```

`POST /login/mfa/` con `{mfa_token, codigo, recordar_dispositivo}` valida y recién ahí llama
a `_asignar_cookies_auth()`.

El `mfa_token` es el UUID del desafío firmado con `signing.dumps` (salt propio,
`max_age=300`): la firma evita enumerar desafíos, y la fila en BD da consumo único y conteo
de intentos.

`update_last_login` se mueve al paso 2 — hoy se marca antes de completar la autenticación.

### Frecuencia real del segundo paso

El código se pide solo en `POST /login/`, nunca en el refresh ni en las peticiones normales.

| Situación | ¿Pide código? |
|---|---|
| Abrir la app con sesión viva (access token vencido) | No — `RefreshView` renueva en silencio |
| Volver al día siguiente habiendo usado la app ayer | No — la rotación llama a `set_exp()` y la ventana del refresh se desliza |
| Volver tras más de 24 h sin entrar (refresh vencido, prod) | Sí |
| Logout explícito, navegador nuevo, incógnito, cookies borradas | Sí |

El caso incómodo es el usuario esporádico, y por eso **"recordar este dispositivo 30 días"
entra en la fase 1**: una cookie httpOnly firmada, ligada a una fila revocable desde el
perfil, que permite saltar el segundo paso en ese navegador. Es lo que hacen Google, GitHub
y AWS. La alternativa —alargar `REFRESH_TOKEN_LIFETIME`— es más barata pero amplía la
ventana de un refresh token robado; se prefiere mantener el token corto y darle al usuario
un control explícito y revocable.

### Duración de la sesión

Con el segundo factor y el dispositivo recordado en juego, los tiempos **no** se alargan:
cuando el refresh vence, el usuario reingresa correo y clave —que el navegador
autocompleta— y en su equipo habitual no se le pide código. Extender el refresh solo
agrandaría la ventana de un token robado a cambio de nada.

| Parámetro | Valor | Qué controla realmente |
|---|---|---|
| `ACCESS_TOKEN_LIFETIME` | 15 min | Radio de daño de un access token robado, y cuánto tarda `invalidar_sesiones` en surtir efecto (la blacklist solo aplica al refresh) |
| `REFRESH_TOKEN_LIFETIME` | 1 día | No es la duración de la sesión: como la rotación llama a `set_exp()`, es un **timeout por inactividad** |
| `SESION_MAXIMA` | 30 días | Tope absoluto desde el login, contado con el claim `ses` |
| Cookie de dispositivo | 30 días | Cada cuánto se vuelve a pedir el segundo factor |
| Desafío MFA | 5 min | Vida del segundo paso |

**Por qué hizo falta `SESION_MAXIMA`.** Sin tope, `set_exp()` corre el vencimiento en cada
rotación y una sesión en uso continuo no caduca nunca: un refresh token robado que el
atacante rote a diario viviría para siempre, porque el MFA solo se verifica en `/login/` y
él nunca vuelve a pasar por ahí. El claim `ses` guarda el instante del login y se copia en
cada rotación —a diferencia de `iat`, que `set_iat()` reescribe—, así que `RefreshView`
puede cerrar la sesión a los 30 días. Alineado con la cookie de dispositivo, ese re-login
obligatorio tampoco pide código en el equipo de siempre: para el usuario legítimo es
invisible, para el atacante es el final.

En `dev.py` el access baja de 12 h a 1 h: con 12 h no se alcanza a ver el efecto de
blacklistear sesiones y parece un bug.

## 4. Endpoints

### Gestión — `seguridad/views/mfa.py`

Todos operan sobre la cuenta del usuario autenticado. No hay endpoint para administrar el
MFA de un tercero.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/seguridad/mfa/` | Estado: `activo`, `metodo`, `codigos_respaldo_restantes`, dispositivos recordados |
| GET | `/seguridad/mfa/metodos/` | Los métodos que ofrece la aplicación (`codigo` + `nombre`), en el orden en que se muestran |
| POST | `/seguridad/mfa/configurar/` | `{metodo}`. TOTP → devuelve `otpauth_uri` y `secreto`. Correo/SMS → envía el código por Zinc; SMS exige celular válido. Siempre devuelve `mfa_token` |
| POST | `/seguridad/mfa/activar/` | `{mfa_token, codigo}` → activa y devuelve los 10 códigos de respaldo **una sola vez** |
| POST | `/seguridad/mfa/desafio/` | Abre un desafío contra el MFA activo, para operaciones sensibles. Devuelve `mfa_token` |
| POST | `/seguridad/mfa/desactivar/` | `{password, mfa_token, codigo}` — exige clave **y** segundo factor |
| POST | `/seguridad/mfa/codigos-respaldo/` | `{password}` → regenera e invalida los anteriores |
| DELETE | `/seguridad/mfa/dispositivo/<id>/` | Revoca un dispositivo recordado |

`/seguridad/mfa/metodos/` existe para que el selector del front no duplique el catálogo:
las etiquetas y el orden salen de `METODOS`, la misma constante contra la que valida
`configurar`. Un test afirma que las dos listas coinciden.

El enrolamiento pasa por el mismo motor que el login: `configurar` abre un desafío y
`activar` lo resuelve. Así el enrolamiento hereda gratis la expiración, el consumo único y
el tope de intentos, en vez de tener su propia verificación paralela. La única diferencia es
que `activar` no acepta códigos de respaldo: ahí se está probando que el factor **nuevo**
funciona, y un código viejo no prueba eso.

`/seguridad/mfa/desafio/` no estaba en la propuesta original y fue necesario: `desactivar`
exige un código, y con correo o SMS ese código hay que mandarlo antes de poder pedirlo.

### Login — `seguridad/views/autenticacion.py`

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/seguridad/login/mfa/` | `{mfa_token, codigo, recordar_dispositivo}` → emite cookies JWT |
| POST | `/seguridad/login/mfa/reenviar/` | Reenvía el código (solo correo y SMS) |

El reenvío **no** reinicia `intentos` ni `expira`: si lo hiciera, pedir un correo nuevo cada
cinco intentos daría intentos infinitos. Su propio tope lo pone el throttle.

Todos anotados con `@extend_schema` y tag `Autenticación`, como el resto de la app.

### Throttling

Scopes nuevos en `DEFAULT_THROTTLE_RATES`:

```python
'mfa_verificar': '10/min',
'mfa_gestion': '10/hour',
'mfa_envio_codigo': '3/min',
```

El límite que de verdad frena la fuerza bruta sobre 6 dígitos es el contador de intentos de
`SegMfaDesafio`, no el throttle (ver la deuda de la sección 9).

## 5. Experiencia del usuario

**Activación (una sola vez):**

1. Perfil → Activar verificación en dos pasos
2. Elegir método: SMS, correo o app autenticadora
3. TOTP → escanear el QR. Correo/SMS → escribir el código que llegó
4. Confirmar con un código, para verificar que quedó bien sincronizado
5. Se muestran los 10 códigos de respaldo → guardarlos o imprimirlos

**Login:** email y clave → pantalla de 6 dígitos, con casilla "recordar este dispositivo" →
entra.

## 6. Lo que no queda expuesto

- **El reset de clave no es un bypass.** `restablecer_clave` no emite tokens: el usuario
  vuelve a `/login/` y el MFA se le pide igual. Queda comentado en el código para que nadie
  "optimice" ese flujo más adelante.
- **Activar o desactivar MFA blacklistea los refresh tokens vigentes** del usuario. Si un
  atacante ya tenía sesión abierta, activar MFA debe expulsarlo.
- **Recuperación sin dispositivo:** los códigos de respaldo son la **única** vía
  self-service, y la UI debe insistir en guardarlos al activarlo. Sin ellos, el desbloqueo es
  intervención manual del staff desde el admin del schema público. Un "reset de MFA por
  correo" volvería el MFA cosmético, porque el correo es justamente el canal de recuperación
  de la clave.

## 7. Fase 1 — alcance

Al terminarla, un usuario puede activar MFA con app o con correo, entrar con el segundo
factor, recordar su equipo y recuperarse con los códigos de respaldo.

**Dependencias y configuración**

- ✅ `requirements.txt`: `pyotp==2.9.0`, `cryptography==50.0.0`
- ✅ `.env` / `.env.example` + `settings/base.py`: `MFA_ENCRYPTION_KEY`
- ✅ `settings/base.py`: los tres scopes de throttling

**Código**

- ✅ `seguridad/models/mfa_usuario.py`, `mfa_codigo_respaldo.py`, `mfa_desafio.py`, `mfa_dispositivo.py` + migración
- ✅ `seguridad/mfa.py` — módulo de servicio, al estilo de `seguridad/servicios.py`:
  cifrar/descifrar el secreto, generar secreto y `otpauth://` URI, verificar código
  (despacha a TOTP o a correo), generar/consumir códigos de respaldo, crear y consumir
  desafíos borrando los vencidos al crear uno nuevo (así no hace falta un cron), emitir y
  validar el token de dispositivo
- ✅ `seguridad/serializers/mfa.py`, `seguridad/views/mfa.py`, rutas en `seguridad/urls.py`
- ✅ Cambios en `seguridad/views/autenticacion.py` (login en dos pasos y tope de sesión)
- ✅ `SegUsuarioMeSerializer`: `mfa_activo` y `mfa_metodo`
- ✅ Plantilla del correo con el código, en `servicio_mfa.enviar_codigo`

**Tests — `seguridad/tests.py`**

Código válido, inválido, expirado y reusado (replay); desafío consumido dos veces; bloqueo
tras 5 intentos; código de respaldo de un solo uso; login sin MFA sin cambios; dispositivo
recordado salta el paso 2 y deja de hacerlo al revocarlo; `/login/` no revela si la cuenta
existe.

**Orden de implementación**

Modelos y migración → `mfa.py` con sus tests unitarios → endpoints de gestión → login en dos
pasos → dispositivo recordado → tests de integración.

## 8. Fuera de la fase 1

Política obligatoria a nivel de organización y administración del MFA de terceros.

## 9. Deuda que esto destapa

El throttling actual (`login: 5/min`) usa el cache por defecto. Sin `CACHES` configurado eso
es `LocMemCache`: un contador independiente por worker de gunicorn, que además se reinicia en
cada deploy. Con 4 workers el límite real es ~20/min.

No es parte del MFA —por eso los intentos se cuentan en `SegMfaDesafio`— pero conviene
configurar Redis como backend de cache en el mismo ciclo.
