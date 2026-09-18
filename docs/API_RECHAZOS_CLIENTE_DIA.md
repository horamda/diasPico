# Rechazos para cruzar por día y cliente

`GET /api/v1/integracion/logistica/rechazos/clientes-diario`

Autenticación: `X-API-Key: <INTEGRATION_API_KEY>` o `Authorization: Bearer <clave>`.
Sin clave configurada responde 503; con credenciales inválidas, 401.

Ejemplo: `?desde=2026-09-01&hasta=2026-09-18&empresa_id=1&sucursal=TODAS&limit=200&offset=0`.
También acepta `fecha=2026-09-01` en lugar del rango. Máximo 31 días, límite 1–1000.
Recorrer páginas incrementando `offset` por `devueltos` mientras `hay_mas` sea true.

## Granularidad y campos

Una fila por **empresa + fecha + cliente_id**, incluso si tiene varios documentos,
artículos, motivos o sucursales. Incluye clientes con movimiento sin rechazo.
Los códigos de cliente se conservan como texto, sin quitar ceros iniciales.
La fecha es la del movimiento de ventas, no una fecha de entrega confirmada.

- `fecha`, `empresa_id`, `cliente_id`, `cliente_nombre`, `sucursales`.
- `tiene_rechazo`: alguna línea tiene cantidad rechazada positiva en bultos, HL o UP.
- `tiene_rechazo_computable`: alguna de esas líneas tiene motivo con `tomar=true`.
- `bultos_registrados`, `bultos_rechazados`, `bultos_rechazados_computables`.
- `hl_registrados`, `hl_rechazados`, `up_registradas`, `up_rechazadas`.
- `documentos`: comprobantes distintos con tipo, letra, serie, número, detalle y sucursal.
- `motivos`: motivos distintos con sector, `computable` y `clasificado`.
- `lineas_origen`: filas de origen, no cantidad de pedidos.
- `calidad`: cliente identificado, múltiples sucursales, cantidad de líneas de rechazo
  sin clasificar y cantidad de líneas con bultos de origen incompletos.

El alcance coincide con mercadería del dashboard: requiere artículo clasificado
como `mercaderia` y excluye documentos/remitos y comodatos según sus prefijos.
Los volúmenes son los valores de origen; no se infiere si los bultos registrados
son pedidos, despachados o entregados. Los valores nulos se suman como cero;
el indicador de bultos incompletos permite detectarlos.

## Cómo usarlo en la otra app

1. Seleccionar la misma empresa y, si corresponde, sucursal que en la app receptora.
2. Cruzar su fecha y código de cliente con `fecha` y `cliente_id`. Verificar primero
   que ambos sistemas usan la misma definición de fecha y el mismo código.
3. Contar cada cliente/día una sola vez. Para la política del dashboard usar
   `tiene_rechazo_computable`; para todos los rechazos registrados usar `tiene_rechazo`.
4. Revisar motivos sin clasificar; no confundirlos con una exclusión deliberada.
5. Si falta una fila, tratarla como **sin datos**, nunca como entrega exitosa.
   Filas con cliente vacío no se deben cruzar y requieren revisión.

Una proporción de clientes/día sin rechazo es un indicador de rechazo, no OTIF
completo. La app receptora debe aportar cumplimiento horario y evidencia de
entrega completa sobre la misma unidad. Si conoce solo fecha y cliente, no se
puede distinguir el cumplimiento de varios pedidos de ese cliente en ese día.
No sumar documentos o motivos como si fueran entregas independientes.

Los endpoints anteriores conservan su respuesta. Para cruces cliente/día usar
este endpoint; los resúmenes anteriores no contienen la clave de cliente.
