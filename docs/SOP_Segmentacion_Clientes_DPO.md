# SOP Segmentacion de Clientes DPO

Version: 2.0
Enfoque: auditoria DPO, circuito completo
Sistema: Dashboard Dias Pico / Modulo Segmentacion de Clientes

## 1. Objetivo

Este SOP define el proceso oficial para agrupar clientes en los 4 clusters DPO, mantener la informacion trazable en el sistema, comparar el desempeno logistico por cluster y convertir el analisis en un plan de servicio operativo.

El procedimiento cubre el circuito completo:

- carga y validacion de datos fuente
- definicion de clientes activos
- calculo de ventas, crecimiento, volumen, rechazos, costos y servicio
- ajuste de crecimiento por IPC
- identificacion de clientes refrigerados
- clasificacion en clusters DPO
- calculo del score 0-100
- analisis de RMD, OTIF y NPS
- reporte de clientes costosos de atender
- exportacion de evidencia por cliente, cluster y periodo
- recalculo mensual, historico y auditoria

## 2. Alcance DPO y relacion con auditoria R4.2

Este SOP responde al requisito "4.2 Plan de agrupacion de clientes".

### 2.1 R4.2.1 - Definicion de clientes por cluster

El distribuidor define 4 clusters oficiales:

- Ganador
- En crecimiento
- Basico
- Ventas bajas

La regla base usa ingresos y crecimiento. Adicionalmente, los clientes con condicion refrigerada (`clientes.descripcion = REF`, `Refrigerado` o `Refrigerados`) se mantienen como prioridad operativa dentro de `Ganador`, con subcluster `Refrigerado`, por criticidad de cadena de frio.

Evidencia esperada:

- distribucion por cluster en el panel
- vista `vw_cliente_cluster_dpo`
- cache `seg_cliente_dpo_cache`
- historico `seg_cliente_cluster_historico`
- PDF SOP descargable desde `GET /api/segmentacion/sop/pdf`

### 2.2 R4.2.2 - SOP y conexion con equipos/sistema

El SOP documenta como se calculan, revisan y publican los clusters. La informacion queda disponible para ventas, operaciones y ruteo mediante panel, vistas, API y exportables.

Evidencia esperada:

- este SOP vigente
- captura del modulo Segmentacion de Clientes
- log de recalculo en `seg_auditoria`
- exportables por cliente, cluster o reporte operativo
- constancia de actualizacion del ruteador cuando aplique

Si el ruteador no se alimenta automaticamente desde la base, el responsable operativo debe exportar la salida aprobada y conservar evidencia de la carga manual.

### 2.3 R4.2.3 - Comparacion contra OTIF y RMD

El sistema permite comparar los clusters contra RMD, OTIF y NPS por cliente, sucursal, localidad y periodo. La auditoria requiere ejecutar el analisis al menos 2 veces al ano; el sistema soporta recalculo mensual e historico.

Evidencia esperada:

- historico mensual en `seg_cliente_cluster_historico`
- resumen por cluster con `rmd_prom`, `otif_prom` y `nps_prom`
- reporte por cliente con PDF/Excel
- archivo importado de RMD/OTIF/NPS historico

### 2.4 R4.2.4 - Plan de servicio logistico

El sistema genera un plan de servicio por cliente y cluster. El plan orienta:

- priorizacion de inventario
- frecuencia de visita y entrega
- ventanas horarias
- ruteo y consolidacion
- atencion de clientes refrigerados
- acciones sobre clientes costosos de atender
- seguimiento de rechazos, RMD, OTIF y NPS

Evidencia esperada:

- vista `vw_cliente_plan_servicio`
- reporte de costos de atencion
- mapa de clientes
- exportables operativos
- evidencia de acciones tomadas por ventas/operaciones

## 3. Responsables y frecuencia

Responsable del proceso:

- Operaciones logisticas DPO.

Responsables de datos:

- Ventas: clientes, promotores, sucursales y actividad comercial.
- Operaciones: entregas, ruteo, autoelevador, rechazos y costos logisticos.
- Servicio/Experiencia: RMD, OTIF, NPS y subdrivers.
- Administracion/BI: IPC, parametros, recalculo, historico y evidencia.

Frecuencia minima:

- Recalculo operativo: mensual.
- Revision DPO auditada: al menos 2 veces por ano.
- Actualizacion de RMD/OTIF/NPS: mensual o cuando se reciba nueva medicion.
- Actualizacion IPC: cuando se publique un nuevo dato oficial.
- Revision de clientes refrigerados/autoelevador: mensual o con cada alta/modificacion de padron.

## 4. Fuentes de datos

### 4.1 Fuentes transaccionales

- `ventas_detalle`: ventas, volumen, fechas, rutas, pedidos y lineas.
- `articulos`: conversion operativa de productos y pallets.
- `rechazos`: criterios de rechazo validos para el calculo.
- `clientes`: padron, sucursal, localidad, anulacion y descripcion.

### 4.2 Configuracion del modelo

- `seg_parametros`: percentiles, costos por HL, anio base, anio analisis y parametros generales.
- `seg_periodos_calculo`: periodo actual y periodo base comparable.
- `seg_score_pesos`: pesos de variables del score.
- `seg_inflacion_mensual`: IPC mensual.
- `seg_clientes_atributos`: atributos vigentes por cliente.
- `seg_cliente_metricas_servicio_historico`: RMD, OTIF y NPS historicos por periodo.
- `seg_cliente_nps_encuestas`: encuestas NPS detalladas.
- `seg_cliente_nps_drivers`: drivers y subdrivers NPS.
- `seg_cliente_nps_mensual`: resumen mensual NPS por cliente.
- `cliente_autoelevador`: clientes con autoelevador.
- `cliente_geografia`: latitud y longitud por cliente.

### 4.3 Salidas auditables

- `vw_clientes_activos_dpo`
- `vw_cliente_metricas`
- `vw_cliente_cluster_dpo`
- `vw_cliente_score`
- `vw_cliente_plan_servicio`
- `vw_clientes_mapa`
- `resumen_cluster_sucursal`
- `resumen_cluster_localidad`
- `seg_cliente_dpo_cache`
- `seg_cliente_cluster_historico`
- `seg_auditoria`

## 5. Formatos de carga

Los archivos se cargan desde la pestania `Carga` del modulo Segmentacion de Clientes o por los endpoints indicados.

### 5.1 RMD vigente

Plantilla:

- `GET /api/segmentacion/plantillas/servicio/rmd/vigente`

Formato CSV separado por punto y coma:

```csv
cliente;RMD;fecha_rmd
100001;4,50;2026-05-31
100002;4,10;2026-05-31
```

Reglas:

- `cliente` es obligatorio.
- `RMD` es una escala decimal de 1 a 5. No es porcentaje.
- `RMD` acepta punto o coma decimal.
- `fecha_rmd` es opcional, pero recomendada.

### 5.2 RMD historico

Plantilla:

- `GET /api/segmentacion/plantillas/servicio/rmd/historico`

Formato:

```csv
cliente;anio;mes;RMD;fecha_rmd
100001;2025;1;4,10;2025-01-31
100001;2026;5;4,50;2026-05-31
```

Reglas:

- `anio` y `mes` son obligatorios.
- `RMD` debe estar entre 1 y 5, con decimales si corresponde.
- Para dato anual consolidado se puede usar `mes = 0`.

### 5.3 OTIF vigente e historico

Plantillas:

- `GET /api/segmentacion/plantillas/servicio/otif/vigente`
- `GET /api/segmentacion/plantillas/servicio/otif/historico`

Columnas equivalentes:

- vigente: `cliente;OTIF;fecha_otif`
- historico: `cliente;anio;mes;OTIF;fecha_otif`

Definicion OTIF:

- OTIF significa `On Time In Full`.
- Mide entregas realizadas en fecha/ventana prometida y completas.
- Formula: `entregas a tiempo y completas / entregas evaluadas * 100`.

El sistema no infiere OTIF desde ventas porque se necesita fecha/ventana comprometida y confirmacion de entrega completa.

### 5.4 NPS vigente e historico

Plantillas:

- `GET /api/segmentacion/plantillas/servicio/nps/vigente`
- `GET /api/segmentacion/plantillas/servicio/nps/historico`

Columnas equivalentes:

- vigente: `cliente;NPS;fecha_nps`
- historico: `cliente;anio;mes;NPS;fecha_nps`

Este archivo guarda el valor sintetico de NPS por cliente. Para analisis detallado de promotores, pasivos, detractores y subdrivers se debe cargar NPS detallado.

### 5.5 NPS detallado con drivers

Plantilla:

- `GET /api/segmentacion/plantillas/nps-detallado`

Formato CSV, XLSX o XLSM:

```csv
id_cliente;FECHA ENC;SCORE;CATEGORIA;DRIVER PRIMARIO;DRIVER SECUNDARIO;COMENTARIO;NOMBRE CLIENTE;DESC LOCALIDAD
100001;2026-05-15 10:30:00;10;Promoter;Experiencia de entrega;Entrega en la fecha acordada;Entrega correcta;Cliente demo;La Plata
```

Reglas:

- `id_cliente`, `FECHA ENC` y `SCORE` son obligatorios.
- `SCORE` debe estar entre 0 y 10.
- `Promoter`: score 9 o 10.
- `Passive`: score 7 u 8.
- `Detractor`: score 0 a 6.
- NPS indice: porcentaje de promotores menos porcentaje de detractores.
- El subdriver `Delivery` y el driver/subdriver `General` se calculan de forma separada para logistica.

### 5.6 IPC inflacion

Plantilla:

- `GET /api/segmentacion/plantillas/inflacion`

Formato:

```csv
anio;mes;inflacion_pct
2025;1;2,20
2025;2;2,40
2026;4;2,60
```

Reglas:

- `inflacion_pct` es la variacion mensual de IPC.
- Se usa para calcular crecimiento real entre periodo base y periodo actual.
- Los decimales pueden venir con coma o punto.

### 5.7 Autoelevador

Formato CSV:

```csv
cliente;autoelevador
100001;SI
100002;NO
```

Reglas:

- `cliente` o `is_cliente` es obligatorio.
- Si no se informa la columna `autoelevador`, el cliente importado se toma como `SI`.

### 5.8 Geografia

Campos esperados:

- `cliente`
- `latitud`
- `longitud`
- `localidad`
- `sucursal`

Uso:

- mapa de clientes
- analisis territorial
- evidencia visual por cluster

## 6. Periodos e IPC

El calculo compara un periodo actual contra un periodo base equivalente.

Ejemplo:

- actual: 2026-01-01 a 2026-05-31
- base: 2025-01-01 a 2025-05-31

El crecimiento nominal se calcula como:

```text
crecimiento_nominal_pct = (venta_actual / venta_base_comparable - 1) * 100
```

El crecimiento real ajustado por IPC se calcula con un factor acumulado:

```text
inflacion_factor = producto mensual de (1 + inflacion_pct / 100)
crecimiento_real_pct = ((venta_actual / venta_base_comparable) / inflacion_factor - 1) * 100
```

Regla de uso:

- Si existe IPC completo para el periodo, `crecimiento_pct` usa crecimiento real.
- Si no existe IPC, `crecimiento_pct` usa crecimiento nominal y debe quedar advertido como limitacion.

La venta que se ajusta es la venta del periodo base, para llevarla a moneda comparable contra el periodo actual.

## 7. Clientes activos DPO

El modelo solo calcula clientes de `vw_clientes_activos_dpo`.

Reglas de exclusion:

1. Cliente anulado:
   - excluir si `estado_anulado` no es `No`.
2. Ruta temporal:
   - excluir si `ruta_venta_descripcion` contiene `temp`.
3. Cliente sin actividad relevante:
   - excluir si no tiene actividad YTD ni base comparable.

El objetivo es evitar que bajas, rutas temporales o registros no operativos distorsionen la matriz de clientes.

## 8. Metricas calculadas por cliente

La vista base es `vw_cliente_metricas`.

Metricas comerciales:

- `venta_anio_base`
- `venta_ytd`
- `venta_base_mismo_per`
- `crecimiento_nominal_pct`
- `crecimiento_real_pct`
- `crecimiento_pct`
- `inflacion_factor`

Metricas operativas:

- `hl_ytd`
- `bultos_ytd`
- `pallets_ytd`
- `up_ytd`
- `pedidos_ytd`
- `dropsize_bultos_ytd`
- `ticket_promedio_ytd`

Metricas de rechazos:

- `rechazos_ytd`
- `pedidos_rechazo_ytd`
- `lineas_rechazo_ytd`
- `hl_rechazado_ytd`
- `hl_rechazado_parcial_ytd`
- `hl_rechazado_total_ytd`
- `pct_rechazo_pedidos`
- `pct_rechazo_hl`

Regla de rechazos:

- Solo se consideran los motivos habilitados en la tabla de criterios de rechazo.
- El porcentaje operativo principal para score es `pct_rechazo_hl` cuando esta disponible.
- `pct_rechazo_pedidos` queda como indicador complementario de pedidos afectados.

Metricas de servicio:

- `rmd_valor`
- `otif_valor`
- `nps_valor`
- NPS logistico detallado por Delivery y General

Metricas de costo:

- `costo_entrega = hl_ytd * costo_entrega_hl`
- `costo_almacen = hl_ytd * costo_almacen_hl`
- `costo_logistico_total = costo_entrega + costo_almacen`
- `margen_logistico_proxy = venta_ytd - costo_logistico_total`
- `ratio_costo_logistico_pct = costo_logistico_total / venta_ytd * 100`

## 9. Reglas de clusterizacion

Vista oficial:

- `vw_cliente_cluster_dpo`

La matriz usa ingresos y crecimiento:

- ingreso: `venta_ytd`
- venta alta: percentil alto configurado, default 0.75
- venta baja: percentil bajo configurado, default 0.25
- crecimiento: percentiles dinamicos sobre `crecimiento_pct`

Reglas:

1. Ganador:
   - cliente refrigerado, o
   - `venta_ytd >= p75_ingresos` y `crecimiento_pct >= p50_crecimiento`.
2. En crecimiento:
   - `venta_ytd < p75_ingresos` y `crecimiento_pct >= p75_crecimiento`.
3. Ventas bajas:
   - `venta_ytd <= p25_ingresos` y `crecimiento_pct <= p25_crecimiento`.
4. Basico:
   - todos los clientes activos que no cumplen reglas anteriores.

Regla especial de clientes refrigerados:

- Si `clientes.descripcion` normalizada es `REF`, `Refrigerado` o `Refrigerados`, entonces `cliente_refrigerado = true`.
- El cliente se clasifica como `Ganador`.
- El subcluster queda `Refrigerado`.
- El plan de servicio exige prioridad de cadena de frio, inventario protegido y seguimiento de OTIF.

Esta regla se documenta como criterio operativo adicional por criticidad logistica. Las variables de ingreso y crecimiento se siguen calculando y quedan visibles para auditoria.

## 10. Score 0-100

Vista:

- `vw_cliente_score`

El score normaliza variables por min-max y aplica pesos de `seg_score_pesos`.

Dimensiones:

- Negocio: venta, HL y crecimiento.
- Productividad: dropsize, pallets por pedido y autoelevador.
- Servicio: rechazos, RMD y NPS.
- Rentabilidad: ratio de costo y margen logistico proxy.
- Geo/frecuencia: pedidos, localidad y sucursal.

Direccion de mejora:

- Mayor es mejor: venta, HL, crecimiento, dropsize, pallets por pedido, autoelevador, RMD, NPS, margen y frecuencia saludable.
- Menor es mejor: rechazos y ratio de costo logistico.

Tratamiento de servicio:

- RMD suma en score si esta cargado.
- NPS suma en score si esta cargado.
- OTIF se monitorea como KPI y alerta operativa; en la regla actual no suma puntos al score porque no tiene peso activo en `seg_score_pesos`.
- Si RMD o NPS faltan para un cliente, el modelo usa la mediana del universo activo para no castigar por ausencia de dato, pero la ausencia debe quedar visible como brecha de calidad.

## 11. NPS logistico

El NPS detallado permite ver como evalua cada cliente al distribuidor y que parte de la experiencia esta afectando el servicio.

Tablas:

- `seg_cliente_nps_encuestas`
- `seg_cliente_nps_drivers`
- `seg_cliente_nps_mensual`

Calculos:

- Score promedio por cliente y mes.
- Cantidad de promotores, pasivos y detractores.
- NPS indice general.
- NPS Delivery.
- NPS General.
- NPS logistico normalizado para uso operativo.
- Top subdrivers por cliente.

Uso en el modulo:

- tarjeta del cliente
- detalle mensual de respuestas
- listado de evaluaciones
- comparacion por cluster
- aporte al score mediante `nps_valor`

El subdriver Delivery es prioritario para logistica porque refleja entrega, cumplimiento, completitud y experiencia de recepcion.

## 12. Costo de atender un cliente

El reporte de costos de atencion identifica clientes costosos y explica el motivo.

Endpoint:

- `GET /api/segmentacion/reporte/costos-atencion`

Criterios considerados:

- ratio de costo logistico alto
- margen logistico proxy negativo
- bajo dropsize
- alto porcentaje de rechazo HL
- baja venta con alta complejidad operativa
- cliente sin autoelevador cuando el volumen o frecuencia lo justifican
- RMD, OTIF o NPS bajos

El reporte devuelve:

- ranking principal de clientes costosos
- motivo principal
- explicacion operativa
- score de costo
- recomendacion
- resumen por cluster/sucursal
- excluidos por baja venta con margen logistico proxy negativo

Regla de excluidos:

- Los clientes con baja venta y margen logistico proxy negativo pueden quedar fuera del ranking principal para no mezclar segmentos incomparables.
- Deben mostrarse debajo del reporte como alerta separada.
- El texto obligatorio es: "Clientes excluidos del ranking principal por baja venta, pero con margen logistico proxy negativo".

## 13. Plan de servicio logistico

Vista:

- `vw_cliente_plan_servicio`

Reglas de accion:

- Ganador: prioridad de inventario, ventanas horarias precisas, mejor seguimiento OTIF y evaluacion de servicio flexible.
- En crecimiento: acompanamiento comercial-logistico, mejora de frecuencia, seguimiento de experiencia y proteccion de crecimiento.
- Basico: servicio estandar, costo controlado, frecuencia optima y consolidacion cuando aplique.
- Ventas bajas: optimizar frecuencia, consolidar pedidos, revisar rentabilidad y evitar sobre-servicio.
- Refrigerado: prioridad cadena de frio, inventario protegido, ventanas cortas, seguimiento OTIF y validacion de condiciones de entrega.

Alertas:

- refrigerado con OTIF menor a 90
- OTIF menor a 85
- margen logistico proxy negativo
- rechazo HL alto
- Ganador con caida YTD
- NPS o RMD bajo

## 14. Recalculo, cache e historico

### 14.1 Refresco de cache

Endpoint:

- `POST /api/segmentacion/cache/refresh`

Uso:

- despues de cargar datos
- despues de cambiar parametros
- antes de revisar paneles

### 14.2 Recalculo oficial

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

- recalcula metricas
- recalcula clusters
- recalcula score
- refresca cache
- guarda snapshot historico
- registra auditoria

### 14.3 Historico mensual

Tabla:

- `seg_cliente_cluster_historico`

Clave:

- `cliente`
- `periodo_anio`
- `periodo_mes`

Uso:

- evolucion de clusters
- comparacion semestral DPO
- soporte para auditoria
- trazabilidad de cambios por cliente

### 14.4 Auditoria tecnica

Tabla:

- `seg_auditoria`

Debe registrar:

- accion
- periodo
- usuario/proceso
- cantidad de clientes procesados
- distribucion por cluster
- version de regla
- parametros usados
- duracion
- error, si existio

## 15. Procedimiento operativo paso a paso

1. Confirmar periodo activo:
   - revisar `GET /api/segmentacion/periodo`.
2. Actualizar parametros:
   - percentiles, costos por HL, anios y fechas.
3. Cargar IPC:
   - usar plantilla IPC.
   - validar que cubra desde el inicio del periodo base hasta el ultimo mes publicado.
4. Cargar datos de servicio:
   - RMD vigente e historico.
   - OTIF vigente e historico.
   - NPS vigente e historico.
   - NPS detallado con drivers y subdrivers.
5. Cargar atributos:
   - autoelevador.
   - geografia.
   - clientes refrigerados deben venir identificados como `REF` en `clientes.descripcion`.
6. Validar clientes activos:
   - excluir anulados, temporales e inactivos no comparables.
7. Refrescar cache:
   - ejecutar `POST /api/segmentacion/cache/refresh`.
8. Ejecutar recalculo oficial:
   - ejecutar `POST /api/segmentacion/recalcular`.
9. Revisar resultados:
   - clusters por sucursal.
   - clusters por localidad.
   - score.
   - NPS/RMD/OTIF.
   - rechazos HL.
   - costo de atencion.
10. Generar evidencia:
   - descargar SOP PDF.
   - exportar reporte de clientes.
   - exportar cliente individual en PDF/Excel cuando aplique.
   - guardar capturas del panel.
11. Publicar plan operativo:
   - compartir con ventas y operaciones.
   - cargar o actualizar ruteador si corresponde.
   - conservar evidencia de la publicacion.

## 16. Evidencia y exportables

SOP:

- `docs/SOP_Segmentacion_Clientes_DPO.md`
- `docs/SOP_Segmentacion_Clientes_DPO.pdf`
- `GET /api/segmentacion/sop/pdf`

Cliente individual:

- `GET /api/segmentacion/cliente/<cliente>/export?formato=pdf`
- `GET /api/segmentacion/cliente/<cliente>/export?formato=xlsx`

Datos NPS del cliente:

- `GET /api/segmentacion/cliente/<cliente>/nps`

Costos de atencion:

- `GET /api/segmentacion/reporte/costos-atencion`

Resumenes:

- `GET /api/segmentacion/resumen/sucursal`
- `GET /api/segmentacion/resumen/localidad`
- `GET /api/segmentacion/clusters`
- `GET /api/segmentacion/cluster-logistico`
- `GET /api/segmentacion/mapa/clientes`

Auditoria:

- `GET /api/segmentacion/auditoria`

## 17. Controles de calidad obligatorios

Antes de aprobar un recalculo:

1. Periodo:
   - actual y base deben tener fechas coherentes.
   - el periodo base debe ser comparable.
2. IPC:
   - validar meses cargados.
   - revisar factor acumulado.
3. Ventas:
   - no deben existir ventas negativas no justificadas.
   - clientes sin identificador deben excluirse o corregirse.
4. Clientes activos:
   - anulados excluidos.
   - rutas temporales excluidas.
5. Refrigerados:
   - clientes `REF` identificados.
   - todos deben tener `cliente_refrigerado = true`.
6. Rechazos:
   - criterios de rechazo validados.
   - `pct_rechazo_hl` no debe calcularse sobre HL nulo.
7. Servicio:
   - cobertura RMD, OTIF y NPS revisada.
   - clientes sin datos deben quedar visibles.
8. Score:
   - `0 <= score_total <= 100`.
   - pesos activos deben sumar 100 puntos.
9. Geografia:
   - latitud entre -90 y 90.
   - longitud entre -180 y 180.
10. Historico:
   - snapshot creado para el periodo.
   - no duplicar `(cliente, anio, mes)`.
11. Auditoria:
   - corrida registrada en `seg_auditoria`.
   - si hay error, debe quedar registrado.

## 18. Paquete minimo de auditoria

Para responder auditoria DPO, conservar:

1. SOP vigente en PDF.
2. Captura de parametros del modelo.
3. Captura de distribucion de clusters.
4. Archivo de RMD/OTIF/NPS importado.
5. Archivo de IPC importado o evidencia de fuente.
6. Captura de comparacion cluster vs RMD/OTIF/NPS.
7. Reporte de costos de atencion.
8. Reporte/export de clientes refrigerados.
9. Log de recalculo.
10. Evidencia de plan de servicio enviado a ventas/operaciones.
11. Evidencia de carga o actualizacion en ruteador, si aplica.

## 19. Limitaciones conocidas

- OTIF requiere fuente especifica de entregas prometidas y completas; no se debe inferir desde ventas.
- El margen logistico proxy es una aproximacion basada en costo por HL; no reemplaza rentabilidad contable completa.
- La regla de refrigerados es una prioridad operativa documentada, no una conclusion estadistica de ingresos/crecimiento.
- Si falta IPC, el crecimiento queda nominal y debe informarse como limitacion.
- Si falta RMD o NPS, el score usa mediana para no penalizar por ausencia, pero la cobertura debe corregirse.

## 20. Generacion local del PDF

Comando:

```bash
python scripts/generar_sop_pdf.py
```

Archivo generado:

- `docs/SOP_Segmentacion_Clientes_DPO.pdf`

El boton `SOP PDF` del modulo descarga este archivo.
