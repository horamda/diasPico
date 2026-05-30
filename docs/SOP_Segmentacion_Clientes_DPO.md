# SOP Segmentacion de Clientes DPO

## 1. Alcance

Este SOP define como se ejecuta la segmentacion logistica-comercial de clientes DPO en el sistema actual, con foco operativo y trazabilidad. Cubre:

- calculo de metricas comerciales y logisticas por cliente
- filtro operativo de clientes activos
- clasificacion DPO en 4 clusters oficiales
- score 0-100 parametrizable
- subclasificacion operativa con autoelevador
- georreferenciacion para mapa
- guardado historico mensual y auditoria

No cubre cambios de modelo fuera del esquema actual ni rediseno funcional de modulos externos.

## 2. Fuentes de datos y objetos base

### 2.1 Fuentes transaccionales

- `ventas_detalle`: ventas, volumen, rutas, rechazos y fechas.
- `articulos`: enriquecimiento de tipo de producto y conversion a pallets.
- `rechazos`: normalizacion de motivos para marcar rechazo valido.
- `clientes`: estado de cliente (`anulado`), localidad y sucursal.

### 2.2 Tablas de configuracion y gobierno

- `seg_parametros`: costos por HL, percentiles, anios base/YTD.
- `seg_periodos_calculo`: rango de periodo YTD y base.
- `seg_score_pesos`: pesos por variable del score.
- `seg_clientes_atributos`: atributos de cliente (NPS, RMD, autoelevador, etc.).
- `cliente_autoelevador`: fuente externa/importada de autoelevador.
- `cliente_geografia`: latitud/longitud por cliente.

### 2.3 Tablas de salida historica

- `seg_cliente_cluster_historico`: snapshot por cliente y periodo.
- `seg_auditoria`: log de ejecuciones del recalculo.

## 3. Filtro de clientes activos (obligatorio para DPO)

El modelo DPO opera solo sobre `vw_clientes_activos_dpo`.

Reglas de exclusion:

1. Cliente inactivo:
   - `clientes.anulado` equivalente a SI/TRUE.
   - o cliente sin venta YTD y con venta en base comparable.
2. Estado anulado:
   - solo `estado_anulado = 'No'`.
3. Ruta temporal:
   - excluir cuando `ruta_venta_descripcion ILIKE '%temp%'`.
   - aplica a `temp`, `Temp`, `TEMP` y combinaciones.

Campos operativos de la vista:

- `cliente_id`, `cliente_nombre`, `sucursal`, `localidad`
- `ruta_venta`
- `estado_cliente`, `estado_anulado`, `activo`

## 4. Metricas calculadas por cliente

La vista base es `vw_cliente_metricas`. Calcula, entre otros:

- `venta_anio_base`
- `venta_ytd`
- `venta_base_mismo_per` (base del mismo rango temporal)
- `crecimiento_pct`
- `hl_ytd`, `bultos_ytd`, `pallets_ytd`, `up_ytd`
- `pedidos_ytd`
- `dropsize_bultos_ytd`
- `ticket_promedio_ytd`
- `rechazos_ytd`, `pct_rechazo_pedidos`
- `nps_valor`, `rmd_valor`
- `costo_entrega`, `costo_almacen`
- `costo_logistico_total`
- `margen_logistico_proxy`
- `ratio_costo_logistico_pct`

Definiciones clave:

- `dropsize_bultos_ytd = bultos_ytd / pedidos_ytd`
- `ticket_promedio_ytd = venta_ytd / pedidos_ytd`
- `costo_entrega = hl_ytd * costo_entrega_hl`
- `costo_almacen = hl_ytd * costo_almacen_hl`
- `ratio_costo_logistico_pct = (costo_logistico_total / venta_ytd) * 100`

## 5. Clusters DPO oficiales (4)

Vista: `vw_cliente_cluster_dpo`.

Se usa matriz ingreso vs crecimiento con umbrales dinamicos:

- venta alta: percentil configurado (default 0.70)
- venta baja: percentil configurado (default 0.30)
- crecimiento: umbral parametrico o mediana

Reglas:

- `Ganador`: venta alta y crecimiento alto.
- `En crecimiento`: crecimiento alto sin cumplir Ganador.
- `Basico`: venta media/alta con crecimiento bajo.
- `Ventas bajas`: resto de clientes.

Nota: el cluster se calcula solo para clientes de `vw_clientes_activos_dpo`.

## 6. Score 0-100 y subclasificacion operativa

### 6.1 Score base

Vista: `vw_cliente_score`. Normaliza variables por min-max y aplica pesos desde `seg_score_pesos`.

Distribucion objetivo:

- Negocio: 35 puntos (venta, HL, crecimiento)
- Productividad: 20 puntos (drop size, pallets/pedido, autoelevador)
- Servicio: 20 puntos (rechazos, RMD, NPS)
- Rentabilidad: 15 puntos (ratio costo, margen)
- Geo/frecuencia: 10 puntos (pedidos, localidad, sucursal)

Direccion de mejora:

- Menor es mejor: rechazos, ratio de costo.
- Mayor es mejor: venta, HL, crecimiento, drop size, NPS, RMD.

### 6.2 Autoelevador y costo diferencial

Vistas:

- `vw_cliente_autoelevador`
- `vw_cliente_costo_operativo`
- `vw_cliente_eficiencia_operativa`

Reglas operativas:

- con autoelevador: `factor_operativo = 1`
- sin autoelevador: `factor_operativo = 3`

Formulas:

- `costo_servir_ajustado = costo_entrega * factor_operativo`
- `costo_logistico_ajustado_total = costo_servir_ajustado + costo_almacen`
- `margen_logistico_ajustado = venta - costo_logistico_ajustado_total`
- `ratio_costo_logistico_ajustado_pct = costo_logistico_ajustado_total / venta * 100`
- `indice_eficiencia_operativa = HL / (pedidos * factor_operativo)`

Score operativo:

- `score_total_operativo = min(100, score_total_base + bonus_autoelevador)`
- bonus autoelevador actual: `+15`.

### 6.3 Subclasificacion logistica extendida

Vista: `vw_cliente_cluster_logistico`.

Etiquetas:

- `GANADOR EFICIENTE`
- `GANADOR AUTOELEVADOR`
- `ALTO VALOR CARO DE SERVIR`
- `ALTO VOLUMEN BAJA COMPLEJIDAD`
- `ALTO COSTO OPERATIVO`

Si no aplica ninguna regla extendida, se conserva subcluster logistico base.

## 7. Georreferenciacion y mapa

Tabla: `cliente_geografia(cliente_id, latitud, longitud, localidad, sucursal, updated_at)`.

Vista: `vw_clientes_mapa`.

Campos de salida:

- `cliente_id`, `cliente_nombre`
- `latitud`, `longitud`
- `hl`, `venta`, `pallets`, `bultos`
- `cluster_dpo`, `tiene_autoelevador`
- `sucursal`, `localidad`
- `ratio_costo_logistico_pct`, `costo_logistico_total`, `margen_logistico_proxy`

Pesos de visualizacion soportados por API:

- `hl` (default)
- `pallets`
- `venta`
- `bultos`

## 8. Vistas y salidas para consumo

### 8.1 Vistas principales

- `vw_cliente_metricas`
- `vw_clientes_activos_dpo`
- `vw_cliente_cluster_dpo`
- `vw_cliente_score`
- `vw_cliente_plan_servicio`
- `resumen_cluster_sucursal`
- `resumen_cluster_localidad`

### 8.2 Vistas operativas adicionales

- `vw_cliente_autoelevador`
- `vw_cliente_costo_operativo`
- `vw_cliente_eficiencia_operativa`
- `vw_cliente_cluster_logistico`
- `vw_clientes_mapa`

### 8.3 Cache para panel

- `mv_cliente_plan_servicio` (materialized view)

## 9. Recalculo mensual, historico y auditoria

### 9.1 Recalculo

Endpoint:

- `POST /api/segmentacion/recalcular`

Body minimo:

```json
{
  "periodo_anio": 2026,
  "periodo_mes": 5,
  "ejecutado_por": "admin"
}
```

Resultado:

- refresca cache de segmentacion
- recalcula cluster/score sobre periodo activo
- guarda snapshot por cliente en historico
- registra auditoria de ejecucion

### 9.2 Historico

Tabla: `seg_cliente_cluster_historico`.

Llave de unicidad:

- `(cliente, periodo_anio, periodo_mes)`

Permite analizar migracion de cluster por mes y por sucursal.

### 9.3 Auditoria

Tabla: `seg_auditoria`.

Registra:

- accion ejecutada
- periodo
- volumen de clientes procesados
- distribucion por cluster
- version de regla
- parametros usados
- usuario/proceso ejecutor
- duracion y error (si aplica)

## 10. Controles de calidad (QC)

Ejecutar en cada recalculo:

1. Integridad de datos:
   - clientes sin `cliente_id` nulo.
   - ventas/HL no negativas.
2. Cobertura de filtros:
   - validacion de exclusion por `ruta_venta_descripcion ILIKE '%temp%'`.
   - validacion de exclusiones por `anulado`/inactividad.
3. Umbrales dinamicos:
   - verificar `percentil_alta > percentil_baja`.
4. Score:
   - `0 <= score_total <= 100`.
   - `0 <= score_total_operativo <= 100`.
5. Geografia:
   - latitud en `[-90, 90]`.
   - longitud en `[-180, 180]`.
6. Trazabilidad:
   - fila de auditoria creada por corrida.
   - snapshot historico con periodo correcto.

## 11. Procedimiento operativo paso a paso

1. Confirmar periodo activo:
   - consultar `GET /api/segmentacion/periodo`.
   - si corresponde, actualizar con `PUT /api/segmentacion/periodo`.
2. Cargar o actualizar parametros:
   - `PUT /api/segmentacion/parametros`.
3. Cargar clientes autoelevador:
   - desde el panel `/segmentacion-clientes`, pestania `Carga`.
   - `POST /api/segmentacion/autoelevador/import` con CSV o JSON.
4. Cargar geografia de clientes:
   - `POST /api/segmentacion/geografia/bulk`.
5. Validar padrón activo:
   - `GET /api/segmentacion/clientes-activos`.
6. Refrescar cache:
   - `POST /api/segmentacion/cache/refresh`.
7. Ejecutar recalculo oficial:
   - `POST /api/segmentacion/recalcular`.
8. Verificar resultados:
   - `GET /api/segmentacion/clusters`
   - `GET /api/segmentacion/cluster-logistico`
   - `GET /api/segmentacion/mapa/clientes`
   - `GET /api/segmentacion/resumen/sucursal`
   - `GET /api/segmentacion/resumen/localidad`
9. Revisar trazabilidad:
   - `GET /api/segmentacion/auditoria`.
10. Publicar en panel:
   - validar que el dashboard consuma vistas y endpoints actualizados.

## 12. Anexo: descarga del SOP en PDF

Archivo esperado:

- `docs/SOP_Segmentacion_Clientes_DPO.pdf`

Endpoint disponible:

- `GET /api/segmentacion/sop/pdf`

Generacion local reproducible:

```bash
python scripts/generar_sop_pdf.py
```
