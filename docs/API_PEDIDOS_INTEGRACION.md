# Comprobantes y rechazos actualizados

`GET /api/v1/integracion/logistica/pedidos`

El endpoint usa **ventas_detalle**. Reemplaza el contrato preliminar que leía
`repartos_detalle`, cuya cobertura estaba desactualizada. La respuesta indica
`contrato: comprobantes_ventas_v2`; los consumidores del contrato preliminar
deben adaptar campos y significado de fechas y estados antes de actualizar.
Los otros endpoints de integración conservan sus contratos.

## Consulta

Enviar `X-API-Key: <INTEGRATION_API_KEY>` o `Authorization: Bearer <clave>`.

`/api/v1/integracion/logistica/pedidos?desde=2026-09-01&hasta=2026-09-17&empresa_id=1&sucursal=TODAS&limit=200&offset=0`

- `fecha=YYYY-MM-DD` o `desde` y `hasta`, máximo 31 días. Filtra **fecha de movimiento**.
- `empresa_id`: predeterminado `1`.
- `sucursal`: código o `TODAS` (predeterminado).
- `limit`: 1–1000, predeterminado 200; `offset`: desde 0.

Incluye líneas de artículos clasificados como `mercaderia`, excluye remitos y
comodatos por prefijo de documento/detalle. Mantiene los rechazos aunque el motivo
no esté configurado para computar en el dashboard. Empresa y sucursal vacías en
origen se interpretan como `1`, igual que en la integración diaria existente.

## Identidad

Una fila por **empresa + sucursal + cliente + fecha de movimiento + comprobante**.
La clave del comprobante incluye tipo, letra, serie y número. Si esos campos están
incompletos se usa `detalle_documento`; si también falta, se conserva cada línea
por separado y se señala la falta de identificación. No se agrupa solo por cliente/día.

- `id_integracion`: hash determinista de esa clave. No es un identificador de Foxtrot.
  Si la clave utiliza el ID de fila, puede cambiar al reimportar.
- `empresa_id`, `sucursal_id`, `cliente_id`, `cliente_nombre`.
- `numero_comprobante`, `comprobantes`: tipo, letra, serie, número y detalle de origen.
- `tipo_identificador`: `comprobante` o `fila`.
- `numero_pedido`: **null**. El número de comprobante no se presenta como número de pedido.

No se normalizan ceros iniciales de códigos ni se equiparan tipos como FACTURA y
FCVTA de manera automática. El consumidor debe definir esas equivalencias cuando
cruce sus datos. Un pedido puede corresponder a varios comprobantes.

## Fechas y vínculo con Foxtrot

- `fecha_movimiento`: `ventas_detalle.fecha`, disponible para cruce por día/cliente.
- `fecha_entrega`: **null**, porque esta fuente no confirma la fecha real de entrega.
- `fuente_fecha_movimiento` y `fuente_fecha_entrega` explicitan esa diferencia.
- `vinculo_foxtrot`: comprobantes y `rutas_venta` (códigos de `ventas_detalle.ruta`).
  Las listas `planillas` y `rutas_distribucion` están vacías porque no existen en esta fuente.
- `detalle`: artículo, cantidades, rechazos, marca de rechazo total, motivo, sector,
  código de ruta y descripción, chofer, transporte y clasificación del motivo.

La ruta comercial es una referencia de origen; no equivale a una ruta Foxtrot
confirmada. No se cruzan automáticamente las tablas antiguas por cliente/día.

## Estados y cantidades

`estado_rechazo` clasifica las líneas de mercadería del comprobante:

| Evidencia | Estado |
| --- | --- |
| Cantidades rechazadas conocidas y sin positivos | `sin_rechazo_registrado` |
| Todas las líneas tienen rechazo positivo y marca total afirmativa | `total` |
| Hay rechazos, marcas conocidas y cantidades completas, sin rechazo total de todas las líneas | `parcial` |
| Datos insuficientes, negativos o marca total sin cantidad positiva | `sin_determinar` |

Un rechazo positivo puede estar en bultos, HL o UP. Se reconocen marcas afirmativas
SI/SÍ/S/YES/Y/TRUE/1/X y negativas NO/N/FALSE/0. Las marcas desconocidas no se
interpretan como negativas cuando hay rechazos. Una marca total explícita en todas
las líneas con cantidades positivas permite clasificar total aun si otra unidad falta.

`estado_entrega` vale `rechazada` ante rechazo total, `parcial` ante rechazo parcial
y `sin_determinar` en los otros casos. `estado_entrega_inferido` distingue las dos
primeras situaciones. **Sin rechazo no confirma entrega completa**: no se devuelve
`completa` sin evidencia adicional de entrega. Tampoco se infiere `en_transito`.

`tiene_rechazo_registrado` indica cantidades rechazadas positivas, incluso si no
se puede clasificar total/parcial. `tiene_rechazo_computable` aplica además la
configuración `tomar=true` de los motivos; esa configuración no altera el estado físico.

`cantidades` suma bultos, HL, UP y sus rechazos dentro del comprobante. Una suma se
devuelve **null** si falta ese campo en alguna línea, para no ocultar faltantes.
Son cantidades de origen: no se infiere si la venta es neta o bruta del rechazo,
ni se calcula cantidad entregada restando rechazos. `calidad` señala identificación,
faltantes, negativos, inconsistencias y motivos de rechazo sin clasificar.

## Cobertura, paginación y uso para OTIF

`cobertura.ultima_fecha_disponible` corresponde a la última fecha de movimiento
dentro del alcance de empresa/sucursal/mercadería, aunque el rango consultado esté vacío.
No garantiza que cada día o cada entrega esté completamente cargada.

`paginacion` contiene `limit`, `offset`, `devueltos`, `total` y `hay_mas`.
Aumentar offset por devueltos hasta que hay_mas sea false, con las importaciones
estables durante la descarga. Se ordena por fecha, sucursal, cliente y comprobante.
El detalle de artículos se genera solo para los comprobantes de la página solicitada.

Para una app con día y cliente, comprobar que su fecha coincide con la fecha de
movimiento. Agrupar los comprobantes de ese cliente/día usando presencia de rechazo;
no contar cada artículo o motivo como un pedido. Si falta una fila, significa
**sin datos**, no éxito. Para OTIF completo todavía hacen falta evidencia de entrega
completa y cumplimiento de la fecha/hora comprometida.
