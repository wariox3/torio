# Pendientes por módulo

Estado: **implementado** con un detector (periodo anterior abierto). Modelos
`contenedor/models/pendiente_tipo.py` y `pendiente.py` (migraciones `contenedor/0055` y
siguientes), catálogo `contenedor/catalogos/11_pendiente_tipo.json`, comando
`contenedor/management/commands/analizar_pendientes.py`, detectores en
`<app>/servicios/pendiente.py` y endpoint `contenedor/views/pendiente.py`.

## 1. Por qué

Al iniciar sesión el usuario tiene que ver qué tiene pendiente en cada uno de sus
contenedores (periodos sin cerrar, documentos sin contabilizar…) sin entrar a cada uno.
Calcularlo en el momento obligaría a entrar a todos sus schemas en el login. En cambio, un
proceso nocturno lo calcula y deja el resultado en el público, donde se lee con una sola
consulta.

## 2. Modelos (schema público)

**`CtnPendienteTipo`** (`ctn_pendiente_tipo`), catálogo con id fijo:

| Campo | |
|---|---|
| `id` | Numérico, definido en el catálogo |
| `nombre` | 200 caracteres |
| `grupo` | FK a `auth.Group` (PROTECT): de qué módulo es, y quién lo ve |

**`CtnPendiente`** (`ctn_pendiente`), lo que el último análisis encontró:

| Campo | |
|---|---|
| `id` | Autonumérico |
| `fecha` | Fecha y hora de creación del registro (la del análisis) |
| `mensaje` | 200 caracteres, solo con la cantidad: «Hay 3 periodos anteriores abiertos» |
| `cantidad` | Entero |
| `cliente` | FK a `CtnCliente` (CASCADE) |
| `pendiente_tipo` | FK a `CtnPendienteTipo` (PROTECT) |

No hay restricción única por contenedor y tipo: cada corrida borra y vuelve a crear los
pendientes del contenedor.

### Catálogo

| id | nombre | grupo |
|---|---|---|
| 1 | Periodo anterior abierto | 7 Contabilidad |

`cargar_geodata` sincroniza los grupos **antes** de cargar los catálogos, porque este
apunta a ellos por FK y el cargador guarda fila por fila.

## 3. El proceso: `analizar_pendientes`

```bash
python manage.py analizar_pendientes                 # todos
python manage.py analizar_pendientes --schema demo   # uno
```

- Recorre los contenedores `listo` con suscripción vigente
  (`suscripcion.fecha_fin >= hoy`, el mismo criterio que `SuscripcionVigente`). Uno en
  `creando` o `error` puede no tener tablas, y a uno vencido no se le analiza.
- Siempre calcula con la fecha de hoy.
- Por contenedor:
  1. Entra a su schema y corre todos los detectores.
  2. Fuera del schema, en **una transacción**, borra sus `CtnPendiente` y crea los
     encontrados (solo los de cantidad mayor que 0). El usuario nunca ve el contenedor sin
     pendientes a mitad del reemplazo.
- Si un detector falla, ese contenedor **conserva los pendientes de la corrida anterior**:
  el error queda en el log y el comando sigue con el siguiente. Al final imprime cuántos
  analizó, cuántos pendientes creó y cuáles fallaron.

Hoy se corre a mano. Falta programarlo una vez al día (cron o timer de systemd) y
documentarlo en `DESPLIEGUE.md`.

## 4. Detectores

El registro `DETECTORES` está dentro del comando: id de `CtnPendienteTipo` → función. Cada
función vive en `<app>/servicios/pendiente.py`, recibe `hoy`, corre dentro del schema del
contenedor y devuelve `(cantidad, mensaje)` o `None`.

### 1. Periodo anterior abierto (`contabilidad/servicios/pendiente.py`)

Cuenta los `ConPeriodo` con `estado_cerrado = False` y `id` menor que el del mes actual.
Como el id es `anio*100+mes`:

- El periodo 13 (ajustes y cierre) del año en curso (`202613`) no cuenta: se cierra al año
  siguiente.
- El 13 del año anterior sí cuenta, si sigue abierto.
- Los periodos solo existen si el contenedor los creó con `anio-nuevo`, así que a quien no
  lleva contabilidad no le aparece.

### Agregar un pendiente nuevo

1. Una fila en `contenedor/catalogos/11_pendiente_tipo.json`, con su `grupo_id`.
2. La función en `<app>/servicios/pendiente.py`.
3. Su entrada en `DETECTORES`.

### Propuestos, sin implementar

- **Documentos sin contabilizar:** el criterio de `tablero.pendiente_contabilizar`, solo
  en contenedores que ya contabilizaron algo (la mayoría factura sin llevar contabilidad
  en torio y tendría miles de documentos de ruido) y solo de meses anteriores.
- **Contratos sin prórroga:** por definir.

## 5. Endpoint: `GET /contenedor/pendiente/`

En el público, sin `X-Tenant`, con sesión. Sin paginar.

- Sin parámetros, devuelve los pendientes de **todos** los contenedores del usuario; con
  `?cliente=<id>`, los de uno. Uno ajeno devuelve `[]`, igual que uno sin pendientes. Si
  `cliente` no es un número, 400.
- Un pendiente se ve si la membresía del usuario **en ese contenedor** es superusuario o
  tiene el grupo del tipo (herede o no permisos: ver `docs/permisos.md`).
- No muestra pendientes de contenedores con la suscripción vencida: el análisis no los
  recorre, así que lo guardado quedó de la última corrida.
- Ordenado por nombre del contenedor y tipo.

```json
[
  {
    "id": 12, "fecha": "2026-11-03T02:00:00-05:00",
    "mensaje": "Hay 10 periodos anteriores abiertos", "cantidad": 10,
    "cliente_id": 4, "cliente_nombre": "Inteliseg SAS",
    "pendiente_tipo_id": 1, "pendiente_tipo_nombre": "Periodo anterior abierto",
    "pendiente_tipo_grupo_id": 7, "pendiente_tipo_grupo_name": "Contabilidad"
  }
]
```
