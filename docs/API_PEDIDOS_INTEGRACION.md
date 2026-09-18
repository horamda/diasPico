# Integración por pedido o comprobante

`GET /api/v1/integracion/logistica/pedidos`

Enviar `X-API-Key: <INTEGRATION_API_KEY>` o `Authorization: Bearer <clave>`.
Acepta `fecha=YYYY-MM-DD` o `desde=YYYY-MM-DD&hasta=YYYY-MM-DD` (máximo 31 días),
`sucursal=TODAS` o código de sucursal, `limit` (1–1000, predeterminado 200) y `offset`.
No acepta `empresa_id`: `repartos_detalle` no identifica empresa y no es posible
garantizar ese filtro. Para instalaciones con varias empresas, este contrato
requiere incorporar empresa en la fuente antes de usarlo como separación entre ellas.

Ejemplo: `/api/v1/integracion/logistica/pedidos?desde=2026-05-01&hasta=2026-05-19&sucursal=2`.

## Unidad de la respuesta

Una fila por **número de pedido + cliente + sucursal + fecha de entrega de planilla**.
Si falta número de pedido, usa el comprobante. Si ambos faltan, cada línea se
conserva por separado con una alerta; nunca se fusionan todos los desconocidos.
Dos pedidos de un mismo cliente/día permanecen separados. Un pedido registrado
en dos días también permanece separado, para no mezclar intentos de entrega.
Varias planillas del mismo pedido/cliente/sucursal/día se conservan en la lista
`planillas` y en el detalle; `multiples_planillas` advierte de esa ambigüedad.

Campos de cada fila:

- `id_integracion`: hash determinista de la clave anterior. No es el ID de Foxtrot.
  Si no hay pedido ni comprobante, depende del ID de fila y puede cambiar al reimportar.
- `numero_pedido`, `comprobantes`, `tipo_identificador` (`pedido`, `comprobante`, `fila`).
- `cliente_id`, `cliente_nombre`, `sucursal_id`, `fecha_entrega`.
- `vinculo_foxtrot`: número de pedido, comprobantes, planillas, rutas de venta y
  distribución tal como están en la fuente; permite que el consumidor los cruce.
  No se afirma que una ruta comercial sea el identificador de ruta externo.
- `estado_entrega`, `estados_origen`, `fuente_estado`, `fuente_fecha_entrega`.
- `detalle`: líneas con artículo, estado, cantidades de origen, motivo de rechazo,
  hora de entrega registrada, comprobante, planilla y rutas.
- `calidad`: identificación de cliente/sucursal/pedido, múltiples planillas y estado conocido.

## Estados

| Estados de todas las líneas | `estado_entrega` |
| --- | --- |
| Todas `ENTREGADO` | `completa` |
| Todas `RECHAZADO` | `rechazada` |
| Mezcla `ENTREGADO` / `RECHAZADO`, o estado explícito `PARCIAL` | `parcial` |
| Alguna `EN TRANSITO`, sin estados desconocidos | `en_transito` |
| Alguna vacía o desconocida | `sin_determinar` |

Se normalizan mayúsculas, espacios y tildes. La clasificación expresa el estado
registrado en repartos; `completa` no compara cantidades contra un pedido original.
No se usa `tipo_entrega` (F/S/N) para inferir cumplimiento, ni la configuración
`tomar` de rechazos: un rechazo físico sigue siendo rechazo aunque esté excluido
de un KPI. La fecha proviene de `fecha_entrega_planilla`, no de ventas, y no prueba
por sí sola entrega efectiva. Una fila en tránsito conserva esa fecha de planilla.

Para OTIF, el consumidor debe validar estos estados y fechas contra la evidencia
de entrega y el compromiso horario. No interpretar un rango vacío como cumplimiento.

## Cobertura y paginación

`cobertura.ultima_fecha_disponible` muestra la última fecha cargada para la sucursal
seleccionada, aun si el rango solicitado no contiene datos. Es una fecha de registros,
no una garantía de que todas las entregas hasta ese día estén cargadas.

`paginacion` contiene `limit`, `offset`, `devueltos`, `total` y `hay_mas`.
El orden es fecha/sucursal/cliente/referencia. Aumentar offset por devueltos hasta
que hay_mas sea false. Consumir con importaciones estables para evitar cambios entre páginas.
La respuesta incluye también `api_version`, `generado_en`, `filtros`, `criterios` y `datos`.

Los endpoints diarios anteriores conservan sus respuestas. Este endpoint utiliza
la fuente `repartos_detalle`, que puede tener una cobertura temporal distinta de ventas.

Autenticacion: se acepta `LOGISTICS_INTEGRATION_API_KEY` y tambien `INTEGRATION_API_KEY` para conservar clientes existentes. Configurar la misma clave logistica en productor y consumidor. Las variables requieren reiniciar/desplegar el servicio.
