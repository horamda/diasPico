# Manual API de Rechazos

Este documento describe los endpoints para que otra aplicacion consuma los rechazos diarios del dashboard.

## Base URL

En produccion, usar la URL publica del dashboard:

```text
https://TU-DOMINIO/api/rechazos
```

Ejemplo Railway:

```text
https://control-asistencia.up.railway.app/api/rechazos
```

En local:

```text
http://localhost:5001/api/rechazos
```

## Autenticacion

Estos endpoints no agregan una autenticacion propia en el contrato actual. Si el despliegue queda detras de login, proxy, API Gateway o una regla de red, la app consumidora debe enviar las credenciales que ese entorno requiera.

## Parametros Comunes

Todos los endpoints diarios aceptan estos parametros por query string:

| Parametro | Requerido | Formato | Default | Descripcion |
| --- | --- | --- | --- | --- |
| `desde` | No | `YYYY-MM-DD` | 1 de enero del anio actual | Fecha inicial del rango. |
| `hasta` | No | `YYYY-MM-DD` | Fecha actual del servidor | Fecha final del rango. |
| `sucursal` | No | Texto | `TODAS` | Codigo de sucursal o `TODAS`. Ejemplo: `2`. |

Si `desde` es posterior a `hasta`, la API responde `400`.

## Criterio de Calculo

La API usa la misma logica del dashboard:

- Incluye solo articulos con `tipo_producto = mercaderia`.
- Excluye documentos de remito y comodato.
- Cuenta como rechazo solo los motivos marcados como `tomar = true` en la tabla de motivos de rechazo.
- Calcula pallets con `bultos_rechazados / bultos_por_pallet` cuando el articulo tiene `bultos_por_pallet`.
- Los porcentajes se calculan sobre el total despachado de cada unidad:
  - `% rechazo bultos = bultos_rechazo / bultos * 100`
  - `% rechazo HL = hl_rechazo / hl * 100`
  - `% rechazo pallets = pallets_rechazo / pallets * 100`
  - `% rechazo pedidos = pedidos_rechazo / pedidos * 100`

## Endpoint 1: Resumen Diario

Devuelve una fila por fecha y sucursal con totales diarios y porcentajes.

```http
GET /api/rechazos/diario/resumen?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&sucursal=TODAS
```

Ejemplo:

```http
GET https://TU-DOMINIO/api/rechazos/diario/resumen?desde=2026-01-01&hasta=2026-01-31&sucursal=2
```

Respuesta:

```json
{
  "desde": "2026-01-01",
  "hasta": "2026-01-31",
  "sucursal": "2",
  "total_filas": 1,
  "campos": [
    "fecha",
    "sucursal",
    "pedidos",
    "pedidos_rechazo",
    "pct_rechazo_pedidos",
    "bultos",
    "bultos_rechazo",
    "pct_rechazo_bultos",
    "hl",
    "hl_rechazo",
    "pct_rechazo_hl",
    "pallets",
    "pallets_rechazo",
    "pct_rechazo_pallets"
  ],
  "datos": [
    {
      "fecha": "2026-01-02",
      "sucursal": "2",
      "pedidos": 120,
      "pedidos_rechazo": 8,
      "pct_rechazo_pedidos": 6.67,
      "bultos": 3500.0,
      "bultos_rechazo": 140.0,
      "pct_rechazo_bultos": 4.0,
      "hl": 420.5,
      "hl_rechazo": 18.2,
      "pct_rechazo_hl": 4.33,
      "pallets": 32.4,
      "pallets_rechazo": 1.3,
      "pct_rechazo_pallets": 4.01
    }
  ]
}
```

### Campos del Resumen

| Campo | Tipo | Descripcion |
| --- | --- | --- |
| `fecha` | string | Fecha del dia en formato `YYYY-MM-DD`. |
| `sucursal` | string | Codigo de sucursal. |
| `pedidos` | integer | Pedidos/PDV atendidos del dia. |
| `pedidos_rechazo` | integer | Pedidos con rechazo del dia. |
| `pct_rechazo_pedidos` | number | Porcentaje de pedidos con rechazo. |
| `bultos` | number | Bultos totales despachados. |
| `bultos_rechazo` | number | Bultos rechazados. |
| `pct_rechazo_bultos` | number | Porcentaje de bultos rechazados. |
| `hl` | number | Hectolitros totales despachados. |
| `hl_rechazo` | number | Hectolitros rechazados. |
| `pct_rechazo_hl` | number | Porcentaje de HL rechazados. |
| `pallets` | number | Pallets totales calculados. |
| `pallets_rechazo` | number | Pallets rechazados calculados. |
| `pct_rechazo_pallets` | number | Porcentaje de pallets rechazados. |

## Endpoint 2: Detalle Diario por Chofer y Motivo

Devuelve una fila por fecha, sucursal, chofer, sector y motivo.

```http
GET /api/rechazos/diario/detalle?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&sucursal=TODAS
```

Ejemplo:

```http
GET https://TU-DOMINIO/api/rechazos/diario/detalle?desde=2026-01-01&hasta=2026-01-31&sucursal=2
```

Respuesta:

```json
{
  "desde": "2026-01-01",
  "hasta": "2026-01-31",
  "sucursal": "2",
  "total_filas": 1,
  "campos": [
    "fecha",
    "sucursal",
    "chofer",
    "chofer_codigo",
    "sector",
    "motivo",
    "pedidos_rechazo",
    "ocurrencias",
    "bultos_rechazo",
    "hl_rechazo",
    "pallets_rechazo"
  ],
  "datos": [
    {
      "fecha": "2026-01-02",
      "sucursal": "2",
      "chofer": "Juan Perez",
      "chofer_codigo": "123",
      "sector": "Entrega",
      "motivo": "Cliente cerrado",
      "pedidos_rechazo": 2,
      "ocurrencias": 4,
      "bultos_rechazo": 35.0,
      "hl_rechazo": 4.8,
      "pallets_rechazo": 0.4
    }
  ]
}
```

### Campos del Detalle

| Campo | Tipo | Descripcion |
| --- | --- | --- |
| `fecha` | string | Fecha del rechazo en formato `YYYY-MM-DD`. |
| `sucursal` | string | Codigo de sucursal. |
| `chofer` | string | Nombre del chofer. Si no existe, devuelve `Sin chofer`. |
| `chofer_codigo` | string | Codigo del chofer, si esta disponible. |
| `sector` | string | Sector asociado al motivo de rechazo. |
| `motivo` | string | Motivo de rechazo. |
| `pedidos_rechazo` | integer | Cantidad de pedidos con rechazo para ese chofer/motivo/dia. |
| `ocurrencias` | integer | Cantidad de lineas de detalle con rechazo. |
| `bultos_rechazo` | number | Bultos rechazados. |
| `hl_rechazo` | number | Hectolitros rechazados. |
| `pallets_rechazo` | number | Pallets rechazados calculados. |

## Endpoint 3: Integracion Completa

Devuelve en una sola respuesta el resumen diario y el detalle diario.

```http
GET /api/rechazos/diario/integracion?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&sucursal=TODAS
```

Ejemplo:

```http
GET https://TU-DOMINIO/api/rechazos/diario/integracion?desde=2026-01-01&hasta=2026-01-31&sucursal=2
```

Respuesta:

```json
{
  "desde": "2026-01-01",
  "hasta": "2026-01-31",
  "sucursal": "2",
  "resumen_diario": [
    {
      "fecha": "2026-01-02",
      "sucursal": "2",
      "pedidos": 120,
      "pedidos_rechazo": 8,
      "pct_rechazo_pedidos": 6.67,
      "bultos": 3500.0,
      "bultos_rechazo": 140.0,
      "pct_rechazo_bultos": 4.0,
      "hl": 420.5,
      "hl_rechazo": 18.2,
      "pct_rechazo_hl": 4.33,
      "pallets": 32.4,
      "pallets_rechazo": 1.3,
      "pct_rechazo_pallets": 4.01
    }
  ],
  "detalle_diario": [
    {
      "fecha": "2026-01-02",
      "sucursal": "2",
      "chofer": "Juan Perez",
      "chofer_codigo": "123",
      "sector": "Entrega",
      "motivo": "Cliente cerrado",
      "pedidos_rechazo": 2,
      "ocurrencias": 4,
      "bultos_rechazo": 35.0,
      "hl_rechazo": 4.8,
      "pallets_rechazo": 0.4
    }
  ]
}
```

## Codigos de Estado

| Codigo | Significado |
| --- | --- |
| `200` | Consulta correcta. |
| `400` | Parametros invalidos, por ejemplo fecha con formato incorrecto o `desde` posterior a `hasta`. |
| `500` | Error interno del servidor o problema de base de datos. |

Respuesta de error:

```json
{
  "error": "desde no puede ser posterior a hasta"
}
```

## Ejemplo de Consumo en JavaScript

```js
const baseUrl = "https://TU-DOMINIO/api/rechazos";

const params = new URLSearchParams({
  desde: "2026-01-01",
  hasta: "2026-01-31",
  sucursal: "2",
});

const response = await fetch(`${baseUrl}/diario/integracion?${params}`);

if (!response.ok) {
  const error = await response.json().catch(() => ({}));
  throw new Error(error.error || `Error HTTP ${response.status}`);
}

const data = await response.json();

console.log(data.resumen_diario);
console.log(data.detalle_diario);
```

## Ejemplo de Consumo con curl

```bash
curl "https://TU-DOMINIO/api/rechazos/diario/integracion?desde=2026-01-01&hasta=2026-01-31&sucursal=2"
```

## Recomendacion de Uso

Para una integracion simple, consumir:

```text
GET /api/rechazos/diario/integracion
```

Para procesos separados o pantallas independientes:

```text
GET /api/rechazos/diario/resumen
GET /api/rechazos/diario/detalle
```

