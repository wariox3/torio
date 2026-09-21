# Webhook de rededoc hacia torio

Estado: **implementado del lado de torio**: vista `contenedor/views/rededoc.py`, firma en
`general/servicios/rededoc.py` (`firmar_aviso`, `firma_valida`), aplicación del aviso en
`general/servicios/factura_electronica.py` (`procesar_aviso`), con tests en
`contenedor/tests_rededoc.py`. **Del lado de nobelio falta el envío**: hoy el modelo
`Webhook` solo guarda la URL y las banderas.

Este documento es el contrato: lo que nobelio tiene que mandar y cómo tiene que leer la
respuesta. Lo que no esté acá no forma parte del contrato.

## 1. Para qué

Torio crea los documentos en rededoc (`POST /api/documentos/documento/`) y guarda el id
que devuelve en `GenDocumento.electronico_id`. Lo que pasa después —que la DIAN lo valide,
que se le entregue al adquiriente— solo lo sabe rededoc. El webhook es cómo se lo cuenta a
torio.

## 2. La petición

```
POST https://<host de torio>/contenedor/rededoc/webhook/
Content-Type: application/json
X-Rededoc-Fecha: <timestamp unix, en segundos>
X-Rededoc-Firma: v1=<firma>
```

- **Sin `X-Tenant`.** El endpoint vive en el schema público. El tenant va en el cuerpo
  (`cliente`), y el middleware de torio respondería 404 a un `X-Tenant` que no reconoce.
- **Sin autenticación de usuario.** Lo que prueba que el aviso viene de rededoc es la
  firma (sección 4), no una sesión ni la API key.

### Cuerpo

| Campo | Tipo | Obligatorio | Qué es |
|---|---|---|---|
| `tipo` | texto | siempre | `validacion` o `notificacion` |
| `cliente` | entero | siempre | Id del cliente (tenant) en torio |
| `documento` | UUID | siempre | Id del documento en rededoc: el mismo que devolvió al crearlo |
| `fecha_validacion` | fecha y hora ISO 8601 | en `validacion` | Cuándo lo validó la DIAN. Con hora: `2026-09-21` solo se rechaza |
| `cufe` | texto, hasta 150 | en `validacion` | CUFE/CUDE del documento |

- **`validacion`**: la DIAN aceptó el documento. Torio lo marca validado y guarda el CUFE
  y la fecha.
- **`notificacion`**: el documento se le entregó al adquiriente. Torio lo marca
  notificado. `fecha_validacion` y `cufe` no se usan.

Incluya la zona horaria en `fecha_validacion` (`2026-09-21T10:15:00-05:00`). Sin ella,
torio la interpreta como hora de Bogotá.

Ejemplo:

```json
{"tipo": "validacion", "cliente": 12, "documento": "0b8f3c2e-5d7a-4e1b-9c6f-2a4d8e7b1f90", "fecha_validacion": "2026-09-21T10:15:00-05:00", "cufe": "abc123"}
```

## 3. La respuesta

Todo error trae `detail` con el mensaje. Un 200 no trae cuerpo.

| Código | Cuándo | ¿Reintentar? |
|---|---|---|
| `200` | Aviso aplicado. También una `notificacion` repetida | No: listo |
| `400` | Cuerpo inválido (campo que falta, `tipo` desconocido, fecha sin hora…). Trae el error por campo además de `detail` | No: el mismo cuerpo volverá a fallar |
| `401` | Firma inválida o fecha fuera de la ventana (sección 4) | Sí, **firmando de nuevo** con la hora actual. Si persiste, es el secreto o el reloj |
| `404` | El cliente no existe, o el documento no está en ese cliente. Es la misma respuesta en los dos casos, a propósito | No |
| `409` | `validacion` de un documento que ya estaba validado. Torio **no** lo reescribe | No: es definitivo |
| `429` | Límite de peticiones de torio | Sí, con espera |
| `5xx`, timeout, sin conexión | Falla de torio o de la red | Sí, con espera |

Sobre el `409`: si torio aplicó una validación pero su `200` se perdió en la red, el
reintento recibe `409`. Tómelo como entregado. Un `409` con un CUFE **distinto** del que
torio tiene es una inconsistencia que hay que revisar a mano; torio conserva el primero.

### Reintentos

Reintente con espera creciente (por ejemplo 1 min, 5 min, 30 min, 2 h, 12 h) y
márquelo como fallido al agotar los intentos. **Cada reintento se firma de nuevo** con su
propia `X-Rededoc-Fecha`: reenviar los headers del primer intento da `401` pasados cinco
minutos.

## 4. La firma

Rededoc y torio comparten un secreto. Del lado de torio es `REDEDOC_WEBHOOK_SECRETO`, y es
**distinto de `REDEDOC_KEY`**: esa autentica a torio ante rededoc; este, a rededoc ante
torio.

```
fecha   = timestamp unix actual, en segundos, como texto   → "1790000000"
mensaje = fecha + "." + cuerpo                              → bytes
firma   = "v1=" + hex(HMAC-SHA256(secreto, mensaje))
```

- **`cuerpo` son los bytes exactos que van en la petición.** Serialice el JSON una sola
  vez, firme esos bytes y mande esos mismos bytes. Firmar un dict y dejar que la librería
  HTTP lo vuelva a serializar produce otro orden de claves u otros espacios, y la firma no
  cuadra.
- **La fecha entra en lo firmado.** Torio rechaza una `X-Rededoc-Fecha` que se aleje más de
  **5 minutos** de su hora, en cualquier dirección. Así un aviso capturado no se puede
  reenviar después. Mantenga el reloj sincronizado (NTP).
- Hex en minúsculas, como lo da `hexdigest()`.

En Python:

```python
import hashlib, hmac, json, time
import httpx

cuerpo = json.dumps(aviso).encode()
fecha = str(int(time.time()))
firma = 'v1=' + hmac.new(secreto.encode(), fecha.encode() + b'.' + cuerpo, hashlib.sha256).hexdigest()

httpx.post(url, content=cuerpo, headers={
    'Content-Type': 'application/json',
    'X-Rededoc-Fecha': fecha,
    'X-Rededoc-Firma': firma,
}, timeout=10)
```

Nótese `content=cuerpo` y no `json=aviso`: es lo que garantiza que viajen los bytes
firmados.

### Vector de prueba

Para comprobar la implementación de nobelio sin torio de por medio:

- secreto: `secreto-de-ejemplo`
- `X-Rededoc-Fecha`: `1790000000`
- cuerpo (una sola línea, exactamente así):
  ```
  {"tipo": "validacion", "cliente": 12, "documento": "0b8f3c2e-5d7a-4e1b-9c6f-2a4d8e7b1f90", "fecha_validacion": "2026-09-21T10:15:00-05:00", "cufe": "abc123"}
  ```
- `X-Rededoc-Firma` esperada:
  ```
  v1=2baa83d05c60f6d0843109233e07935bfe0225aaa776c1c59dfcc6e1e2c0ba5e
  ```

### Rotar el secreto

Torio acepta dos secretos a la vez: `REDEDOC_WEBHOOK_SECRETO` y
`REDEDOC_WEBHOOK_SECRETO_ANTERIOR`.

1. En torio: el secreto actual pasa a `REDEDOC_WEBHOOK_SECRETO_ANTERIOR` y el nuevo va en
   `REDEDOC_WEBHOOK_SECRETO`. Desde ahí acepta los dos.
2. En nobelio: empezar a firmar con el nuevo.
3. Cuando ya no queden avisos pendientes firmados con el anterior (pasado el último
   reintento), vaciar `REDEDOC_WEBHOOK_SECRETO_ANTERIOR`.

Si torio no tiene ningún secreto configurado **rechaza todos los avisos** con `401`: es
preferible a aceptarlos sin verificar.

## 5. De dónde sale el `cliente`

Rededoc no conoce los tenants de torio: torio tiene que decírselo. Esto **todavía no está
decidido**. Las dos opciones que se discutieron:

- Guardarlo en el emisor al crearlo (un campo genérico como `referencia_externa`, no
  `tenant_id`, para que sirva a cualquier ERP), y que rededoc lo copie en cada aviso.
- Que torio registre el `Webhook` del emisor al crearlo, con el cliente en la URL.

La segunda cambiaría la URL de la sección 2, y el `cliente` dejaría de ir en el cuerpo.

## 6. Qué no hace el webhook

- No crea ni corrige documentos: solo marca los que torio ya había creado en rededoc.
- No revierte una validación: un documento validado no vuelve a pendiente por un aviso.
- No informa rechazos de la DIAN. Si se necesitan, es un `tipo` nuevo y hay que acordarlo
  acá antes de mandarlo: hoy torio responde `400` a cualquier `tipo` que no conozca.
