# Portal del empleado — app móvil para turnos y nóminas

Estado: **propuesta, nada implementado**. El paso 1 del plan tiene forma concreta y está
esperando visto bueno (ver §10). Documento de decisión escrito el 2026-09-07 contra
`main @ fe710aa`. Versión con diagramas:
<https://claude.ai/code/artifact/37891f62-cc5d-4239-bd1d-029f0be26c23>

## 1. La decisión

**Un solo backend (este), un solo emisor de tokens, dos superficies de API separadas por un
claim.** La app móvil del empleado se autentica contra el mismo `POST /seguridad/login/` que
el ERP, pero su sesión lleva un claim propio que le abre una API de solo lectura y le cierra
la del ERP.

Debajo de eso hay una separación que es la que sostiene todo lo demás:

> **La cuenta es de la persona. El vínculo laboral es del tenant.**

Una persona tiene un `SegUsuario` para toda su vida: su correo, su clave, su MFA. Lo que
cambia con el tiempo es de qué contenedor es empleada, y en qué papel entra a cada uno. Eso
son filas aparte, y son lo que hay que construir: hoy no existen.

### Lo decidido

Todo esto está resuelto y ya está incorporado al diseño de las secciones que siguen. Se decidió
el 2026-09-07.

| Tema | Qué quedó | Dónde |
|---|---|---|
| Vínculo | Apunta al `GenContacto`, no al `HumContrato`: los contratos van y vienen dentro de la misma relación con la empresa | §4 |
| Acceso | La fila es el permiso. Sin campo `estado`: si existe hay acceso, si no, no. Se quita borrándola, y lo hace un administrador del contenedor | §4 |
| Enrolamiento | Lo inicia el empleado con tres factores: código de la empresa + su `numero_identificacion` + correo que coincida con el del contacto | §4 |
| Correo | La comparación es siempre contra el correo personal (`GenContacto.correo`) | §4 |
| Cuenta | Verificación de correo obligatoria y por OTP. El MFA sigue opcional, pero si se activa aplica también a la app | §5 |
| Alcance | Autenticación y lectura: turnos y nóminas. Sin certificados y sin notificaciones | §11 |

## 2. Por qué no un backend aparte

Los tres datos que quiere ver el empleado viven en el schema de su tenant: los turnos en
`turno/` (`TurProgramacion`, `TurTurno`, `TurPuesto`), los contratos y las liquidaciones en
`humano/`. Un backend separado tendría que hablarle a la misma base con una copia de esos
modelos —dos definiciones del mismo esquema que se desincronizan en la primera migración— o
consumir una API de torio, y esa API hay que escribirla igual.

Duplicar la autenticación sería peor. Ya está lo difícil: MFA por correo, SMS y TOTP,
códigos de respaldo, dispositivos recordados, rotación de refresh con blacklist, tope
absoluto de sesión en el claim `ses` y la bitácora de `SegAcceso` (ver `docs/mfa.md` y
`docs/accesos.md`). Un segundo emisor de tokens es un segundo lugar donde equivocarse.

Y hay una razón que aparece recién cuando se mira el caso real: **una misma persona puede ser
usuaria del ERP y empleada al mismo tiempo**. Con dos backends serían dos cuentas, dos claves
y dos MFA para la misma persona, y ninguna forma de saber que son la misma. Con uno solo es
una cuenta con dos papeles.

Del lado del cliente no hay obstáculo: `SegCookieJWTAuthentication`
(`seguridad/authentication.py`) ya acepta `Authorization: Bearer` además de la cookie
httpOnly, así que una app móvil entra sin tocar el mecanismo.

## 3. Una cuenta, varios papeles

La jefa de recursos humanos usa el ERP y además es empleada de la empresa: le pagan nómina,
tiene contrato y pide su certificado laboral como cualquiera. Un guarda solo es empleado. Un
contador externo solo es usuario del ERP. Los tres son `SegUsuario` en el schema público, y
lo que los distingue son **dos vínculos independientes con cada contenedor**:

| Vínculo | Tabla | Qué habilita | Quién lo crea |
|---|---|---|---|
| Usuario del ERP | `SegUsuarioCliente` (existe) | La API del ERP, con los grupos y permisos que le hayan dado | El propietario del contenedor, al invitar |
| Empleado | `SegUsuarioEmpleado` (**falta**) | La API del portal, solo sus propios datos | RRHH, al enrolar |

Los dos son independientes: se puede tener uno, el otro, o los dos en el mismo contenedor.

De ahí sale la regla que gobierna el login: **la superficie la pide el cliente y la autoriza
el backend, cada una contra su propio vínculo.** La app pide una sesión de portal y el
backend se la da si existe el vínculo de empleado; el Angular pide una sesión de ERP y el
backend se la da si hay membresía. Quien tiene los dos papeles obtiene **dos sesiones
distintas**, nunca un token que sirva para las dos cosas. Que la jefa de RRHH pueda ver la
nómina de todos es una decisión del ERP y de sus grupos; en el portal ve la suya, como
cualquiera.

## 4. El vínculo laboral y el enrolamiento

Un empleado hoy es un `GenContacto` con un `HumContrato` en el schema del tenant. Un usuario
es un `SegUsuario` en el público. Nada une las dos mitades, y ese es el trabajo real.

El vínculo va en el **schema público**, no en el del tenant, y la razón es el login: la
sesión se emite antes de resolver ningún schema, así que el backend tiene que poder responder
"¿de qué contenedores es empleada esta persona?" sin recorrer todos los schemas de la base.
Es exactamente la forma que ya tiene `SegUsuarioCliente`, y por eso el modelo nuevo se le
parece:

```
  SCHEMA PÚBLICO                                  SCHEMA DEL TENANT «alfa»

  SegUsuario ──┬── SegUsuarioCliente ────────▶  grupos y permisos del ERP
  la persona   │   membresía del ERP
  correo·clave │
  MFA          └── SegUsuarioEmpleado ───────▶  GenContacto ──▶ HumContrato ──┬─▶ TurTurno
                   cliente · contacto_id           (contacto_id)              │
                   fecha_enrolamiento                                         └─▶ HumLiquidacion
```

`contacto_id` es el id del `GenContacto` dentro de ese schema: un entero que no significa
nada fuera de él, y que solo se resuelve después de que el middleware ya puso el tenant. La
llave es explícita y **nunca un cruce por `numero_identificacion`**, que no es único en
ninguna de las dos puntas (`SegUsuario` lo tiene nulable, `GenContacto` sin `unique`): una
coincidencia equivocada le muestra la nómina de otro a alguien.

### El vínculo no tiene estados

**La fila es el permiso, y es todo el permiso.** Si existe la fila, esa persona puede abrir
sesión de portal contra ese contenedor y ver sus datos; si no existe, no puede. No hay
`estado`, no hay `activo` ni `terminado` ni `anulado`, y no hay nada que interpretar al
autorizar: la consulta es «¿hay fila?».

El acceso se quita **borrando la fila**, y eso lo hace un administrador del contenedor desde
el ERP. No caduca solo, y terminar un contrato tampoco lo corta: mientras la fila esté, el ex
empleado sigue viendo sus datos, que es lo que se decidió al atarlo al contacto y no al
contrato.

Lo que se pierde con esto es la posibilidad de dejar a alguien en modo «solo historia», sin
ver el presente. No hace falta: un ex empleado no tiene turnos futuros que ver, así que la
distinción no cambiaba nada en la práctica y sí obligaba a decidir el estado en cada consulta.

**Borrar sí borra el rastro.** No hay tabla de enrolamientos ni de intentos, así que una vez
borrada la fila no queda registro de que esa persona tuvo acceso a esa empresa. Es el precio
de no guardar estados: se asume a sabiendas, y si algún día hace falta auditarlo, la respuesta
es una tabla de intentos de enrolamiento y no un estado en el vínculo.

### Cambio de empleador

Es el caso que hay que tener resuelto desde el diseño, no después: la persona sale de un
contenedor y entra a otro, o trabaja en dos a la vez durante el mes de traslape.

- **La cuenta no se toca.** El `SegUsuario` es de la persona: conserva su correo, su clave,
  su MFA y su historial de accesos. Nadie crea una cuenta nueva por cambiar de empresa.
- **Se abre un vínculo nuevo y el viejo se queda, o no.** El del contenedor anterior sobrevive
  mientras su administrador no lo borre; el nuevo se crea al enrolarse. Las dos filas conviven
  sin problema: nada obliga a que haya una sola.
- **El enrolamiento nuevo encuentra la cuenta que ya existe**, no la duplica. La persona se
  vincula desde la app con la clave que ya tenía, y le aparece la empresa nueva en el
  selector.
- **Un token no cruza de contenedor.** La sesión de portal queda atada al contenedor que se
  eligió (ver la sección siguiente), así que un token de la empresa vieja no lee datos de la
  nueva ni al revés.

### Cómo se enrola

Lo inicia el empleado, no RRHH. La persona ya tiene cuenta —se registró con el flujo normal—
y desde la app se vincula a su empresa:

1. **Escribe el código de la empresa.** Es un campo nuevo, `CtnCliente.codigo`, un varchar
   configurable que el contenedor le da a su gente. Resuelve contra qué schema se va a buscar.
2. **El backend busca el contacto por el `numero_identificacion` de la cuenta**, dentro de ese
   schema. No lo escribe el usuario: sale de su `SegUsuario`.
3. **Compara los dos correos personales.** El de la cuenta (`SegUsuario.email`) y el del
   contacto (`GenContacto.correo`) tienen que ser el mismo. Siempre se compara contra el
   correo personal de la persona, nunca contra uno corporativo.
4. **Si los dos coinciden, queda enrolado**: se crea la fila de `SegUsuarioEmpleado` con el
   `contacto_id` que se acaba de resolver.

La prueba de identidad son las tres cosas juntas: hay que saber el código de la empresa, tener
la identificación registrada en la nómina de esa empresa, y controlar el correo personal que
RRHH tiene en ese contacto.

**Cuatro reglas que se derivan de esto y hay que respetar al implementarlo:**

- **La identificación no es única en `GenContacto`** (`CharField` sin `unique`). Si la búsqueda
  devuelve más de un contacto, el enrolamiento se rechaza por ambiguo en vez de escoger uno.
  Es el mismo criterio que ya aplica `_Indice` en el importador de detalles.
- **Una cuenta sin `numero_identificacion` no puede enrolarse.** El campo es nulable en
  `SegUsuario`, así que el error tiene que decirlo en vez de fallar buscando `None`.
- **El error es siempre el mismo.** Distinguir «no hay contacto con esa identificación» de «el
  correo no coincide» convierte el endpoint en un oráculo para averiguar quién trabaja en una
  empresa. Un solo mensaje para los dos casos.
- **Ese endpoint necesita límite de intentos de verdad** (ver el detalle abajo). El código de
  empresa es lo más adivinable de los tres factores.

### El límite de intentos del enrolamiento

**Solo el throttle de DRF, sin nada más.** Un scope propio, `enrolamiento`, en
`DEFAULT_THROTTLE_RATES`, al lado de los que ya existen (`login: 5/min`, `registro: 5/hour`).
El endpoint exige sesión, así que cuenta por cuenta autenticada, no por IP anónima.

```python
'enrolamiento': '10/hour',
```

Lo que hay que saber de ese freno, para no confiarle más de lo que aguanta:

- **Cuenta por worker.** No hay `CACHES`, así que el throttle vive en la memoria de cada
  proceso de gunicorn: con cuatro workers el límite efectivo son cuarenta intentos por hora,
  no diez. Es un freno a la inundación, no un muro.
- **No hay conteo en base.** Se evaluó y se descartó: nada de tabla de intentos, nada de
  ventana deslizante. Si en algún momento el barrido se vuelve un problema real, ese es el
  camino —es lo que hace `SegMfaDesafio` con su contador de `intentos`— pero no se implementa
  ahora.
- **Sin traza de enrolamiento.** Como no hay tabla de intentos, borrar un vínculo borra el
  rastro: no queda registro de quién estuvo enrolado en qué empresa ni desde cuándo. `SegAcceso`
  guarda los inicios de sesión, pero no la empresa.
- **Pasarse del límite no cambia el mensaje**, solo agrega el «intenta más tarde». Decir
  «demasiados intentos con ese código» confirmaría que el código existe.

**Nota sobre el canal lateral:** un código que no existe responde sin tocar el schema del
tenant, y uno que sí existe hace una consulta más. La diferencia de tiempo es medible si
alguien se lo propone. No se cierra con tiempo constante —es caro y frágil— y con el throttle
por worker tampoco queda cerrada por el límite: es un riesgo asumido, no uno resuelto.

### El correo del contacto es el personal

La comparación se hace **siempre contra el correo personal**, y en el modelo eso es
`GenContacto.correo`: es el único campo de correo del contacto —el otro,
`correo_facturacion_electronica`, es para la DIAN—. En el contacto de un empleado ese campo
tiene que ser su dirección personal, no la corporativa.

No es una preferencia, se cae de dos lados:

- **La cuenta sobrevive al empleo.** El `USERNAME_FIELD` de `SegUsuario` es el correo. Con el
  corporativo, la persona pierde el día que renuncia la dirección con la que se identifica, la
  recuperación de clave y el segundo factor por correo — y con eso el acceso a su propia
  historia laboral, que es justo lo que el portal le tiene que seguir mostrando.
- **El enrolamiento en la empresa siguiente.** El correo de la cuenta es uno solo y tiene que
  coincidir con el contacto de *cada* empresa donde trabaje. Si cada contenedor guarda su
  correo corporativo, solo puede enrolarse en uno.

Para RRHH es una disciplina de captura: el correo del contacto de un empleado es el que la
persona conserva cuando se va. Si en algún momento hace falta guardar los dos, sería un campo
aparte en `GenContacto` — no está propuesto acá.

## 5. Verificar la cuenta, y el MFA que el empleado no está obligado a usar

**La verificación de correo es obligatoria y ya existe.** `POST /seguridad/login/` rechaza a
quien no la haya hecho (`seguridad/views/autenticacion.py:155`), así que esto no es una regla
nueva del portal: es la que ya rige. Y es lo que sostiene el tercer factor del enrolamiento —
nadie llega a compararse contra el correo de un contacto sin haber probado que controla ese
buzón.

**Lo que hay que cambiar es la forma.** Hoy la verificación es un enlace firmado a
`{FRONTEND_URL}/auth/verify-email?token=...`, o sea un rebote al Angular. En un teléfono eso
es salir de la app, abrir el navegador y volver. Para el portal la verificación es un **código
que la persona teclea en la app**.

No hace falta inventar el mecanismo: `seguridad/mfa.py` ya genera códigos, los guarda
hasheados, los manda con `Zinc().correo()` y cuenta los intentos en base. La variante OTP de
la verificación se apoya en eso. El enlace se queda para el registro desde el ERP; son dos
caminos al mismo `is_verified`.

**El MFA es aparte, y sigue siendo opcional.** Es de la cuenta y no del contenedor (ver
`docs/mfa.md`), así que a nadie se le exige por ser empleado. El SMS es el que menos conviene
empujar: cuesta por mensaje y Zinc solo entrega en Colombia.

**Pero si la persona lo activa, le aplica en la app.** El login es el mismo: con MFA activo y
el dispositivo no recordado, `POST /seguridad/login/` no devuelve sesión sino
`{mfa_requerido, mfa_token, metodo}`, y la sesión sale de `POST /seguridad/login/mfa/`. De ahí
salen dos obligaciones para la app:

- **Implementar el login en dos pasos desde el primer día**, aunque casi nadie active MFA. Si
  la app solo sabe el camino corto, el día que alguien active su segundo factor queda fuera y
  no entiende por qué.
- **Usar el dispositivo recordado** (`SegMfaDispositivo`). En un teléfono personal es lo que
  hace tolerable el MFA: se pide una vez y no en cada entrada.

## 6. La compuerta del claim

El permiso por defecto del proyecto es `EsMiembroDelTenant` + `SuscripcionVigente`
(`torioapp/settings/base.py:136`): **ser miembro del contenedor alcanza**. Solo 34 de los 118
viewsets declaran `TienePermisoModelo`. Si a un empleado se le da una membresía normal para
que entre a la app, se le está dando lectura de los otros 84: contactos, documentos,
movimientos contables, la nómina de todos.

No se arregla en la app: se arregla haciendo que el token del empleado sea inútil contra el
ERP aunque alguien apunte la URL a mano.

```
  App móvil ──┐                              ┌──────────── un codebase, un Postgres ───────┐
  (empleado)  │                              │                                             │
              ├─▶ POST /seguridad/login/ ──┬─┼─▶ urls_portal                               │
  Angular ────┘   un solo emisor           │ │   exige app: portal + ten: <schema>         │
  (ERP)           MFA · rotación           │ │   solo lectura, filtrado por el vínculo     │
                                           │ │        ▲                                    │
                        token de portal    │ │        ✗ rechazado                          │
                        app + ten + vin ───┘ │        │                                    │
                        token de ERP ────────┼─▶ urls_tenant · urls_public                 │
                        sin el claim         │   el ERP completo, 118 viewsets             │
                                             └─────────────────────────────────────────────┘
```

Reglas que se derivan de eso:

- **El claim lo emite el login, no lo pide el token.** El cliente dice qué superficie quiere;
  el backend la concede solo si el vínculo correspondiente existe. Para el ERP eso es la
  membresía; para el portal, la fila de `SegUsuarioEmpleado`.
- `urls_portal` exige el claim; `urls_tenant` y `urls_public` lo rechazan. La regla vive en
  la puerta, no en cada viewset nuevo que alguien agregue.
- **La sesión de portal va atada al contenedor.** Lleva el schema en el token (`ten`) y el
  vínculo (`vin`), y el permiso exige que coincidan con el tenant que resolvió el
  middleware. En el ERP el `X-Tenant` se comprueba por request contra la membresía; en el
  portal el header es apenas una pista de ruteo y **manda el token**, que es lo que impide
  que una persona con dos empleadores lea el contenedor equivocado.
- **Una sesión por contenedor.** Si la persona tiene dos vínculos activos, elige empresa y
  eso emite el token de esa empresa; cambiar de empresa en la app es volver a pedir sesión,
  no cambiar un header.
- Dentro del portal, cada queryset se filtra por el `contacto_id` del vínculo del token y
  **nunca por un parámetro**. El patrón ya existe: `GET /seguridad/acceso/` filtra por
  `request.user` y no acepta que le digan de quién quiere ver el historial.
- `SegAcceso` debería registrar con qué superficie se abrió la sesión. Hoy distingue el
  resultado del intento pero no el cliente, y con dos apps sobre el mismo login esa columna
  es la diferencia entre una auditoría útil y una lista de correos.

## 7. Despliegue

Un solo codebase, dos procesos de gunicorn: uno sirviendo el ERP y otro sirviendo
`urls_portal` de cara a internet, con su propio límite de tasa. Es el aislamiento operativo
que se buscaba con el backend aparte —que cientos de empleados abriendo la app un lunes a
las 6am no le tumben el ERP a la oficina— sin el segundo codebase.

## 8. Lo que hay que arreglar antes de abrirlo a internet

| | Qué | Por qué |
|---|---|---|
| **Bloqueante** | El token del empleado no puede servir contra el ERP | Es la razón de ser de la compuerta. Sin ella, cualquier cuenta de empleado con membresía lee medio ERP. |
| **Bloqueante** | El token de portal atado al contenedor | Sin eso, una persona con dos empleadores puede leer el contenedor equivocado cambiando un header. |
| **Bloqueante** | Límite de intentos que limite de verdad | No hay backend de `CACHES`, así que `login: 5/min` son cinco **por worker**. Hace falta Redis, o contar en base como ya hace el desafío de MFA. |
| Antes de salir | Cierre de acceso al borrar el vínculo | Terminar el contrato no corta el acceso; borrar la fila sí, y ahí las sesiones vivas de ese contenedor tienen que morir, no esperar a que expire el refresh. |
| Antes de salir | Sesión pensada para navegador | Refresh de 1 día por inactividad (`REFRESH_TOKEN_LIFETIME`) obliga al empleado a hacer login con MFA cada dos días. Hace falta un perfil propio del portal, atado al dispositivo. |
| A vigilar | Cambia la escala de usuarios | Hoy los `SegUsuario` son los del contenedor: decenas. Mañana son todos los empleados de todos los contenedores, con su foto, su MFA y su bitácora. |

## 9. Lo que queda por decidir

Lo demás ya está decidido y vive en las secciones de arriba; el registro está en §1. Quedan
tres, y ninguna bloquea el paso 1.

**Empresas simultáneas — ¿el selector siempre, o solo cuando hay más de una?**
*Recomendación:* si hay un solo vínculo, entrar directo; el selector aparece con dos o más.

**Membresía del ERP — ¿el empleado también recibe una?**
*Recomendación:* no. El vínculo de empleado es suficiente para el portal, y una membresía
`SegUsuarioCliente` sin grupos igual abre los 84 viewsets que solo comprueban membresía. Que
sean dos tablas distintas es justamente lo que evita ese error.

**Sesión — ¿cuánto dura en el teléfono?**
*Recomendación:* refresh de 30 días con rotación, y cierre inmediato cuando el vínculo deja de
existir. Lo segundo importa más que lo primero.

## 10. Orden de trabajo

Los tres primeros pasos no producen nada visible en el teléfono.

1. **`SegUsuarioEmpleado`** en el schema público —cuatro columnas, sin estados— más
   **`CtnCliente.codigo`**. Modelos, migración y pruebas.
   *(propuesto, esperando visto bueno — ver abajo)*
2. **El enrolamiento**: el endpoint que recibe el código, busca el contacto por
   identificación, compara los correos y crea el vínculo, con sus cuatro reglas y su límite de
   intentos (§4). Más el endpoint del ERP donde un administrador ve y **borra** los vínculos de
   su contenedor, y la variante OTP de la verificación de correo (§5), que hoy solo existe como
   enlace al Angular. El límite de intentos es solo el scope de throttle: no hay modelos nuevos.
3. **Los claims** —superficie, contenedor y vínculo— y la compuerta que los exige de un lado
   y los rechaza del otro, con pruebas que fijen las dos mitades y el caso de la persona con
   dos empleadores.
4. **`urls_portal`** con los dos endpoints de lectura: mis turnos y mis nóminas, los dos
   filtrados por el vínculo del token.
5. **Redis** para el límite de intentos, y el segundo proceso de despliegue.
6. **La app**: login **en dos pasos** —con MFA y dispositivo recordado, aunque el MFA sea
   opcional—, verificación de correo por OTP, enrolamiento por código, selector de empresa
   cuando hay más de una, y esos dos endpoints.

### El modelo del paso 1

```python
class SegUsuarioEmpleado(models.Model):
    usuario = models.ForeignKey('seguridad.SegUsuario', ...)
    cliente = models.ForeignKey('contenedor.CtnCliente', ...)
    # id del GenContacto dentro del schema del cliente. No puede ser FK:
    # la tabla vive en otro schema. Lo resuelve el enrolamiento y no cambia después.
    contacto_id = models.BigIntegerField()
    fecha_enrolamiento = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seg_usuario_empleado'
        unique_together = [['usuario', 'cliente']]
```

Y el campo nuevo en el registro de contenedores, que es lo que el empleado escribe para elegir
empresa:

```python
class CtnCliente(TenantBase):
    ...
    codigo = models.CharField(max_length=20, unique=True, null=True)
```

Sigue la forma de `SegUsuarioCliente` —mismo par usuario/cliente, mismo esquema de nombres—
porque es el modelo hermano: uno dice «esta persona usa el ERP de este contenedor», el otro
«esta persona trabaja en este contenedor».

Cambió dos veces respecto de la primera versión: se fue el estado `pendiente` —el
enrolamiento es inmediato— y después se fue el campo `estado` entero. La existencia de la fila
es el permiso, así que no hay nada más que guardar: cuatro columnas y la fecha.

Dos decisiones que van implícitas en esa forma:

- **`contacto_id` es un entero pelado, no un FK.** `GenContacto` vive en el schema del
  tenant y una llave foránea entre schemas no existe en PostgreSQL. La contrapartida es que
  nada garantiza en base que ese id exista: lo tiene que sostener el código que lo escribe.
- **`unique_together (usuario, cliente)`**: un vínculo por persona y contenedor. Una
  recontratación reusa la fila que ya existe en vez de crear otra, que es coherente con
  apuntar al contacto y no al contrato.


## 11. Fuera de alcance por ahora

La primera entrega es **autenticación y lectura**. Estas dos quedan explícitamente afuera, con
lo que ya se sabe de cada una para cuando se retomen:

**Certificados.** Certificado laboral, certificado de ingresos y retenciones, desprendible de
pago: cada uno con su formato legal y su firma, y falta definir si se generan al vuelo o
quedan archivados, y con qué motor de PDF. El laboral sería el primero: es el que más piden y
el que menos reglas tiene. Cuando entren, entra con ellos una restricción que ya está medida:
**los PDF los sirve el backend**, porque el bucket de B2 no tiene lectura pública pese a su
nombre; se descargan por un endpoint que valida el vínculo y transmite el archivo, sin atajo
por URL directa.

**Notificaciones push.** «Te asignaron turno el sábado» es la mitad del valor de una app de
turnos, pero trae registro de dispositivos, un proceso que envía y una dependencia de Firebase
o similar. Si se retoma, conviene guardar el token del dispositivo desde antes: pedirle
permiso de notificaciones a toda la base de empleados una segunda vez es caro.

---

Cifras verificadas sobre `main @ 3ba2422`: 118 clases `ViewSet`, 34 con
`permission_classes = [TienePermisoModelo]`, y los tiempos de sesión de
`torioapp/settings/base.py`. Lo demás es propuesta.