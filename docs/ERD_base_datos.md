# ERD base de datos

Fuente: introspeccion de PostgreSQL schema `public` el 2026-05-26.

Convenciones:

- `PK`: clave primaria declarada.
- `FK`: clave foranea declarada en PostgreSQL.
- `FK logica`: relacion usada por la aplicacion, pero no declarada como constraint.
- Los diagramas muestran columnas de identidad y union. No listan todas las columnas descriptivas para mantenerlos legibles.

## Punto critico para autoelevador

La tabla actual `cliente_autoelevador` tiene `is_cliente`, pero no tiene `sucursal`.

Eso es insuficiente para el modelo real que definimos:

- `clientes` es la tabla maestra.
- Cada cliente del detalle debe unirse a `clientes` por `cliente + sucursal`.
- `cliente_autoelevador` tambien debe unirse por `is_cliente + sucursal`.

Diseno recomendado:

```mermaid
erDiagram
    sucursales ||--o{ clientes : "id = sucursal"
    clientes ||--o| cliente_autoelevador : "cliente+sucursal"

    sucursales {
        varchar id PK
        varchar nombre
        boolean activa
    }

    clientes {
        varchar cliente PK
        varchar sucursal "FK logica a sucursales.id"
        varchar localidad
        varchar coord_x
        varchar coord_y
        varchar fuerza_venta_1_dias_visita
        varchar anulado
    }

    cliente_autoelevador {
        bigint id PK
        varchar is_cliente "FK logica a clientes.cliente"
        varchar sucursal "FK logica a clientes.sucursal"
        boolean autoelevador
        varchar fuente
        timestamp fecha_importacion
    }
```

Regla de carga recomendada para el archivo de autoelevador:

```text
cliente,sucursal,autoelevador
10001,1,SI
10055,2,NO
```

Con indice unico recomendado:

```sql
UNIQUE (is_cliente, sucursal)
```

## Nucleo clientes, ventas y segmentacion

```mermaid
erDiagram
    sucursales ||--o{ clientes : "id = sucursal, logica"
    sucursales ||--o{ ventas_detalle : "id = sucursal, logica"
    clientes ||--o{ ventas_detalle : "cliente+sucursal, logica"
    articulos ||--o{ ventas_detalle : "id_articulo, logica"
    rechazos ||--o{ ventas_detalle : "motivo_key = motivo_rechazo, logica"
    clientes ||--o| cliente_geografia : "cliente+sucursal, logica"
    clientes ||--o| cliente_autoelevador : "cliente = is_cliente, actual"
    clientes ||--o| seg_clientes_atributos : "cliente, logica"
    clientes ||--o{ seg_cliente_cluster_historico : "cliente+sucursal_id, logica"
    sucursales ||--o{ seg_parametros : "id = sucursal_id, logica"
    sucursales ||--o{ seg_cliente_cluster_historico : "id = sucursal_id, logica"

    sucursales {
        varchar id PK
        varchar empresa_id
        varchar nombre
        boolean activa
    }

    clientes {
        varchar cliente PK
        varchar sucursal
        varchar razon_social
        varchar nombre_fantasia
        varchar localidad
        varchar coord_x
        varchar coord_y
        varchar anulado
        varchar fuerza_venta_1_dias_visita
    }

    ventas_detalle {
        bigint id PK
        varchar sucursal
        integer id_articulo
        varchar cliente
        date fecha
        numeric bultos
        numeric importe_neto
        varchar motivo_rechazo
        varchar ruta
        varchar transporte
    }

    articulos {
        integer id_articulo PK
        varchar descripcion
        numeric bultos_por_pallet
        numeric peso
        varchar tipo_producto
        varchar marca
    }

    rechazos {
        varchar motivo_key PK
        varchar motivo_rechazo
        boolean tomar
        varchar sector
    }

    cliente_geografia {
        varchar cliente_id PK
        numeric latitud
        numeric longitud
        text localidad
        text sucursal
    }

    cliente_autoelevador {
        bigint id PK
        varchar is_cliente
        boolean autoelevador
        varchar fuente
        timestamp fecha_importacion
    }

    seg_clientes_atributos {
        varchar cliente PK
        varchar sucursal_id
        varchar localidad
        boolean autoelevador
        numeric nps_valor
        numeric rmd_valor
        numeric otif_valor
        boolean activo
    }

    seg_parametros {
        integer id PK
        varchar empresa_id
        varchar sucursal_id
        smallint anio_base
        smallint anio_ytd
        smallint mes_ytd_hasta
        boolean activo
    }

    seg_periodos_calculo {
        bigint id PK
        varchar empresa_id
        smallint periodo_anio
        smallint periodo_mes
        date fecha_desde
        date fecha_hasta
        boolean activo
    }

    seg_score_pesos {
        varchar variable PK
        varchar dimension
        numeric peso
        boolean activo
    }

    seg_cliente_cluster_historico {
        bigint id PK
        varchar cliente
        varchar sucursal_id
        smallint periodo_anio
        smallint periodo_mes
        varchar cluster_dpo
        numeric score_total
        numeric otif_valor
    }

    seg_auditoria {
        bigint id PK
        varchar accion
        smallint periodo_anio
        smallint periodo_mes
        integer clientes_procesados
        varchar ejecutado_por
    }

    seg_schema_version {
        varchar component PK
        varchar version
        timestamp applied_at
    }
```

## Planificacion de picos y capacidad

```mermaid
erDiagram
    sucursales ||--o{ planificacion_picos : "id = sucursal_id, logica"
    sucursales ||--o{ planificacion_estadistica_diaria : "id = sucursal_id, logica"
    sucursales ||--o{ factor_estacionalidad : "id = sucursal_id, logica"
    sucursales ||--o{ configuracion_picos : "id = sucursal_id, logica"
    sucursales ||--o{ capacidad_operativa : "id = sucursal_id, logica"
    sucursales ||--o{ capacidad_mensual : "id = sucursal_id, logica"
    planificacion_picos ||--o{ planificacion_picos_real : "FK"
    planificacion_picos ||--o{ planificacion_picos_dias : "FK"
    planificacion_picos ||--o{ planificacion_picos_escenarios : "FK"
    planificacion_picos ||--o{ planificacion_variables_plan : "FK"
    planificacion_variables ||--o{ planificacion_variables_plan : "FK"
    planificacion_variables ||--o{ planificacion_variables_valores : "FK"

    planificacion_picos {
        bigint id PK
        varchar empresa_id
        varchar sucursal_id
        smallint anio
        smallint mes
        varchar estado
    }

    planificacion_picos_real {
        bigint id PK
        bigint planificacion_id FK
        numeric hl_real
        numeric bultos_real
        numeric camiones_promedio_real
        varchar estado_general
    }

    planificacion_picos_dias {
        bigint id PK
        bigint planificacion_id FK
        date fecha
        boolean es_pico
    }

    planificacion_picos_escenarios {
        bigint id PK
        bigint planificacion_id FK
        varchar nombre
        numeric hl_plan
    }

    planificacion_variables {
        bigint id PK
        varchar empresa_id
        varchar sucursal_id
        varchar codigo
        varchar nombre
        boolean activo
    }

    planificacion_variables_plan {
        bigint id PK
        bigint planificacion_id FK
        bigint variable_id FK
        numeric valor_base
        numeric valor_plan
        numeric valor_real
    }

    planificacion_variables_valores {
        bigint id PK
        bigint variable_id FK
        varchar sucursal_id
        date fecha
        numeric valor
    }

    planificacion_estadistica_diaria {
        bigint id PK
        varchar sucursal_id
        date fecha
        numeric hl
        numeric bultos
        integer salidas
        integer pdv_unicos
    }

    factor_estacionalidad {
        bigint id PK
        varchar sucursal_id
        smallint mes
        numeric factor_hl
        numeric factor_pdv
        numeric factor_salidas
    }

    configuracion_picos {
        bigint id PK
        varchar sucursal_id
        numeric umbral_pico_hl_pct
        numeric umbral_pico_salidas_pct
        boolean activo
    }

    capacidad_operativa {
        bigint id PK
        varchar sucursal_id
        date fecha
        numeric camiones_disponibles
        numeric choferes
        numeric acompanantes
    }

    capacidad_mensual {
        bigint id PK
        varchar sucursal_id
        smallint anio
        smallint mes
        integer camiones_disponibles
        integer choferes
        integer ayudantes
    }

    parametros_pico {
        varchar sucursal PK
        numeric umbral_pct
        varchar metrica
    }

    eventos_especiales {
        integer id PK
        date fecha
        varchar sucursal
        varchar descripcion
    }

    feriados {
        integer id PK
        date fecha
        varchar descripcion
        varchar tipo
    }
```

## Simulaciones logisticas

```mermaid
erDiagram
    sucursales ||--o{ simulaciones_logisticas : "id = sucursal_id, logica"
    simulaciones_logisticas ||--o{ avances_simulaciones_logisticas : "FK"
    simulaciones_logisticas ||--o{ cierres_simulaciones_logisticas : "FK"
    simulaciones_logisticas ||--o{ aprendizaje_simulaciones_logisticas : "simulacion_id, logica"

    simulaciones_logisticas {
        bigint id PK
        varchar sucursal_id
        smallint anio
        smallint mes
        numeric hl_plan
        numeric camiones_necesarios
        numeric personas_necesarias
        varchar estado
    }

    avances_simulaciones_logisticas {
        bigint id PK
        bigint simulacion_id FK
        smallint dias_transcurridos
        numeric hl_real
        numeric camiones_real
        numeric personas_real
    }

    cierres_simulaciones_logisticas {
        bigint id PK
        bigint simulacion_id FK
        numeric hl_real
        numeric error_hl_pct
        text conclusiones
    }

    aprendizaje_simulaciones_logisticas {
        bigint id PK
        varchar sucursal_id
        smallint mes
        smallint anio
        bigint simulacion_id
        numeric factor_ajuste_hl
    }
```

## Flota, camiones y repartos

```mermaid
erDiagram
    sucursales ||--o{ flota_vehiculos : "id = sucursal_id, logica"
    flota_vehiculos ||--o{ flota_disponibilidad_mensual : "FK"
    sucursales ||--o{ transportes : "id = sucursal, logica"
    sucursales ||--o{ repartos_resumen : "id = sucursal, logica"
    repartos_resumen ||--o{ repartos_detalle : "nro_planilla+sucursal, logica"
    clientes ||--o{ repartos_detalle : "cliente = id_cliente, logica"
    articulos ||--o{ repartos_detalle : "id_articulo, logica"
    transportes ||--o{ repartos_resumen : "codigo/descripcion, logica"
    transportes ||--o{ repartos_detalle : "codigo/descripcion, logica"
    sucursales ||--o{ operacion_camiones : "id = sucursal_id, logica"

    flota_vehiculos {
        bigint id PK
        varchar sucursal_id
        varchar codigo
        varchar descripcion
        varchar placa
        numeric carga_maxima_kg
        numeric capacidad_up
        boolean anulado
    }

    flota_disponibilidad_mensual {
        bigint id PK
        bigint vehiculo_id FK
        varchar sucursal_id
        smallint anio
        smallint mes
        boolean activo
    }

    transportes {
        integer codigo PK
        varchar descripcion
        varchar placa
        numeric carga_maxima_kg
        numeric capacidad_up
        varchar sucursal
        boolean anulado
    }

    repartos_resumen {
        integer id PK
        varchar sucursal
        varchar transporte
        varchar patente
        integer nro_planilla
        date fecha_reparto
        numeric bultos_totales
        numeric pallets
        numeric peso_carga
    }

    repartos_detalle {
        integer id PK
        varchar sucursal
        integer id_cliente
        integer nro_planilla
        integer id_articulo
        numeric bultos
        numeric importe
        varchar motivo_rechazo
    }

    operacion_camiones {
        bigint id PK
        varchar sucursal_id
        date fecha
        smallint nro_salida
        varchar chofer
        varchar ayudante_1
        varchar ayudante_2
    }
```

## Dropsize, KPI y objetivos

```mermaid
erDiagram
    sucursales ||--o{ dropsize_objetivos : "id = sucursal_id, logica"
    sucursales ||--o{ dropsize_historico : "id = sucursal_id, logica"
    sucursales ||--o{ kpi_objetivos : "id = sucursal_id, logica"

    dropsize_objetivos {
        bigint id PK
        varchar sucursal_id
        varchar unidad
        numeric objetivo_minimo
        numeric objetivo_ideal
        date fecha_desde
        boolean activo
    }

    dropsize_historico {
        bigint id PK
        varchar sucursal_id
        date fecha
        smallint periodo_mes
        smallint periodo_anio
        integer clientes_entregados
        numeric total_bultos
        numeric total_hl
    }

    kpi_objetivos {
        bigint id PK
        varchar sucursal_id
        varchar indicador
        varchar nombre
        varchar unidad
        numeric objetivo
        boolean activo
    }
```

## Portal

```mermaid
erDiagram
    portal_usuarios ||--o{ portal_usuario_modulo : "FK"
    portal_modulos ||--o{ portal_usuario_modulo : "FK"

    portal_usuarios {
        bigint id PK
        varchar username
        text password_hash
        varchar nombre
        boolean activo
        boolean es_admin
    }

    portal_modulos {
        bigint id PK
        varchar codigo
        varchar titulo
        varchar ruta
        integer orden
        boolean activo
    }

    portal_usuario_modulo {
        bigint usuario_id PK "FK a portal_usuarios.id"
        bigint modulo_id PK "FK a portal_modulos.id"
        boolean puede_ver
    }
```

## Vistas principales de segmentacion

Las vistas no son tablas fisicas, pero explican el flujo de calculo del dashboard.

```mermaid
flowchart LR
    ventas_detalle --> vw_cliente_metricas
    clientes --> vw_cliente_metricas
    sucursales --> vw_cliente_metricas
    articulos --> vw_cliente_metricas
    seg_parametros --> vw_cliente_metricas
    seg_periodos_calculo --> vw_cliente_metricas
    seg_clientes_atributos --> vw_cliente_metricas
    cliente_autoelevador --> vw_cliente_metricas

    vw_cliente_metricas --> vw_clientes_activos_dpo
    vw_cliente_metricas --> vw_cliente_cluster_dpo
    vw_cliente_cluster_dpo --> vw_cliente_score
    vw_cliente_score --> vw_cliente_plan_servicio
    vw_cliente_cluster_dpo --> resumen_cluster_sucursal
    vw_cliente_cluster_dpo --> resumen_cluster_localidad

    vw_cliente_metricas --> vw_cliente_autoelevador
    vw_cliente_autoelevador --> vw_cliente_costo_operativo
    vw_cliente_costo_operativo --> vw_cliente_eficiencia_operativa
    vw_cliente_costo_operativo --> vw_cliente_cluster_logistico
    vw_cliente_cluster_dpo --> vw_clientes_mapa
    cliente_geografia --> vw_clientes_mapa
    clientes --> vw_clientes_mapa
    vw_cliente_plan_servicio --> mv_cliente_plan_servicio
```

## Observaciones de normalizacion

1. La base tiene pocas FKs reales declaradas. La mayoria de relaciones son logicas por columnas como `sucursal`, `sucursal_id`, `cliente`, `id_cliente` e `id_articulo`.
2. Para no duplicar o cruzar datos entre sucursales, las uniones de cliente deben usar siempre `cliente + sucursal`.
3. `cliente_autoelevador` debe evolucionar de `UNIQUE(is_cliente)` a `UNIQUE(is_cliente, sucursal)`.
4. `clientes.fuerza_venta_1_dias_visita = dom/DOM` debe excluirse de clientes activos.
5. `clientes.coord_x` y `clientes.coord_y` son la fuente principal para el mapa; `cliente_geografia` puede quedar como cache o enriquecimiento.
