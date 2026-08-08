# MFA — Autenticación en dos pasos

Propuesta de diseño. Estado: **modelos y migración implementados** (un archivo por modelo en `seguridad/models/`,
migración `0017_mfa`). Lo demás, pendiente.

## 1. Alcance y decisiones de fondo

El MFA es **de la cuenta**, no del contenedor. Un usuario protege su `SegUsuario`, y esa
protección aplica igual en todos los contenedores a los que pertenezca, porque el login es
uno solo y ocurre en el schema público antes de resolver cualquier tenant.

Todo vive en `seguridad/`. Ningún modelo, campo ni endpoint toca `contenedor/` ni los
schemas de tenant.

Dos métodos, **elegibles por el usuario al momento de activar**:

| Método | Fricción | Seguridad | Costo |
|---|---|---|---|
| TOTP (app autenticadora) | Alta la primera vez, nula después | La mejor | $0 |
| Código por correo (Zinc) | Ninguna | Media — protege contra clave filtrada, cae si le entran al correo | $0 |

El motor del desafío es el mismo para ambos; lo único que cambia es de dónde sale el
código: la app lo calcula, o el backend lo genera y lo manda por `Zinc().correo()`.

**SMS queda fuera**: es el método más débil (SIM swap) y el único que cuesta por mensaje.

### Por qué TOTP y no solo correo

TOTP (RFC 6238) no depende de la entregabilidad de nada: el celular calcula
`HMAC(secreto, tiempo / 30s)` truncado a 6 dígitos, y el servidor hace la misma cuenta.
Funciona en modo avión. Sirve cualquier app estándar — Google Authenticator, Microsoft
Authenticator, Authy, 1Password, Bitwarden, o el llavero nativo de iOS y Android.

Se ofrece correo como alternativa porque exigir "descargue una app y escanee este QR" a
una base de usuarios administrativos genera soporte, y la reacción típica a la fricción es
desactivar el MFA. Un MFA por correo activo es mejor que un TOTP que nadie prendió.

## 2. Modelos — `seguridad/models/`

Un archivo por modelo, exportados en `models/__init__.py`, como el resto de la app.

| Modelo | Tabla | Rol |
|---|---|---|
| `SegMfaUsuario` | `seg_mfa_usuario` | 1-1 con `SegUsuario`: `metodo`, `secreto` cifrado, `activo`, `ultimo_contador`, fechas |
| `SegMfaCodigoRespaldo` | `seg_mfa_codigo_respaldo` | Los 10 códigos, hash SHA-256 indexado, `usado_en` |
| `SegMfaDesafio` | `seg_mfa_desafio` | UUID, usuario, `metodo`, `hash_codigo` (solo correo), `expira`, `consumido`, `intentos`, `ip` |
| `SegMfaDispositivo` | `seg_mfa_dispositivo` | `hash_token`, `user_agent`, `ip`, `ultimo_uso`, `expira` |

Las constantes `METODO_TOTP` / `METODO_CORREO` / `METODOS` viven en `mfa_usuario.py`, junto al
modelo que las define, como `CAMPOS_ACCESO` en `usuario_cliente.py`. `mfa_desafio.py` las importa.

Una sola migración, en `seguridad/`. Cero cambios de esquema en tenants: las cuatro tablas
quedan solo en el schema público.

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

## 4. Endpoints

### Gestión — `seguridad/views/mfa.py`

Todos operan sobre la cuenta del usuario autenticado. No hay endpoint para administrar el
MFA de un tercero.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/seguridad/mfa/` | Estado: `activo`, `metodo`, `codigos_respaldo_restantes`, dispositivos recordados |
| POST | `/seguridad/mfa/configurar/` | `{metodo}`. TOTP → devuelve `otpauth_uri`. Correo → envía código por Zinc |
| POST | `/seguridad/mfa/activar/` | `{codigo}` → activa y devuelve los 10 códigos de respaldo **una sola vez** |
| POST | `/seguridad/mfa/desactivar/` | `{password, codigo}` — exige ambos |
| POST | `/seguridad/mfa/codigos-respaldo/` | `{password}` → regenera e invalida los anteriores |
| DELETE | `/seguridad/mfa/dispositivo/<id>/` | Revoca un dispositivo recordado |

### Login — `seguridad/views/autenticacion.py`

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/login/mfa/` | `{mfa_token, codigo, recordar_dispositivo}` → emite cookies JWT |
| POST | `/login/mfa/reenviar/` | Reenvía el código (solo método correo) |

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
2. Elegir método: app autenticadora o correo
3. TOTP → escanear el QR. Correo → escribir el código que llegó
4. Confirmar con un código, para verificar que quedó bien sincronizado
5. Se muestran los 10 códigos de respaldo → guardarlos o imprimirlos

**Login:** email y clave → pantalla de 6 dígitos, con casilla "recordar este dispositivo" →
entra.

## 6. Lo que no queda expuesto

- **El reset de clave no es un bypass.** `restablecer_clave` no emite tokens: el usuario
  vuelve a `/login/` y el MFA se le pide igual. Conviene dejarlo comentado en el código para
  que nadie "optimice" ese flujo más adelante.
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

- `requirements.txt`: `pyotp==2.9.0`, `cryptography`
- `.env` + `settings/base.py`: `MFA_ENCRYPTION_KEY`
- `settings/base.py`: los tres scopes de throttling

**Código**

- `seguridad/models/mfa_usuario.py`, `mfa_codigo_respaldo.py`, `mfa_desafio.py`, `mfa_dispositivo.py` + migración
- `seguridad/mfa.py` — módulo de servicio, al estilo de `seguridad/servicios.py`:
  cifrar/descifrar el secreto, generar secreto y `otpauth://` URI, verificar código
  (despacha a TOTP o a correo), generar/consumir códigos de respaldo, crear y consumir
  desafíos borrando los vencidos al crear uno nuevo (así no hace falta un cron), emitir y
  validar el token de dispositivo
- `seguridad/serializers/mfa.py`, `seguridad/views/mfa.py`, rutas en `seguridad/urls.py`
- Cambios en `seguridad/views/autenticacion.py` (login en dos pasos)
- `SegUsuarioMeSerializer`: agregar `mfa_activo` y `mfa_metodo`
- Plantilla del correo con el código, en el estilo de los que ya manda `Zinc()`

**Tests — `seguridad/tests.py`**

Código válido, inválido, expirado y reusado (replay); desafío consumido dos veces; bloqueo
tras 5 intentos; código de respaldo de un solo uso; login sin MFA sin cambios; dispositivo
recordado salta el paso 2 y deja de hacerlo al revocarlo; `/login/` no revela si la cuenta
existe.

**Orden de implementación**

Modelos y migración → `mfa.py` con sus tests unitarios → endpoints de gestión → login en dos
pasos → dispositivo recordado → tests de integración.

## 8. Fuera de la fase 1

MFA por SMS, política obligatoria a nivel de organización, y administración del MFA de
terceros.

## 9. Deuda que esto destapa

El throttling actual (`login: 5/min`) usa el cache por defecto. Sin `CACHES` configurado eso
es `LocMemCache`: un contador independiente por worker de gunicorn, que además se reinicia en
cada deploy. Con 4 workers el límite real es ~20/min.

No es parte del MFA —por eso los intentos se cuentan en `SegMfaDesafio`— pero conviene
configurar Redis como backend de cache en el mismo ciclo.
