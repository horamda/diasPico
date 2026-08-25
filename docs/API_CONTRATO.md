# Contrato de API

Actualizado: 2026-08-13.

Este contrato consolida las rutas publicas del backend Flask. Todas las rutas de integracion deben consumir el prefijo `/api`; las rutas sin `/api` son pantallas HTML o alias administrativos internos.

## Base URL

Produccion:

```text
https://TU-DOMINIO
```

Local:

```text
http://localhost:5001
```

Healthcheck:

```http
GET /api/health
```

## Ruta que Deben Tomar

Para integraciones externas, usar estas rutas base:

| Dominio | Ruta base recomendada | Uso |
| --- | --- | --- |
| Rechazos | `/api/rechazos` | Motivos, sync y rechazos diarios. |
| Dias pico | `/api/picos` | Calendario, KPIs, historico, venta por dia, dotacion y periodos criticos. |
| Segmentacion clientes | `/api/segmentacion` | Segmentacion DPO, clientes, clusters, NPS, costos, cache e imports propios. |
| Carga de datos | `/api/upload` | Importacion de archivos operativos. |
| Catalogo | `/api/catalogo` | Empresas, sucursales, empleados y dotacion operativa. |
| Recursos | `/api/recursos` | Equipos, disponibilidad, dotacion y flota de operacion. |
| Control stock | `/api/control-stock` | ABC, conteos, planificacion y responsables. |
| Frescura | `/api/frescura` | Stock, articulos criticos, oportunidades y planes de accion. |
| Planificacion picos | `/api/planificacion_picos` | Simulador, capacidad, escenarios, alertas y export. |
| Dropsize | `/api/dropsize` | Resumen, evolucion, objetivos, recalculo y export. |
| Flota | `/api/flota` | Vehiculos, disponibilidad y sync de transportes. |
| Portal | `/api/portal` | Usuario actual, modulos, dashboard y administracion. |
| Sync operativo | `/api/sync` | Sincronizacion y consultas operativas desde Sheets. |
| Integracion logistica v1 | `/api/v1/integracion/logistica` | Volumen diario unificado por camion y chofer para aplicaciones externas. |
| Simulaciones logisticas | `/api/simulaciones` | Calculo, guardado, avance, cierre y aprendizaje. |
| Admin proyecto | `/api/admin-proyecto` | Estado tecnico de tablas, indices y dashboard. |
| Foxtrot review | `/api/foxtrot` | Datasets y edicion de filas de revision. |

Recomendacion concreta para rechazos: consumir `GET /api/rechazos/diario/integracion` cuando la app externa necesite una respuesta completa. Si la app necesita pantallas o procesos separados, consumir `GET /api/rechazos/diario/resumen` y `GET /api/rechazos/diario/detalle`.

## Convenciones

- Formato de fechas: `YYYY-MM-DD`.
- Meses: `YYYY-MM`.
- Filtros comunes: `sucursal=TODAS` o codigo de sucursal.
- Respuestas exitosas: JSON, salvo endpoints de exportacion o plantillas.
- Errores esperados: JSON con clave `error` cuando la ruta valida parametros.
- Autenticacion: los endpoints legacy `/api` no agregan autenticacion propia. La integracion logistica v1 exige una API key exclusiva mediante `INTEGRATION_API_KEY`; el consumidor debe enviar `X-API-Key` o `Authorization: Bearer <clave>`. Si la variable no esta configurada, la ruta responde `503` y no expone datos.

## Endpoints Principales

### Salud

| Metodo | Ruta |
| --- | --- |
| GET | `/api/health` |

### Integracion Logistica v1

Endpoint recomendado para una aplicacion externa:

```http
GET /api/v1/integracion/logistica/diaria
```

La consulta requiere un dia (`fecha`) o un rango inclusivo (`desde` y `hasta`). El rango maximo es de 31 dias.

| Parametro | Requerido | Descripcion |
| --- | --- | --- |
| `fecha` | Si, como alternativa al rango | Dia en formato `YYYY-MM-DD`. |
| `desde` | Si, cuando no se usa `fecha` | Inicio del rango `YYYY-MM-DD`. |
| `hasta` | Si, cuando no se usa `fecha` | Fin del rango `YYYY-MM-DD`. |
| `empresa_id` | No | Empresa; valor por defecto `1`. |
| `sucursal` | No | `TODAS` o identificador de sucursal; valor por defecto `TODAS`. |
| `incluir_clientes` | No | `1` agrega `clientes_detalle`; valor por defecto `0`. |
| `limit` | No | Maximo 1000 sin clientes y 200 con detalle de clientes. |
| `offset` | No | Desplazamiento para paginacion; valor por defecto `0`. |

Ejemplo:

```bash
curl "https://TU-DOMINIO/api/v1/integracion/logistica/diaria?desde=2026-08-01&hasta=2026-08-24&sucursal=1" \
  -H "X-API-Key: TU_CLAVE"
```

Cada elemento de `datos` representa una combinacion de fecha, sucursal, camion y chofer. Campos principales:

```json
{
  "fecha": "2026-08-13",
  "empresa_id": "1",
  "sucursal_id": "1",
  "sucursal": "Casa Central",
  "camion_codigo": "1100",
  "camion_descripcion": "IVECO TECTOR",
  "patente": "KTO613",
  "marca": "IVECO",
  "modelo": "2018",
  "carga_maxima_kg": 18000.0,
  "capacidad_up": 700.0,
  "camion_en_maestro_flota": true,
  "chofer_codigo": "15",
  "chofer": "Nombre del chofer",
  "clientes": 42,
  "documentos": 45,
  "bultos": 520.5,
  "hl": 48.7,
  "pallets_estimados": 6.3,
  "up": 680.0,
  "lineas_origen": 120,
  "calidad": {
    "pallets_completos": true,
    "articulos_sin_configuracion_pallet": 0,
    "bultos_sin_conversion_pallet": 0.0,
    "camion_identificado": true,
    "chofer_identificado": true
  }
}
```

La respuesta incluye `api_version`, `generado_en`, `filtros`, `cobertura_resultado`, `paginacion`, `calidad_datos` y `datos`. Tambien informa el total en el header `X-Total-Count`.

Fuentes y alcance:

- Volumen, clientes y asignacion camion/chofer: `ventas_detalle`.
- Patente, marca, modelo y capacidades: `flota_vehiculos`, con fallback a `transportes`.
- Pallets: estimacion `bultos / bultos_por_pallet`; los faltantes se informan en `calidad`.
- Solo se incluyen movimientos de mercaderia con una venta registrada; un camion operativo sin venta no genera una fila.

### Rechazos

| Metodo | Ruta |
| --- | --- |
| GET | `/api/rechazos` |
| PATCH | `/api/rechazos/<motivo_key>` |
| POST | `/api/rechazos/sync` |
| GET | `/api/rechazos/diario/resumen` |
| GET | `/api/rechazos/diario/detalle` |
| GET | `/api/rechazos/diario/integracion` |
| GET | `/api/rechazos/por-cliente` |
| GET | `/api/rechazos/por-motivo` |

Parametros diarios: `desde`, `hasta`, `sucursal`.

### Dias Pico

| Metodo | Ruta |
| --- | --- |
| GET | `/api/picos/calendario` |
| GET | `/api/picos/kpis` |
| GET | `/api/picos/historico` |
| GET | `/api/picos/venta-dia` |
| GET | `/api/picos/venta-dia/export` |
| GET | `/api/picos/experiencia-clientes` |
| GET | `/api/picos/analisis-hl` |
| GET | `/api/picos/analisis-rechazos` |
| GET | `/api/picos/dia` |
| GET | `/api/picos/dias-detalle/export` |
| GET | `/api/picos/rechazos-dolores/diario` |
| GET | `/api/picos/comparativo-anual` |
| GET | `/api/picos/venta-anual` |
| GET | `/api/picos/dotacion-diaria` |
| GET | `/api/picos/cobertura-dotacion` |
| GET | `/api/picos/ausentismo-mensual` |
| POST | `/api/picos/ausentismo-mensual` |
| POST | `/api/picos/ausentismo-mensual/import` |
| GET | `/api/picos/periodos-criticos` |
| POST | `/api/picos/periodos-criticos` |
| DELETE | `/api/picos/periodos-criticos/<periodo_id>` |

### Segmentacion Clientes

| Metodo | Ruta |
| --- | --- |
| GET | `/api/segmentacion/parametros` |
| PUT | `/api/segmentacion/parametros` |
| GET | `/api/segmentacion/periodo` |
| PUT | `/api/segmentacion/periodo` |
| GET | `/api/segmentacion/score-pesos` |
| PUT | `/api/segmentacion/score-pesos` |
| GET | `/api/segmentacion/cache` |
| GET | `/api/segmentacion/cache/status` |
| POST | `/api/segmentacion/cache/refresh` |
| POST | `/api/segmentacion/cache/repair-scores` |
| GET | `/api/segmentacion/calidad-datos` |
| GET | `/api/segmentacion/metricas` |
| GET | `/api/segmentacion/clientes-activos` |
| GET | `/api/segmentacion/clusters` |
| GET | `/api/segmentacion/cluster-logistico` |
| GET | `/api/segmentacion/mapa/clientes` |
| GET | `/api/segmentacion/experiencia-clientes` |
| GET | `/api/segmentacion/nps/resumen-anual` |
| GET | `/api/segmentacion/inflacion` |
| GET | `/api/segmentacion/autoelevador/resumen` |
| GET | `/api/segmentacion/plan-servicio` |
| GET | `/api/segmentacion/clientes/export` |
| GET | `/api/segmentacion/reporte/costos-atencion` |
| GET | `/api/segmentacion/reporte/costos-atencion/export` |
| GET | `/api/segmentacion/cliente/<cliente>` |
| GET | `/api/segmentacion/cliente/<cliente>/evolucion` |
| GET | `/api/segmentacion/cliente/<cliente>/export` |
| GET | `/api/segmentacion/cliente/<cliente>/nps` |
| GET | `/api/segmentacion/resumen/sucursal` |
| GET | `/api/segmentacion/resumen/localidad` |
| GET | `/api/segmentacion/resumen/activos-localidad` |
| GET | `/api/segmentacion/evolucion-mensual` |
| GET | `/api/segmentacion/auditoria` |
| GET | `/api/segmentacion/sop/pdf` |
| GET | `/api/segmentacion/plantillas/servicio/<metric>/<modo>` |
| GET | `/api/segmentacion/plantillas/inflacion` |
| GET | `/api/segmentacion/plantillas/nps-detallado` |
| POST | `/api/segmentacion/clientes/atributos` |
| POST | `/api/segmentacion/clientes/atributos/bulk` |
| POST | `/api/segmentacion/geografia/bulk` |
| POST | `/api/segmentacion/autoelevador/import` |
| POST | `/api/segmentacion/inflacion/import` |
| POST | `/api/segmentacion/promotor/import` |
| POST | `/api/segmentacion/servicio/import` |
| POST | `/api/segmentacion/servicio/historico/import` |
| POST | `/api/segmentacion/nps-detallado/import` |
| POST | `/api/segmentacion/historico/recalcular` |
| POST | `/api/segmentacion/recalcular` |

### Carga de Datos

| Metodo | Ruta |
| --- | --- |
| POST | `/api/upload/articulos` |
| POST | `/api/upload/articulos-faltantes` |
| POST | `/api/upload/articulos-completar-desde-ventas` |
| POST | `/api/upload/resumen` |
| POST | `/api/upload/detalle` |
| POST | `/api/upload/ventas-detalle` |
| POST | `/api/upload/clientes` |
| POST | `/api/upload/transportes` |
| POST | `/api/upload/rechazos` |

### Catalogo y Parametros

| Metodo | Ruta |
| --- | --- |
| GET | `/api/catalogo/status` |
| GET | `/api/catalogo/empresas` |
| GET | `/api/catalogo/sucursales` |
| GET | `/api/catalogo/empleados` |
| GET | `/api/catalogo/catalogo` |
| GET | `/api/catalogo/dotacion_operativa` |
| GET | `/api/sucursales` |
| POST | `/api/sucursales` |
| DELETE | `/api/sucursales/<sucursal_id>` |
| GET | `/api/parametros` |
| POST | `/api/parametros` |

### Recursos, Eventos y Feriados

| Metodo | Ruta |
| --- | --- |
| GET | `/api/recursos/equipos` |
| GET | `/api/recursos/disponibles` |
| GET | `/api/recursos/dotacion-entrega` |
| GET | `/api/recursos/flota-operacion` |
| POST | `/api/recursos/sync-capacidad` |
| GET | `/api/eventos` |
| POST | `/api/eventos` |
| DELETE | `/api/eventos/<evento_id>` |
| GET | `/api/feriados` |
| POST | `/api/feriados` |
| POST | `/api/feriados/sync` |
| DELETE | `/api/feriados/<fecha_str>` |
| DELETE | `/api/feriados/mes/<anio>/<mes>` |
| DELETE | `/api/feriados/anio/<anio>` |

### Control Stock y Frescura

| Metodo | Ruta |
| --- | --- |
| GET | `/api/control-stock/abc` |
| GET | `/api/control-stock/planilla` |
| PUT | `/api/control-stock/articulos/<id_articulo>/logistica` |
| GET | `/api/control-stock/control-externo/sorteo` |
| GET | `/api/control-stock/planificacion` |
| GET | `/api/control-stock/pendientes-dias` |
| GET | `/api/control-stock/resumen-mensual` |
| GET | `/api/control-stock/articulos-controlados` |
| GET | `/api/control-stock/resumen-articulo` |
| GET | `/api/control-stock/abc-mensual` |
| GET | `/api/control-stock/frescura-status` |
| POST | `/api/control-stock/conteos` |
| POST | `/api/control-stock/conteos/validar-dispersion` |
| PUT | `/api/control-stock/conteos/<conteo_id>/items/<id_articulo>` |
| GET | `/api/control-stock/responsables` |
| POST | `/api/control-stock/responsables` |
| PUT | `/api/control-stock/responsables/<responsable_id>` |
| GET | `/api/frescura/errores-stock` |
| GET | `/api/frescura/config` |
| POST | `/api/frescura/config` |
| GET | `/api/frescura/sync` |
| GET | `/api/frescura/articulos` |
| GET | `/api/frescura/articulos/criticos` |
| GET | `/api/frescura/articulos/<codigo_articulo>/resumen` |

Notas de `/api/control-stock/planilla`:
- Cada item incluye datos logisticos: `bultos_por_pallet`, `bultos_por_piso`, `pisos`, `unidades_por_bulto`.
- Si `bultos_por_piso` falta pero existen `bultos_por_pallet` y `pisos`, el backend lo calcula como `bultos_por_pallet / pisos`.
- Cada item informa `logistica_incompleta` y `logistica_faltante`.
- La respuesta incluye `logistica_filtrada` con `total_articulos`, `completos` e `incompletos`.

`PUT /api/control-stock/articulos/<id_articulo>/logistica` actualiza datos logisticos del maestro de articulos. Body JSON: `bultos_por_pallet`, `pisos`, `bultos_por_piso`. Si `bultos_por_piso` no se envia, se calcula con `bultos_por_pallet / pisos`.

Notas de `/api/control-stock/pendientes-dias`:
- Los pendientes se calculan desde el inicio operativo del modulo: `2026-08-10`.
- Fechas anteriores a `2026-08-10` no generan pendientes.
- La respuesta incluye `desde`, `hasta` y `periodo_activo`.
| GET | `/api/frescura/articulos/<codigo_articulo>/clientes` |
| GET | `/api/frescura/articulos/<codigo_articulo>/oportunidades` |
| GET | `/api/frescura/articulos/<codigo_articulo>/clientes/export` |
| POST | `/api/frescura/articulos/<codigo_articulo>/plan-accion` |

### Planificacion, Dropsize, Flota y Simulaciones

| Metodo | Ruta |
| --- | --- |
| POST | `/api/planificacion_picos/generar` |
| GET | `/api/planificacion_picos/<planificacion_id>` |
| POST | `/api/planificacion_picos/<planificacion_id>/recalcular` |
| POST | `/api/planificacion_picos/<planificacion_id>/actualizar_real` |
| GET | `/api/planificacion_picos/<planificacion_id>/escenarios` |
| POST | `/api/planificacion_picos/<planificacion_id>/escenarios` |
| POST | `/api/planificacion_picos/<planificacion_id>/escenarios/<escenario_id>/activar` |
| GET | `/api/planificacion_picos/variables` |
| POST | `/api/planificacion_picos/variables` |
| GET | `/api/planificacion_picos/<planificacion_id>/variables` |
| POST | `/api/planificacion_picos/variables/valores` |
| GET | `/api/planificacion_picos/configuracion` |
| POST | `/api/planificacion_picos/configuracion` |
| GET | `/api/planificacion_picos/resumen` |
| GET | `/api/planificacion_picos/comparativo` |
| GET | `/api/planificacion_picos/evolucion_diaria` |
| GET | `/api/planificacion_picos/dias_pico` |
| GET | `/api/planificacion_picos/alertas` |
| GET | `/api/planificacion_picos/capacidad` |
| POST | `/api/planificacion_picos/capacidad` |
| GET | `/api/planificacion_picos/simulador` |
| POST | `/api/planificacion_picos/simulador` |
| GET | `/api/planificacion_picos/capacidad_mensual` |
| POST | `/api/planificacion_picos/capacidad_mensual` |
| POST | `/api/planificacion_picos/sync_empleados_sheets` |
| GET | `/api/planificacion_picos/export` |
| GET | `/api/dropsize/resumen` |
| GET | `/api/dropsize/evolucion_diaria` |
| GET | `/api/dropsize/evolucion_mensual` |
| GET | `/api/dropsize/ranking_sucursales` |
| GET | `/api/dropsize/comparativo` |
| GET | `/api/dropsize/dias_pico` |
| GET | `/api/dropsize/objetivos` |
| POST | `/api/dropsize/objetivos` |
| DELETE | `/api/dropsize/objetivos/<objetivo_id>` |
| POST | `/api/dropsize/recalcular` |
| GET | `/api/dropsize/export` |
| GET | `/api/flota/vehiculos` |
| POST | `/api/flota/vehiculos` |
| DELETE | `/api/flota/vehiculos/<vehiculo_id>` |
| POST | `/api/flota/disponibilidad` |
| POST | `/api/flota/sync-transportes` |
| POST | `/api/simulaciones/calcular` |
| POST | `/api/simulaciones/guardar` |
| GET | `/api/simulaciones` |
| GET | `/api/simulaciones/<simulacion_id>` |
| POST | `/api/simulaciones/<simulacion_id>/avance` |
| POST | `/api/simulaciones/<simulacion_id>/cerrar` |
| GET | `/api/simulaciones/sugerir` |
| GET | `/api/simulaciones/aprendizaje` |

### Portal, Admin, Sync y Revision

| Metodo | Ruta |
| --- | --- |
| GET | `/api/portal/dashboard-kpis` |
| GET | `/api/portal/me` |
| GET | `/api/portal/modulos` |
| GET | `/api/portal/admin/usuarios` |
| POST | `/api/portal/admin/usuarios` |
| PUT | `/api/portal/admin/usuarios/<user_id>` |
| GET | `/api/portal/admin/usuarios/<user_id>/accesos` |
| PUT | `/api/portal/admin/usuarios/<user_id>/accesos` |
| GET | `/api/portal/admin/modulos` |
| POST | `/api/portal/admin/modulos` |
| PUT | `/api/portal/admin/modulos/<module_id>` |
| DELETE | `/api/portal/admin/modulos/<module_id>` |
| GET | `/api/admin-proyecto/resumen` |
| GET | `/api/admin-proyecto/dashboard` |
| GET | `/api/admin-proyecto/tablas` |
| GET | `/api/admin-proyecto/indices` |
| GET | `/api/admin-proyecto/candidatas-limpieza` |
| POST | `/api/sync/sheets-operativo` |
| GET | `/api/sync/debug-sheets` |
| GET | `/api/sync/operacion-camiones/anios` |
| GET | `/api/sync/operacion-camiones/mensual` |
| GET | `/api/foxtrot/datasets` |
| GET | `/api/foxtrot/<dataset>/rows` |
| PATCH | `/api/foxtrot/<dataset>/rows/<row_id>` |

## Rutas HTML

Estas rutas renderizan pantallas y no forman parte del contrato API externo:

```text
/
/login
/logout
/portal
/portal/admin
/dias-pico
/reporte-picos
/segmentacion-clientes
/frescura-oportunidades
/importaciones-datos
/importaciones
/control-stock
/dashboard
/admin
/admin/proyecto
/admin/segmentacion
/admin/dropsize
/admin/planificacion_picos
```
