import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("RAILWAY_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta RAILWAY_URL en .env")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# ─── SUCURSALES ──────────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS sucursales (
    id          VARCHAR(50) PRIMARY KEY,
    empresa_id  VARCHAR(50) NOT NULL DEFAULT '1',
    nombre      VARCHAR(100) NOT NULL,
    activa      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
""")
cur.execute("""
INSERT INTO sucursales (id, empresa_id, nombre, activa) VALUES
    ('1', '1', 'Casa Central', TRUE),
    ('2', '1', 'Dolores', TRUE)
ON CONFLICT (id) DO NOTHING;
""")

# ─── ARTICULOS ───────────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS articulos (
    id_articulo         INTEGER PRIMARY KEY,
    descripcion         VARCHAR(255),
    activo              VARCHAR(10),
    bultos_por_pallet   DECIMAL(10,4),
    pisos               DECIMAL(10,4),
    apilabilidad         DECIMAL(10,4),
    bultos_por_piso     DECIMAL(10,4),
    presentacion_bulto  INTEGER,
    unidades_por_bulto  DECIMAL(10,4),
    unidad_medida       VARCHAR(50),
    desc_unidad_medida  VARCHAR(100),
    valor_unidad_medida DECIMAL(10,4),
    peso                DECIMAL(10,4),
    alcoholico          VARCHAR(10),
    division            VARCHAR(100),
    familia             VARCHAR(100),
    marca               VARCHAR(100),
    tipo_producto       VARCHAR(100),
    unidad_negocio      VARCHAR(100),
    rotacion_abc        VARCHAR(5),
    grupos_productos    VARCHAR(100),
    activo_cc           VARCHAR(10),
    activo_dolores      VARCHAR(10),
    movil               VARCHAR(20),
    anulado             VARCHAR(20),
    actualizado         TIMESTAMP DEFAULT NOW()
);
""")

# ─── REPARTOS RESUMEN ────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS repartos_resumen (
    id                  SERIAL PRIMARY KEY,
    sucursal            VARCHAR(50),
    transporte          VARCHAR(100),
    patente             VARCHAR(20),
    carga_maxima_kg     DECIMAL(10,2),
    capacidad_up        INTEGER,
    nro_planilla        INTEGER,
    fecha_reparto       DATE,
    pedidos             INTEGER,
    comprobantes        INTEGER,
    bultos_totales      DECIMAL(10,2),
    um                  DECIMAL(10,2),
    pallets             DECIMAL(10,2),
    unidad_paquete      DECIMAL(10,2),
    peso_carga          DECIMAL(10,2),
    importe_total       DECIMAL(14,2),
    picking             DECIMAL(10,2),
    fecha_llegada       TIMESTAMP,
    fecha_salida        TIMESTAMP,
    cargado             TIMESTAMP DEFAULT NOW()
);
""")

# ─── REPARTOS DETALLE ────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS repartos_detalle (
    id                      SERIAL PRIMARY KEY,
    sucursal                VARCHAR(50),
    comprobante             VARCHAR(50),
    fecha_comprobante       DATE,
    id_cliente              INTEGER,
    nombre_cliente          VARCHAR(255),
    domicilio               VARCHAR(255),
    localidad               VARCHAR(100),
    estado                  VARCHAR(50),
    nro_planilla            INTEGER,
    transporte              VARCHAR(100),
    chofer                  VARCHAR(100),
    patente                 VARCHAR(20),
    fecha_entrega_planilla  DATE,
    id_articulo             INTEGER,
    descripcion_articulo    VARCHAR(255),
    bultos                  DECIMAL(10,4),
    unidad_medida           VARCHAR(50),
    cantidad_um             DECIMAL(10,4),
    tipo_entrega            VARCHAR(10),
    deposito                VARCHAR(100),
    propio                  VARCHAR(20),
    nro_pedido              INTEGER,
    cantidad_up             DECIMAL(10,4),
    importe                 DECIMAL(14,2),
    peso                    DECIMAL(10,2),
    hora_entrega            TIME,
    motivo_rechazo          VARCHAR(255),
    ruta_venta              VARCHAR(100),
    ruta_distribucion       VARCHAR(100),
    cargado                 TIMESTAMP DEFAULT NOW()
);
""")

# ─── CLIENTES ───────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS clientes (
    cliente                 VARCHAR(50) PRIMARY KEY,
    sucursal                VARCHAR(50),
    razon_social            VARCHAR(255),
    nombre_fantasia         VARCHAR(255),
    telefonos               VARCHAR(255),
    movil                   VARCHAR(100),
    email                   VARCHAR(255),
    domicilio               VARCHAR(255),
    calle                   VARCHAR(255),
    altura                  VARCHAR(50),
    depto                   VARCHAR(50),
    calle_1                 VARCHAR(255),
    calle_2                 VARCHAR(255),
    comentario              VARCHAR(255),
    coord_x                 VARCHAR(100),
    coord_y                 VARCHAR(100),
    lugar_entrega           VARCHAR(255),
    calle_entrega           VARCHAR(255),
    altura_entrega          VARCHAR(50),
    depto_entrega           VARCHAR(50),
    calle_1_entrega         VARCHAR(255),
    calle_2_entrega         VARCHAR(255),
    comentario_entrega      VARCHAR(255),
    horario_entrega         VARCHAR(100),
    flete_entrega           VARCHAR(100),
    coord_x_entrega         VARCHAR(100),
    coord_y_entrega         VARCHAR(100),
    localidad               VARCHAR(100),
    provincia               VARCHAR(100),
    departamento            VARCHAR(100),
    area                    VARCHAR(100),
    subcanal                VARCHAR(100),
    ramo                    VARCHAR(100),
    lista_precio            VARCHAR(100),
    hereda                  VARCHAR(100),
    lista_boni              VARCHAR(100),
    forma_pago              VARCHAR(100),
    plazo_pago              VARCHAR(100),
    limite_cr_anticipo      VARCHAR(100),
    categoria               VARCHAR(100),
    apellido_paterno        VARCHAR(100),
    apellido_materno        VARCHAR(100),
    nombres                 VARCHAR(255),
    tipo_identif            VARCHAR(100),
    identificador           VARCHAR(100),
    fecha_vencimiento       DATE,
    exento_ib               VARCHAR(50),
    inscripto_ib            VARCHAR(50),
    convenio_mut            VARCHAR(100),
    agente_de_pe            VARCHAR(100),
    documento               VARCHAR(100),
    licencia_alco           VARCHAR(100),
    vencimiento             DATE,
    alta_fecha              DATE,
    anulado                 VARCHAR(50),
    anulado_fecha           DATE,
    modificacion            VARCHAR(100),
    cliente_asoc            VARCHAR(100),
    cta_y_ord               VARCHAR(100),
    fuerza_venta_1_dias_visita VARCHAR(50)
);
""")

# ─── FERIADOS ────────────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS transportes (
    codigo                       INTEGER PRIMARY KEY,
    descripcion                  VARCHAR(255),
    marca                        VARCHAR(100),
    modelo                       VARCHAR(100),
    placa                        VARCHAR(30),
    carga_maxima_kg              NUMERIC,
    capacidad_up                 NUMERIC,
    propio                       BOOLEAN,
    sucursal                     VARCHAR(50),
    deposito_defecto             INTEGER,
    descripcion_deposito_defecto VARCHAR(255),
    anulado                      BOOLEAN,
    actualizado                  TIMESTAMP DEFAULT NOW()
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS feriados (
    id          SERIAL PRIMARY KEY,
    fecha       DATE UNIQUE NOT NULL,
    descripcion VARCHAR(200),
    tipo        VARCHAR(50) DEFAULT 'nacional'
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS rechazos (
    motivo_key      VARCHAR(255) PRIMARY KEY,
    motivo_rechazo  VARCHAR(255) NOT NULL,
    sector          VARCHAR(100),
    tomar           BOOLEAN NOT NULL DEFAULT FALSE,
    actualizado     TIMESTAMP DEFAULT NOW()
);
""")

# ─── PARAMETROS PICO ─────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS parametros_pico (
    sucursal        VARCHAR(50) PRIMARY KEY,
    umbral_pct      DECIMAL(5,2) DEFAULT 1.20,
    metrica         VARCHAR(20)  DEFAULT 'bultos',
    actualizado     TIMESTAMP DEFAULT NOW()
);
""")

# Fila global por defecto
cur.execute("""
INSERT INTO parametros_pico (sucursal, umbral_pct, metrica)
VALUES ('TODAS', 1.20, 'bultos')
ON CONFLICT (sucursal) DO NOTHING;
""")

# ─── INDICES ─────────────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS dropsize_objetivos (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50),
    unidad VARCHAR(20) NOT NULL CHECK (unidad IN ('bultos', 'hl', 'pallets')),
    objetivo_minimo NUMERIC(14,4) NOT NULL,
    objetivo_ideal NUMERIC(14,4) NOT NULL,
    fecha_desde DATE NOT NULL,
    fecha_hasta DATE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS dropsize_historico (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50) NOT NULL,
    fecha DATE NOT NULL,
    periodo_mes SMALLINT NOT NULL,
    periodo_anio SMALLINT NOT NULL,
    clientes_entregados INTEGER NOT NULL DEFAULT 0,
    total_bultos NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_hl NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_pallets NUMERIC(18,4) NOT NULL DEFAULT 0,
    dropsize_bultos NUMERIC(18,4) NOT NULL DEFAULT 0,
    dropsize_hl NUMERIC(18,4) NOT NULL DEFAULT 0,
    dropsize_pallets NUMERIC(18,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, fecha)
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS kpi_objetivos (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50),
    indicador VARCHAR(80) NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    unidad VARCHAR(20) NOT NULL DEFAULT '',
    direccion VARCHAR(10) NOT NULL CHECK (direccion IN ('max', 'min')),
    objetivo NUMERIC(14,4) NOT NULL,
    alerta NUMERIC(14,4),
    fecha_desde DATE NOT NULL,
    fecha_hasta DATE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
""")

indices = [
    "CREATE INDEX IF NOT EXISTS idx_resumen_fecha      ON repartos_resumen(fecha_reparto);",
    "CREATE INDEX IF NOT EXISTS idx_resumen_sucursal   ON repartos_resumen(sucursal);",
    "CREATE INDEX IF NOT EXISTS idx_resumen_suc_fecha  ON repartos_resumen(sucursal, fecha_reparto);",
    "CREATE INDEX IF NOT EXISTS idx_detalle_fecha      ON repartos_detalle(fecha_entrega_planilla);",
    "CREATE INDEX IF NOT EXISTS idx_detalle_sucursal   ON repartos_detalle(sucursal);",
    "CREATE INDEX IF NOT EXISTS idx_detalle_articulo   ON repartos_detalle(id_articulo);",
    "CREATE INDEX IF NOT EXISTS idx_detalle_planilla   ON repartos_detalle(nro_planilla);",
    "CREATE INDEX IF NOT EXISTS idx_detalle_tipo       ON repartos_detalle(tipo_entrega);",
    "CREATE INDEX IF NOT EXISTS idx_transportes_placa  ON transportes(placa);",
    "CREATE INDEX IF NOT EXISTS idx_transportes_sucursal ON transportes(sucursal);",
    "CREATE INDEX IF NOT EXISTS idx_transportes_anulado ON transportes(anulado);",
    "CREATE INDEX IF NOT EXISTS idx_feriados_fecha     ON feriados(fecha);",
    "CREATE INDEX IF NOT EXISTS idx_rechazos_tomar     ON rechazos(tomar);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_fecha ON ventas_detalle(fecha);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_sucursal ON ventas_detalle(sucursal);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_sucursal_fecha ON ventas_detalle(sucursal, fecha);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_fecha_sucursal ON ventas_detalle(fecha, sucursal);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_suc_fecha_cliente ON ventas_detalle(sucursal, fecha, cliente);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_fecha_cliente ON ventas_detalle(fecha, cliente);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_articulo ON ventas_detalle(id_articulo);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_empresa ON ventas_detalle(empresa);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_cliente ON ventas_detalle(cliente);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_documento_codigo ON ventas_detalle(documento);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_documento ON ventas_detalle(detalle_documento);",
    "CREATE INDEX IF NOT EXISTS idx_ventas_detalle_motivo ON ventas_detalle(motivo_rechazo);",
    "CREATE INDEX IF NOT EXISTS idx_dropsize_obj_suc_unidad ON dropsize_objetivos(sucursal_id, unidad, activo);",
    "CREATE INDEX IF NOT EXISTS idx_dropsize_obj_fechas ON dropsize_objetivos(fecha_desde, fecha_hasta);",
    "CREATE INDEX IF NOT EXISTS idx_dropsize_hist_fecha ON dropsize_historico(fecha);",
    "CREATE INDEX IF NOT EXISTS idx_dropsize_hist_suc_fecha ON dropsize_historico(sucursal_id, fecha);",
    "CREATE INDEX IF NOT EXISTS idx_dropsize_hist_empresa ON dropsize_historico(empresa_id);",
    "CREATE INDEX IF NOT EXISTS idx_kpi_obj_suc_ind_activo ON kpi_objetivos(sucursal_id, indicador, activo);",
    "CREATE INDEX IF NOT EXISTS idx_kpi_obj_fechas ON kpi_objetivos(fecha_desde, fecha_hasta);",
]
for sql in indices:
    cur.execute(sql)

# ─── SEGMENTACIÓN CLIENTES DPO 2026 — Plan 4.2 ──────────────

cur.execute("""
CREATE TABLE IF NOT EXISTS seg_parametros (
    id                  SERIAL PRIMARY KEY,
    empresa_id          VARCHAR(50)   NOT NULL DEFAULT '1',
    sucursal_id         VARCHAR(50),
    costo_entrega_hl    NUMERIC(10,4) NOT NULL DEFAULT 0,
    costo_almacen_hl    NUMERIC(10,4) NOT NULL DEFAULT 0,
    percentil_alta      NUMERIC(5,4)  NOT NULL DEFAULT 0.70,
    percentil_baja      NUMERIC(5,4)  NOT NULL DEFAULT 0.30,
    umbral_crecimiento  NUMERIC(8,4)  DEFAULT NULL,
    anio_base           SMALLINT      NOT NULL DEFAULT 2025,
    anio_ytd            SMALLINT      NOT NULL DEFAULT 2026,
    mes_ytd_hasta       SMALLINT      DEFAULT NULL,
    peso_negocio        NUMERIC(5,4)  NOT NULL DEFAULT 0.35,
    peso_productividad  NUMERIC(5,4)  NOT NULL DEFAULT 0.20,
    peso_servicio       NUMERIC(5,4)  NOT NULL DEFAULT 0.20,
    peso_rentabilidad   NUMERIC(5,4)  NOT NULL DEFAULT 0.15,
    peso_geo            NUMERIC(5,4)  NOT NULL DEFAULT 0.10,
    activo              BOOLEAN       NOT NULL DEFAULT TRUE,
    version_regla       SMALLINT      NOT NULL DEFAULT 1,
    updated_at          TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_seg_pesos CHECK (
        ABS(peso_negocio + peso_productividad + peso_servicio
            + peso_rentabilidad + peso_geo - 1.0) < 0.02
    ),
    CONSTRAINT chk_seg_percentiles CHECK (
        percentil_alta > percentil_baja
        AND percentil_alta <= 1 AND percentil_baja >= 0
    )
);
""")

cur.execute("""
INSERT INTO seg_parametros (empresa_id) VALUES ('1') ON CONFLICT DO NOTHING;
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS seg_clientes_atributos (
    cliente         VARCHAR(50) PRIMARY KEY,
    sucursal_id     VARCHAR(50),
    localidad       VARCHAR(100),
    promotor        VARCHAR(255),
    autoelevador    BOOLEAN     DEFAULT FALSE,
    nps_valor       NUMERIC(6,2),
    nps_fecha       DATE,
    rmd_valor       NUMERIC(6,2),
    rmd_fecha       DATE,
    otif_valor      NUMERIC(6,2),
    otif_fecha      DATE,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMP   NOT NULL DEFAULT NOW()
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS cliente_autoelevador (
    id                BIGSERIAL PRIMARY KEY,
    is_cliente        VARCHAR(100) NOT NULL,
    autoelevador      BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_importacion TIMESTAMP NOT NULL DEFAULT NOW(),
    fuente            VARCHAR(100) NOT NULL DEFAULT 'manual',
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cliente_autoelevador_cliente UNIQUE (is_cliente),
    CONSTRAINT chk_cliente_autoelevador_cliente
        CHECK (NULLIF(BTRIM(is_cliente), '') IS NOT NULL)
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS seg_cliente_cluster_historico (
    id                      BIGSERIAL PRIMARY KEY,
    cliente                 VARCHAR(50)  NOT NULL,
    descripcion_cliente     VARCHAR(255),
    sucursal_id             VARCHAR(50),
    localidad               VARCHAR(100),
    periodo_anio            SMALLINT     NOT NULL,
    periodo_mes             SMALLINT     NOT NULL DEFAULT 0,
    cluster_dpo             VARCHAR(50),
    subcluster_logistico    VARCHAR(80),
    score_total             NUMERIC(6,2),
    dim_negocio             NUMERIC(6,2),
    dim_productividad       NUMERIC(6,2),
    dim_servicio            NUMERIC(6,2),
    dim_rentabilidad        NUMERIC(6,2),
    dim_geo                 NUMERIC(6,2),
    venta_ytd               NUMERIC(18,2),
    hl_ytd                  NUMERIC(18,4),
    otif_valor              NUMERIC(6,2),
    crecimiento_pct         NUMERIC(14,4),
    costo_logistico_total   NUMERIC(18,2),
    ratio_costo_logistico   NUMERIC(14,4),
    pedidos_ytd             INTEGER,
    dropsize_ytd            NUMERIC(14,4),
    pct_rechazo_pedidos     NUMERIC(12,4),
    fecha_calculo           TIMESTAMP    NOT NULL DEFAULT NOW(),
    version_regla           SMALLINT     NOT NULL DEFAULT 1,
    proceso                 VARCHAR(100) NOT NULL DEFAULT 'sistema',
    UNIQUE (cliente, periodo_anio, periodo_mes)
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS seg_auditoria (
    id                      BIGSERIAL PRIMARY KEY,
    accion                  VARCHAR(100) NOT NULL,
    periodo_anio            SMALLINT,
    periodo_mes             SMALLINT,
    clientes_procesados     INTEGER DEFAULT 0,
    clientes_ganador        INTEGER DEFAULT 0,
    clientes_en_crecimiento INTEGER DEFAULT 0,
    clientes_basico         INTEGER DEFAULT 0,
    clientes_ventas_bajas   INTEGER DEFAULT 0,
    version_regla           SMALLINT,
    parametros              JSONB,
    ejecutado_por           VARCHAR(100) NOT NULL DEFAULT 'sistema',
    ejecutado_at            TIMESTAMP    NOT NULL DEFAULT NOW(),
    duracion_ms             INTEGER,
    error_detalle           TEXT
);
""")

indices_seg = [
    "CREATE INDEX IF NOT EXISTS idx_seg_params_activo ON seg_parametros(activo, empresa_id);",
    "CREATE INDEX IF NOT EXISTS idx_seg_cli_suc       ON seg_clientes_atributos(sucursal_id);",
    "CREATE INDEX IF NOT EXISTS idx_seg_cli_loc       ON seg_clientes_atributos(localidad);",
    "CREATE INDEX IF NOT EXISTS idx_seg_cli_activo    ON seg_clientes_atributos(activo);",
    "CREATE INDEX IF NOT EXISTS idx_cli_auto_cliente  ON cliente_autoelevador(is_cliente);",
    "CREATE INDEX IF NOT EXISTS idx_cli_auto_flag     ON cliente_autoelevador(autoelevador);",
    "CREATE INDEX IF NOT EXISTS idx_seg_hist_cliente  ON seg_cliente_cluster_historico(cliente);",
    "CREATE INDEX IF NOT EXISTS idx_seg_hist_periodo  ON seg_cliente_cluster_historico(periodo_anio, periodo_mes);",
    "CREATE INDEX IF NOT EXISTS idx_seg_hist_cluster  ON seg_cliente_cluster_historico(cluster_dpo);",
    "CREATE INDEX IF NOT EXISTS idx_seg_hist_suc      ON seg_cliente_cluster_historico(sucursal_id);",
    "CREATE INDEX IF NOT EXISTS idx_seg_aud_at        ON seg_auditoria(ejecutado_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_seg_aud_accion    ON seg_auditoria(accion);",
]
for sql in indices_seg:
    cur.execute(sql)

# ── Vistas — se recrean en orden de dependencia ───────────────

# Limpiar vistas existentes (CASCADE elimina dependientes)
cur.execute("DROP VIEW IF EXISTS vw_cliente_plan_servicio CASCADE;")
cur.execute("DROP VIEW IF EXISTS resumen_cluster_sucursal CASCADE;")
cur.execute("DROP VIEW IF EXISTS resumen_cluster_localidad CASCADE;")
cur.execute("DROP VIEW IF EXISTS vw_cliente_score CASCADE;")
cur.execute("DROP VIEW IF EXISTS vw_cliente_cluster_dpo CASCADE;")
cur.execute("DROP VIEW IF EXISTS vw_cliente_metricas CASCADE;")

# ── vw_cliente_metricas ──────────────────────────────────────
cur.execute("""
CREATE VIEW vw_cliente_metricas AS
WITH params AS (
    SELECT costo_entrega_hl, costo_almacen_hl, anio_base, anio_ytd,
           COALESCE(mes_ytd_hasta,
                    EXTRACT(MONTH FROM CURRENT_DATE)::INT) AS mes_ytd_hasta
    FROM seg_parametros
    WHERE activo = TRUE
    ORDER BY (sucursal_id IS NULL) DESC, id DESC
    LIMIT 1
),
base AS (
    SELECT
        NULLIF(TRIM(v.cliente), '')                                     AS cliente,
        NULLIF(TRIM(v.descripcion_cliente), '')                         AS descripcion_cliente,
        COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')                    AS sucursal,
        v.fecha,
        COALESCE(v.importe_neto, 0)                                     AS importe,
        COALESCE(v.bultos, 0)                                           AS bultos,
        COALESCE(v.unidad_medida, 0)                                    AS hl,
        COALESCE(v.unidad_paquete, 0)                                   AS up,
        CASE WHEN COALESCE(a.bultos_por_pallet, 0) > 0
             THEN COALESCE(v.bultos, 0) / a.bultos_por_pallet
             ELSE 0 END                                                  AS pallets,
        CASE WHEN COALESCE(rz.tomar, FALSE) AND (
                COALESCE(v.bultos_rechazados, 0) > 0
             OR COALESCE(v.unidad_medida_rechazado, 0) > 0
             OR COALESCE(v.unidad_paquete_rechazado, 0) > 0)
             THEN 1 ELSE 0 END                                           AS es_rechazo,
        v.fecha::TEXT || '|' || NULLIF(TRIM(v.cliente), '')             AS pedido_key
    FROM ventas_detalle v
    JOIN articulos a ON a.id_articulo = v.id_articulo
    LEFT JOIN LATERAL (
        SELECT tomar FROM rechazos r
        WHERE LOWER(TRIM(COALESCE(v.motivo_rechazo, ''))) = r.motivo_key
           OR LOWER(TRIM(COALESCE(v.motivo_rechazo, ''))) LIKE r.motivo_key || ' %'
        ORDER BY LENGTH(r.motivo_key) DESC
        LIMIT 1
    ) rz ON TRUE
    WHERE LOWER(TRIM(COALESCE(a.tipo_producto, ''))) = 'mercaderia'
      AND LOWER(TRIM(COALESCE(v.documento, '')))         NOT LIKE 'remit%'
      AND LOWER(TRIM(COALESCE(v.documento, '')))         NOT LIKE 'comod%'
      AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE 'remit%'
      AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE 'comod%'
      AND NULLIF(TRIM(v.cliente), '') IS NOT NULL
),
ab AS (
    SELECT b.cliente, b.sucursal,
           MAX(b.descripcion_cliente)    AS desc_cli,
           SUM(b.importe)                AS venta,
           SUM(b.hl)                     AS hl,
           SUM(b.bultos)                 AS blt,
           SUM(b.pallets)                AS pal,
           SUM(b.up)                     AS up,
           COUNT(DISTINCT b.pedido_key)  AS ped
    FROM base b CROSS JOIN params p
    WHERE EXTRACT(YEAR FROM b.fecha)::INT = p.anio_base
    GROUP BY b.cliente, b.sucursal
),
ytd AS (
    SELECT b.cliente, b.sucursal,
           SUM(b.importe)                AS venta,
           SUM(b.hl)                     AS hl,
           SUM(b.bultos)                 AS blt,
           SUM(b.pallets)                AS pal,
           SUM(b.up)                     AS up,
           COUNT(DISTINCT b.pedido_key)  AS ped,
           SUM(b.es_rechazo)             AS rec
    FROM base b CROSS JOIN params p
    WHERE EXTRACT(YEAR  FROM b.fecha)::INT = p.anio_ytd
      AND EXTRACT(MONTH FROM b.fecha)::INT <= p.mes_ytd_hasta
    GROUP BY b.cliente, b.sucursal
),
bmp AS (
    SELECT b.cliente, b.sucursal,
           SUM(b.importe)               AS venta,
           COUNT(DISTINCT b.pedido_key) AS ped
    FROM base b CROSS JOIN params p
    WHERE EXTRACT(YEAR  FROM b.fecha)::INT = p.anio_base
      AND EXTRACT(MONTH FROM b.fecha)::INT <= p.mes_ytd_hasta
    GROUP BY b.cliente, b.sucursal
)
SELECT
    COALESCE(y.cliente,  ab.cliente)                        AS cliente,
    COALESCE(y.sucursal, ab.sucursal)                       AS sucursal,
    COALESCE(ab.desc_cli, y.cliente, '')                    AS descripcion_cliente,
    COALESCE(ab.venta, 0)                                   AS venta_anio_base,
    COALESCE(y.venta,  0)                                   AS venta_ytd,
    COALESCE(bmp.venta, 0)                                  AS venta_base_mismo_per,
    CASE WHEN COALESCE(bmp.venta, 0) > 0
         THEN ROUND(((COALESCE(y.venta, 0) - bmp.venta)
                     / bmp.venta * 100)::NUMERIC, 2)
         ELSE NULL END                                       AS crecimiento_pct,
    COALESCE(ab.hl,  0) AS hl_anio_base,   COALESCE(y.hl,  0) AS hl_ytd,
    COALESCE(ab.blt, 0) AS bultos_anio_base, COALESCE(y.blt, 0) AS bultos_ytd,
    COALESCE(ab.pal, 0) AS pallets_anio_base, COALESCE(y.pal, 0) AS pallets_ytd,
    COALESCE(ab.up,  0) AS up_anio_base,   COALESCE(y.up,  0) AS up_ytd,
    COALESCE(ab.ped, 0) AS pedidos_anio_base, COALESCE(y.ped, 0) AS pedidos_ytd,
    CASE WHEN COALESCE(y.ped, 0) > 0
         THEN ROUND((y.blt / y.ped)::NUMERIC, 2) ELSE 0 END AS dropsize_bultos_ytd,
    CASE WHEN COALESCE(y.ped, 0) > 0
         THEN ROUND((y.hl  / y.ped)::NUMERIC, 4) ELSE 0 END AS dropsize_hl_ytd,
    CASE WHEN COALESCE(y.ped, 0) > 0
         THEN ROUND((y.venta / y.ped)::NUMERIC, 2) ELSE 0 END AS ticket_promedio_ytd,
    COALESCE(y.rec, 0)                                      AS rechazos_ytd,
    CASE WHEN COALESCE(y.ped, 0) > 0
         THEN ROUND((COALESCE(y.rec, 0)::NUMERIC / y.ped * 100), 2)
         ELSE 0 END                                          AS pct_rechazo_pedidos,
    COALESCE(ca.localidad, '')                              AS localidad,
    COALESCE(cae.autoelevador, ca.autoelevador, FALSE)      AS autoelevador,
    ca.nps_valor,
    ca.rmd_valor,
    ca.otif_valor,
    ROUND((COALESCE(y.hl, 0) * p.costo_entrega_hl)::NUMERIC, 2)  AS costo_entrega,
    ROUND((COALESCE(y.hl, 0) * p.costo_almacen_hl)::NUMERIC, 2)  AS costo_almacen,
    ROUND((COALESCE(y.hl, 0)
           * (p.costo_entrega_hl + p.costo_almacen_hl))::NUMERIC, 2)
                                                             AS costo_logistico_total,
    ROUND((COALESCE(y.venta, 0)
           - COALESCE(y.hl, 0)
             * (p.costo_entrega_hl + p.costo_almacen_hl))::NUMERIC, 2)
                                                             AS margen_logistico_proxy,
    CASE WHEN COALESCE(y.venta, 0) > 0
         THEN ROUND((COALESCE(y.hl, 0)
                     * (p.costo_entrega_hl + p.costo_almacen_hl)
                     / y.venta * 100)::NUMERIC, 2)
         ELSE 0 END                                          AS ratio_costo_logistico_pct
FROM ytd y
FULL OUTER JOIN ab
    ON ab.cliente = y.cliente AND ab.sucursal = y.sucursal
LEFT JOIN bmp
    ON bmp.cliente = COALESCE(y.cliente, ab.cliente)
   AND bmp.sucursal = COALESCE(y.sucursal, ab.sucursal)
LEFT JOIN seg_clientes_atributos ca
    ON ca.cliente = COALESCE(y.cliente, ab.cliente)
LEFT JOIN cliente_autoelevador cae
    ON cae.is_cliente = COALESCE(y.cliente, ab.cliente)
CROSS JOIN params p;
""")

# ── vw_cliente_cluster_dpo ───────────────────────────────────
# percentile_cont no acepta columnas de CROSS JOIN como argumento directo;
# se usan subqueries escalares como constantes para percentil_alta/baja.
cur.execute("""
CREATE VIEW vw_cliente_cluster_dpo AS
WITH m AS (
    SELECT * FROM vw_cliente_metricas
    WHERE venta_ytd > 0 OR venta_anio_base > 0
),
umbrales AS (
    SELECT
        percentile_cont(
            COALESCE(
                (SELECT percentil_alta FROM seg_parametros
                 WHERE activo ORDER BY (sucursal_id IS NULL) DESC, id DESC LIMIT 1),
                0.70)
        ) WITHIN GROUP (ORDER BY venta_ytd)              AS umbral_venta_alta,
        percentile_cont(
            COALESCE(
                (SELECT percentil_baja FROM seg_parametros
                 WHERE activo ORDER BY (sucursal_id IS NULL) DESC, id DESC LIMIT 1),
                0.30)
        ) WITHIN GROUP (ORDER BY venta_ytd)              AS umbral_venta_baja,
        COALESCE(
            (SELECT umbral_crecimiento FROM seg_parametros
             WHERE activo AND umbral_crecimiento IS NOT NULL
             ORDER BY (sucursal_id IS NULL) DESC, id DESC LIMIT 1),
            percentile_cont(0.5) WITHIN GROUP (ORDER BY crecimiento_pct)
        )                                                 AS umbral_crecimiento,
        percentile_cont(0.25) WITHIN GROUP (ORDER BY dropsize_bultos_ytd)        AS p25_dropsize,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY dropsize_bultos_ytd)        AS p50_dropsize,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY ratio_costo_logistico_pct)  AS p75_ratio_costo
    FROM m
)
SELECT
    m.*,
    u.umbral_venta_alta,
    u.umbral_venta_baja,
    u.umbral_crecimiento,
    CASE
        WHEN m.venta_ytd >= u.umbral_venta_alta
         AND COALESCE(m.crecimiento_pct, 0) > COALESCE(u.umbral_crecimiento, 0)
            THEN 'Ganador'
        WHEN COALESCE(m.crecimiento_pct, 0) > COALESCE(u.umbral_crecimiento, 0)
            THEN 'En crecimiento'
        WHEN m.venta_ytd >= u.umbral_venta_baja
            THEN 'Básico'
        ELSE 'Ventas bajas'
    END AS cluster_dpo,
    CASE
        WHEN COALESCE(m.ratio_costo_logistico_pct, 0) > u.p75_ratio_costo
         AND m.dropsize_bultos_ytd < u.p25_dropsize
            THEN 'Caro de servir'
        WHEN COALESCE(m.pct_rechazo_pedidos, 0) > 20
            THEN 'Complejo'
        WHEN COALESCE(m.crecimiento_pct, 0) > 15
         AND COALESCE(m.pct_rechazo_pedidos, 0) < 5
            THEN 'Alto potencial'
        WHEN COALESCE(m.ratio_costo_logistico_pct, 0) <= 20
         AND m.dropsize_bultos_ytd >= u.p50_dropsize
            THEN 'Eficiente'
        WHEN COALESCE(m.ratio_costo_logistico_pct, 0) <= 25
         AND COALESCE(m.margen_logistico_proxy, 0) > 0
            THEN 'Rentable'
        ELSE 'Estándar'
    END AS subcluster_logistico
FROM m CROSS JOIN umbrales u;
""")

# ── vw_cliente_score ─────────────────────────────────────────
cur.execute("""
CREATE VIEW vw_cliente_score AS
WITH m AS (
    SELECT * FROM vw_cliente_metricas
    WHERE venta_ytd > 0 OR venta_anio_base > 0
),
md AS (
    SELECT
        COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY rmd_valor), 5)        AS med_rmd,
        COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY nps_valor), 5)        AS med_nps,
        COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY crecimiento_pct), 0)  AS med_crec
    FROM m
),
cl AS (
    SELECT m.*,
           GREATEST(-100, LEAST(300,
               COALESCE(m.crecimiento_pct, md.med_crec)))      AS cc,
           COALESCE(m.rmd_valor, md.med_rmd)                    AS ri,
           COALESCE(m.nps_valor, md.med_nps)                    AS ni,
           CASE WHEN m.pedidos_ytd > 0
                THEN m.pallets_ytd / m.pedidos_ytd ELSE 0 END  AS ppp,
           GREATEST(0, m.ratio_costo_logistico_pct)             AS rcp
    FROM m CROSS JOIN md
),
rn AS (
    SELECT c.*,
           MIN(venta_ytd)           OVER () AS mnv, MAX(venta_ytd)           OVER () AS mxv,
           MIN(hl_ytd)              OVER () AS mnh, MAX(hl_ytd)              OVER () AS mxh,
           MIN(cc)                  OVER () AS mnc, MAX(cc)                  OVER () AS mxc,
           MIN(dropsize_bultos_ytd) OVER () AS mnd, MAX(dropsize_bultos_ytd) OVER () AS mxd,
           MIN(ppp)                 OVER () AS mnp, MAX(ppp)                 OVER () AS mxp,
           MIN(pct_rechazo_pedidos) OVER () AS mnr, MAX(pct_rechazo_pedidos) OVER () AS mxr,
           MIN(ri)                  OVER () AS mnrmd, MAX(ri)                OVER () AS mxrmd,
           MIN(ni)                  OVER () AS mnnps, MAX(ni)                OVER () AS mxnps,
           MIN(rcp)                 OVER () AS mnrc,  MAX(rcp)               OVER () AS mxrc,
           MIN(margen_logistico_proxy) OVER () AS mnmg, MAX(margen_logistico_proxy) OVER () AS mxmg,
           MIN(pedidos_ytd)         OVER () AS mnped, MAX(pedidos_ytd)       OVER () AS mxped
    FROM cl c
),
nr AS (
    SELECT r.*,
           CASE WHEN mxv   > mnv   THEN (venta_ytd           - mnv  )/(mxv  -mnv  ) ELSE 0.5 END AS nv,
           CASE WHEN mxh   > mnh   THEN (hl_ytd              - mnh  )/(mxh  -mnh  ) ELSE 0.5 END AS nh,
           CASE WHEN mxc   > mnc   THEN (cc                  - mnc  )/(mxc  -mnc  ) ELSE 0.5 END AS nc,
           CASE WHEN mxd   > mnd   THEN (dropsize_bultos_ytd - mnd  )/(mxd  -mnd  ) ELSE 0.5 END AS nd,
           CASE WHEN mxp   > mnp   THEN (ppp                 - mnp  )/(mxp  -mnp  ) ELSE 0.5 END AS np,
           CASE WHEN mxr   > mnr   THEN 1-(pct_rechazo_pedidos-mnr  )/(mxr  -mnr  ) ELSE 0.5 END AS nr_,
           CASE WHEN mxrmd > mnrmd THEN (ri  - mnrmd)/(mxrmd - mnrmd)                ELSE 0.5 END AS nrmd,
           CASE WHEN mxnps > mnnps THEN (ni  - mnnps)/(mxnps - mnnps)                ELSE 0.5 END AS nnps,
           CASE WHEN mxrc  > mnrc  THEN 1-(rcp - mnrc)/(mxrc  - mnrc)                ELSE 0.5 END AS nrc,
           CASE WHEN mxmg  > mnmg  THEN (margen_logistico_proxy-mnmg)/(mxmg-mnmg)   ELSE 0.5 END AS nmg,
           CASE WHEN mxped > mnped THEN (pedidos_ytd - mnped)/(mxped - mnped)        ELSE 0.5 END AS nped
    FROM rn r
)
SELECT
    cliente, descripcion_cliente, sucursal, localidad,
    ROUND((nv*15 + nh*10 + nc*10)::NUMERIC, 2)                                         AS dim_negocio,
    ROUND((nd*10 + np*5  + (CASE WHEN autoelevador THEN 5.0 ELSE 0.0 END))::NUMERIC, 2) AS dim_productividad,
    ROUND((nr_*10 + nrmd*5 + nnps*5)::NUMERIC, 2)                                       AS dim_servicio,
    ROUND((nrc*10 + nmg*5)::NUMERIC, 2)                                                  AS dim_rentabilidad,
    ROUND((nped*7
           + (CASE WHEN NULLIF(localidad,'') IS NOT NULL THEN 2.0 ELSE 0.0 END)
           + (CASE WHEN NULLIF(sucursal,'')  IS NOT NULL THEN 1.0 ELSE 0.0 END))::NUMERIC, 2) AS dim_geo,
    ROUND((nv  *15)::NUMERIC, 2) AS pts_venta,
    ROUND((nh  *10)::NUMERIC, 2) AS pts_hl,
    ROUND((nc  *10)::NUMERIC, 2) AS pts_crecimiento,
    ROUND((nd  *10)::NUMERIC, 2) AS pts_dropsize,
    ROUND((np  * 5)::NUMERIC, 2) AS pts_pallets_ped,
    ROUND((CASE WHEN autoelevador THEN 5.0 ELSE 0.0 END)::NUMERIC, 2) AS pts_autoelevador,
    ROUND((nr_ *10)::NUMERIC, 2) AS pts_rechazos,
    ROUND((nrmd* 5)::NUMERIC, 2) AS pts_rmd,
    ROUND((nnps* 5)::NUMERIC, 2) AS pts_nps,
    ROUND((nrc *10)::NUMERIC, 2) AS pts_ratio_costo,
    ROUND((nmg * 5)::NUMERIC, 2) AS pts_margen,
    ROUND((nped* 7)::NUMERIC, 2) AS pts_frecuencia,
    ROUND((
        nv*15 + nh*10 + nc*10
      + nd*10 + np*5  + (CASE WHEN autoelevador THEN 5.0 ELSE 0.0 END)
      + nr_*10 + nrmd*5 + nnps*5
      + nrc*10 + nmg*5
      + nped*7
      + (CASE WHEN NULLIF(localidad,'') IS NOT NULL THEN 2.0 ELSE 0.0 END)
      + (CASE WHEN NULLIF(sucursal,'')  IS NOT NULL THEN 1.0 ELSE 0.0 END)
    )::NUMERIC, 2) AS score_total
FROM nr;
""")

# ── vw_cliente_plan_servicio ─────────────────────────────────
cur.execute("""
CREATE VIEW vw_cliente_plan_servicio AS
SELECT
    c.cliente, c.descripcion_cliente, c.sucursal, c.localidad, c.autoelevador,
    c.cluster_dpo, c.subcluster_logistico,
    s.score_total, s.dim_negocio, s.dim_productividad,
    s.dim_servicio, s.dim_rentabilidad, s.dim_geo,
    s.pts_venta, s.pts_hl, s.pts_crecimiento, s.pts_dropsize,
    s.pts_rechazos, s.pts_rmd, s.pts_nps,
    c.venta_ytd, c.venta_anio_base, c.crecimiento_pct,
    c.hl_ytd, c.bultos_ytd, c.pallets_ytd, c.pedidos_ytd,
    c.dropsize_bultos_ytd, c.ticket_promedio_ytd,
    c.rechazos_ytd, c.pct_rechazo_pedidos,
    c.nps_valor, c.rmd_valor, c.otif_valor,
    c.costo_entrega, c.costo_almacen, c.costo_logistico_total,
    c.margen_logistico_proxy, c.ratio_costo_logistico_pct,
    CASE c.cluster_dpo
        WHEN 'Ganador'
            THEN 'Prioridad de inventario · mejor OTIF · ventanas horarias precisas · evaluar flex/express'
        WHEN 'En crecimiento'
            THEN 'Seguimiento comercial-logístico · mejorar frecuencia · acompañar experiencia de entrega'
        WHEN 'Básico'
            THEN 'Servicio estándar · mantener costo controlado · frecuencia óptima por ruta'
        WHEN 'Ventas bajas'
            THEN 'Optimizar frecuencia · consolidar pedidos · revisar rentabilidad de servir'
        ELSE 'Sin clasificación'
    END AS plan_servicio,
    CASE c.subcluster_logistico
        WHEN 'Caro de servir' THEN 'Revisar costo logístico · negociar drop size mínimo · evaluar consolidación'
        WHEN 'Alto potencial' THEN 'Fortalecer relación comercial · asignar vendedor referente · mejorar OTIF'
        WHEN 'Eficiente'      THEN 'Mantener operación · compartir benchmarks positivos con el equipo'
        WHEN 'Rentable'       THEN 'Proteger cuenta · renovar acuerdo · ofrecer beneficios premium'
        WHEN 'Complejo'       THEN 'Plan mejora de rechazo · visita técnica · acuerdo de entrega revisado'
        ELSE                       'Monitorear indicadores mensualmente'
    END AS accion_prioritaria,
    CASE
        WHEN c.pct_rechazo_pedidos > 20                         THEN 'CRÍTICO: tasa de rechazo > 20 %'
        WHEN c.pct_rechazo_pedidos > 10                         THEN 'ATENCIÓN: tasa de rechazo > 10 %'
        WHEN c.ratio_costo_logistico_pct > 40                   THEN 'CRÍTICO: ratio costo logístico > 40 %'
        WHEN c.otif_valor IS NOT NULL AND c.otif_valor < 85     THEN 'ATENCION: OTIF menor a 85 %'
        WHEN COALESCE(c.crecimiento_pct, 0) < -30              THEN 'ALERTA: caída de venta > 30 % vs año base'
        WHEN c.cluster_dpo = 'Ganador'
         AND COALESCE(c.crecimiento_pct, 0) < 0               THEN 'AVISO: Ganador con caída YTD'
        ELSE NULL
    END AS alerta_operativa,
    CASE c.cluster_dpo
        WHEN 'Ganador'        THEN 1
        WHEN 'En crecimiento' THEN 2
        WHEN 'Básico'         THEN 3
        WHEN 'Ventas bajas'   THEN 4
        ELSE 5
    END AS prioridad_gestion
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente = c.cliente;
""")

# ── resumen_cluster_sucursal ──────────────────────────────────
cur.execute("""
CREATE VIEW resumen_cluster_sucursal AS
SELECT
    c.sucursal,
    c.cluster_dpo,
    COUNT(*)                                                                AS cantidad_clientes,
    ROUND(SUM(c.venta_ytd)::NUMERIC, 2)                                     AS venta_total_ytd,
    ROUND(SUM(c.hl_ytd)::NUMERIC, 4)                                        AS hl_total_ytd,
    ROUND(SUM(c.costo_logistico_total)::NUMERIC, 2)                         AS costo_logistico_total,
    ROUND(SUM(c.rechazos_ytd)::NUMERIC, 0)                                  AS rechazos_total,
    ROUND(SUM(c.pedidos_ytd)::NUMERIC, 0)                                   AS pedidos_total,
    ROUND(AVG(c.pct_rechazo_pedidos)::NUMERIC, 2)                           AS pct_rechazo_prom,
    ROUND(AVG(c.dropsize_bultos_ytd)::NUMERIC, 2)                           AS dropsize_prom,
    ROUND(AVG(c.ratio_costo_logistico_pct)::NUMERIC, 2)                     AS ratio_costo_prom,
    ROUND(AVG(COALESCE(c.crecimiento_pct, 0))::NUMERIC, 2)                  AS crecimiento_prom_pct,
    ROUND(AVG(c.rmd_valor)::NUMERIC, 2)                                     AS rmd_prom,
    ROUND(AVG(c.otif_valor)::NUMERIC, 2)                                    AS otif_prom,
    ROUND(AVG(c.nps_valor)::NUMERIC, 2)                                     AS nps_prom,
    ROUND(AVG(s.score_total)::NUMERIC, 2)                                   AS score_prom,
    ROUND((SUM(c.venta_ytd)
           / NULLIF(SUM(SUM(c.venta_ytd)) OVER (PARTITION BY c.sucursal), 0)
           * 100)::NUMERIC, 2)                                              AS pct_venta_en_sucursal
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente = c.cliente
GROUP BY c.sucursal, c.cluster_dpo;
""")

# ── resumen_cluster_localidad ─────────────────────────────────
cur.execute("""
CREATE VIEW resumen_cluster_localidad AS
SELECT
    COALESCE(NULLIF(c.localidad, ''), 'Sin localidad') AS localidad,
    c.sucursal,
    c.cluster_dpo,
    COUNT(*)                                                    AS cantidad_clientes,
    ROUND(SUM(c.venta_ytd)::NUMERIC, 2)                        AS venta_total_ytd,
    ROUND(SUM(c.hl_ytd)::NUMERIC, 4)                           AS hl_total_ytd,
    ROUND(SUM(c.costo_logistico_total)::NUMERIC, 2)            AS costo_logistico_total,
    ROUND(AVG(c.pct_rechazo_pedidos)::NUMERIC, 2)              AS pct_rechazo_prom,
    ROUND(AVG(c.dropsize_bultos_ytd)::NUMERIC, 2)              AS dropsize_prom,
    ROUND(AVG(COALESCE(c.crecimiento_pct, 0))::NUMERIC, 2)     AS crecimiento_prom_pct,
    ROUND(AVG(s.score_total)::NUMERIC, 2)                      AS score_prom
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente = c.cliente
GROUP BY c.localidad, c.sucursal, c.cluster_dpo;
""")

conn.commit()
cur.close()
conn.close()
print("Tablas e índices creados correctamente en Railway PostgreSQL")
