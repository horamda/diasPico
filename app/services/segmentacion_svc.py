"""
Segmentación logística-comercial DPO 2026 — Plan 4.2
Clasificación de clientes: Ganador / En crecimiento / Básico / Ventas bajas.
Score 0-100 + subcluster logístico + plan de servicio.

Fuente de datos: ventas_detalle (PostgreSQL Railway).
Tablas propias: seg_parametros, seg_clientes_atributos,
                seg_cliente_cluster_historico, seg_auditoria.
"""

from __future__ import annotations

import json
import time
from calendar import monthrange
from datetime import date, datetime
from threading import Lock
from typing import Any, Iterable

import psycopg2.extras

from app.database import pg_conn, pg_cursor
from app.services import cache_svc

_TABLES_READY = False
_TABLES_LOCK = Lock()
_PLAN_SOURCE_CACHE: str | None = None
_SCHEMA_VERSION = '20260531_segmentacion_dpo_cache_otif_v1'

_DDL_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS seg_schema_version (
    component      VARCHAR(80) PRIMARY KEY,
    version        VARCHAR(120) NOT NULL,
    applied_at     TIMESTAMP NOT NULL DEFAULT NOW()
);"""

# ─────────────────────────────────────────────────────────────
# DDL — tablas de soporte
# ─────────────────────────────────────────────────────────────
_DDL_PARAMETROS = """
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
    )
);"""

_DDL_ATRIBUTOS = """
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
);"""

_DDL_CLIENTE_GEO = """
CREATE TABLE IF NOT EXISTS cliente_geografia (
    cliente_id   VARCHAR(100) PRIMARY KEY,
    latitud      NUMERIC(12,8),
    longitud     NUMERIC(12,8),
    localidad    TEXT,
    sucursal     TEXT,
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
);"""

_DDL_CLIENTE_AUTOELEVADOR = """
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
);"""

_DDL_PERIODOS = """
CREATE TABLE IF NOT EXISTS seg_periodos_calculo (
    id                 BIGSERIAL PRIMARY KEY,
    empresa_id         VARCHAR(50) NOT NULL DEFAULT '1',
    periodo_anio       SMALLINT    NOT NULL,
    periodo_mes        SMALLINT    NOT NULL DEFAULT 0,
    fecha_desde        DATE        NOT NULL,
    fecha_hasta        DATE        NOT NULL,
    fecha_base_desde   DATE        NOT NULL,
    fecha_base_hasta   DATE        NOT NULL,
    activo             BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMP   NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_seg_periodo_mes CHECK (periodo_mes BETWEEN 0 AND 12),
    CONSTRAINT chk_seg_periodo_rango CHECK (
        fecha_desde <= fecha_hasta
        AND fecha_base_desde <= fecha_base_hasta
    )
);"""

_DDL_SCORE_PESOS = """
CREATE TABLE IF NOT EXISTS seg_score_pesos (
    variable        VARCHAR(50) PRIMARY KEY,
    dimension       VARCHAR(50) NOT NULL,
    peso            NUMERIC(8,4) NOT NULL,
    mayor_es_mejor  BOOLEAN NOT NULL DEFAULT TRUE,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);"""

_DDL_DPO_CACHE = """
CREATE TABLE IF NOT EXISTS seg_cliente_dpo_cache (
    cliente      VARCHAR(50) PRIMARY KEY,
    descripcion_cliente TEXT,
    sucursal     VARCHAR(50),
    sucursal_nombre TEXT,
    localidad    VARCHAR(100),
    autoelevador BOOLEAN DEFAULT FALSE,
    cluster_dpo  VARCHAR(50),
    subcluster_logistico VARCHAR(80),
    ingreso NUMERIC(18,2),
    ventas_anio_actual NUMERIC(18,2),
    ventas_anio_anterior NUMERIC(18,2),
    venta_anio_base NUMERIC(18,2),
    venta_base_mismo_per NUMERIC(18,2),
    venta_ytd    NUMERIC(18,2),
    hl_ytd       NUMERIC(18,4),
    bultos_ytd NUMERIC(18,4),
    pallets_ytd NUMERIC(18,4),
    up_ytd NUMERIC(18,4),
    pedidos_ytd INTEGER,
    dropsize_bultos_ytd NUMERIC(18,4),
    ticket_promedio_ytd NUMERIC(18,2),
    rechazos_ytd NUMERIC(18,4),
    pct_rechazo_pedidos NUMERIC(8,2),
    crecimiento_pct NUMERIC(10,2),
    nps_valor NUMERIC(6,2),
    rmd_valor NUMERIC(6,2),
    otif_valor NUMERIC(6,2),
    costo_entrega NUMERIC(18,2),
    costo_almacen NUMERIC(18,2),
    costo_logistico_total NUMERIC(18,2),
    margen_logistico_proxy NUMERIC(18,2),
    ratio_costo_logistico_pct NUMERIC(8,2),
    p25_ingresos NUMERIC(18,2),
    p50_ingresos NUMERIC(18,2),
    p75_ingresos NUMERIC(18,2),
    p25_crecimiento NUMERIC(10,2),
    p50_crecimiento NUMERIC(10,2),
    p75_crecimiento NUMERIC(10,2),
    umbral_venta_alta NUMERIC(18,2),
    umbral_venta_baja NUMERIC(18,2),
    umbral_crecimiento NUMERIC(10,2),
    score_total NUMERIC(6,2),
    dim_negocio NUMERIC(6,2),
    dim_productividad NUMERIC(6,2),
    dim_servicio NUMERIC(6,2),
    dim_rentabilidad NUMERIC(6,2),
    dim_geo NUMERIC(6,2),
    pts_venta NUMERIC(6,2),
    pts_hl NUMERIC(6,2),
    pts_crecimiento NUMERIC(6,2),
    pts_dropsize NUMERIC(6,2),
    pts_rechazos NUMERIC(6,2),
    pts_rmd NUMERIC(6,2),
    pts_nps NUMERIC(6,2),
    plan_servicio TEXT,
    accion_prioritaria TEXT,
    alerta_operativa TEXT,
    prioridad_gestion INTEGER,
    payload      JSONB NOT NULL,
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
);"""

_DDL_HISTORICO = """
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
    venta_base_mismo_periodo NUMERIC(18,2),
    venta_ytd               NUMERIC(18,2),
    bultos_ytd              NUMERIC(18,4),
    pallets_ytd             NUMERIC(18,4),
    up_ytd                  NUMERIC(18,4),
    hl_ytd                  NUMERIC(18,4),
    rechazos_ytd            NUMERIC(18,4),
    nps_valor               NUMERIC(6,2),
    rmd_valor               NUMERIC(6,2),
    otif_valor              NUMERIC(6,2),
    costo_entrega           NUMERIC(18,2),
    costo_almacen           NUMERIC(18,2),
    margen_logistico_proxy  NUMERIC(18,2),
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
);"""

_DDL_AUDITORIA = """
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
);"""

_DEFAULT_SCORE_PESOS = (
    ('venta', 'negocio', 15.0, True),
    ('hl', 'negocio', 10.0, True),
    ('crecimiento', 'negocio', 10.0, True),
    ('dropsize', 'productividad', 10.0, True),
    ('pallets_pedido', 'productividad', 5.0, True),
    ('autoelevador', 'productividad', 5.0, True),
    ('rechazos', 'servicio', 10.0, False),
    ('rmd', 'servicio', 5.0, True),
    ('nps', 'servicio', 5.0, True),
    ('ratio_costo', 'rentabilidad', 10.0, False),
    ('margen', 'rentabilidad', 5.0, True),
    ('frecuencia', 'geo', 7.0, True),
    ('localidad', 'geo', 2.0, True),
    ('sucursal', 'geo', 1.0, True),
)

# ─────────────────────────────────────────────────────────────
# DDL — vistas (CREATE OR REPLACE)
# Se importan desde el archivo SQL de referencia en producción;
# aquí se recrean en ensure_tables() para arranque automático.
# ─────────────────────────────────────────────────────────────
_VIEWS_SQL = r"""
DROP MATERIALIZED VIEW IF EXISTS mv_cliente_plan_servicio;

-- vw_cliente_metricas ----------------------------------------
DROP VIEW IF EXISTS vw_cliente_metricas CASCADE;
CREATE VIEW vw_cliente_metricas AS
WITH params AS (
    SELECT
        sp.costo_entrega_hl,
        sp.costo_almacen_hl,
        sp.anio_base,
        sp.anio_ytd,
        COALESCE(sp.mes_ytd_hasta, EXTRACT(MONTH FROM CURRENT_DATE)::INT) AS mes_ytd_hasta,
        COALESCE(pc.periodo_anio, sp.anio_ytd) AS periodo_anio,
        COALESCE(pc.periodo_mes, 0) AS periodo_mes,
        COALESCE(pc.fecha_desde, make_date(sp.anio_ytd, 1, 1)) AS fecha_desde,
        COALESCE(
            pc.fecha_hasta,
            (make_date(
                sp.anio_ytd,
                COALESCE(sp.mes_ytd_hasta, EXTRACT(MONTH FROM CURRENT_DATE)::INT),
                1
            ) + interval '1 month - 1 day')::date
        ) AS fecha_hasta,
        COALESCE(pc.fecha_base_desde, make_date(sp.anio_base, 1, 1)) AS fecha_base_desde,
        COALESCE(
            pc.fecha_base_hasta,
            (make_date(
                sp.anio_base,
                COALESCE(sp.mes_ytd_hasta, EXTRACT(MONTH FROM CURRENT_DATE)::INT),
                1
            ) + interval '1 month - 1 day')::date
        ) AS fecha_base_hasta
    FROM (
        SELECT *
        FROM seg_parametros
        WHERE activo
        ORDER BY (sucursal_id IS NULL) DESC, id DESC
        LIMIT 1
    ) sp
    LEFT JOIN LATERAL (
        SELECT *
        FROM seg_periodos_calculo
        WHERE activo AND empresa_id = sp.empresa_id
        ORDER BY id DESC
        LIMIT 1
    ) pc ON TRUE
),
base AS (
    SELECT NULLIF(TRIM(v.cliente),'') AS cliente,
           NULLIF(TRIM(v.descripcion_cliente),'') AS descripcion_cliente,
           COALESCE(NULLIF(TRIM(v.sucursal),''),'1') AS sucursal,
           v.fecha,
           COALESCE(v.importe_neto,0) AS importe,
           COALESCE(v.bultos,0) AS bultos,
           COALESCE(v.unidad_medida,0) AS hl,
           COALESCE(v.unidad_paquete,0) AS up,
           CASE WHEN COALESCE(a.bultos_por_pallet,0)>0
                THEN COALESCE(v.bultos,0)/a.bultos_por_pallet ELSE 0 END AS pallets,
           CASE WHEN COALESCE(rz.tomar,FALSE) AND (
                    COALESCE(v.bultos_rechazados,0)>0
                 OR COALESCE(v.unidad_medida_rechazado,0)>0
                 OR COALESCE(v.unidad_paquete_rechazado,0)>0)
                THEN 1 ELSE 0 END AS es_rechazo,
           CASE WHEN LOWER(TRIM(COALESCE(v.descripcion_ruta,''))) LIKE '%temp%'
                  OR LOWER(TRIM(COALESCE(v.descripcion_detallada_ruta,''))) LIKE '%temp%'
                THEN TRUE ELSE FALSE END AS es_ruta_temp_line,
           v.fecha::TEXT||'|'||NULLIF(TRIM(v.cliente),'') AS pedido_key
    FROM ventas_detalle v
    CROSS JOIN params p
    JOIN articulos a ON a.id_articulo=v.id_articulo
    LEFT JOIN LATERAL (
        SELECT tomar FROM rechazos r
        WHERE LOWER(TRIM(COALESCE(v.motivo_rechazo,'')))=r.motivo_key
           OR LOWER(TRIM(COALESCE(v.motivo_rechazo,''))) LIKE r.motivo_key||' %'
        ORDER BY LENGTH(r.motivo_key) DESC LIMIT 1
    ) rz ON TRUE
    WHERE v.fecha BETWEEN LEAST(make_date(p.anio_base, 1, 1), p.fecha_desde, p.fecha_base_desde)
                      AND GREATEST((make_date(p.anio_base + 1, 1, 1) - interval '1 day')::date, p.fecha_hasta, p.fecha_base_hasta)
      AND LOWER(TRIM(COALESCE(a.tipo_producto,'')))='mercaderia'
      AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%'
      AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%'
      AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%'
      AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%'
      AND NULLIF(TRIM(v.cliente),'') IS NOT NULL
),
ab AS (
    SELECT b.cliente,b.sucursal,MAX(b.descripcion_cliente) AS desc_cli,
           SUM(b.importe) AS venta,SUM(b.hl) AS hl,SUM(b.bultos) AS blt,
           SUM(b.pallets) AS pal,SUM(b.up) AS up,COUNT(DISTINCT b.pedido_key) AS ped
    FROM base b CROSS JOIN params p
    WHERE b.fecha >= make_date(p.anio_base, 1, 1)
      AND b.fecha < make_date(p.anio_base + 1, 1, 1)
    GROUP BY b.cliente,b.sucursal
),
ytd AS (
    SELECT b.cliente,b.sucursal,
           SUM(b.importe) AS venta,SUM(b.hl) AS hl,SUM(b.bultos) AS blt,
           SUM(b.pallets) AS pal,SUM(b.up) AS up,
           COUNT(DISTINCT b.pedido_key) AS ped,SUM(b.es_rechazo) AS rec,
           BOOL_OR(COALESCE(b.es_ruta_temp_line,FALSE)) AS es_ruta_temp
    FROM base b CROSS JOIN params p
    WHERE b.fecha BETWEEN p.fecha_desde AND p.fecha_hasta
    GROUP BY b.cliente,b.sucursal
),
bmp AS (
    SELECT b.cliente,b.sucursal,SUM(b.importe) AS venta,COUNT(DISTINCT b.pedido_key) AS ped
    FROM base b CROSS JOIN params p
    WHERE b.fecha BETWEEN p.fecha_base_desde AND p.fecha_base_hasta
    GROUP BY b.cliente,b.sucursal
)
SELECT COALESCE(y.cliente,ab.cliente) AS cliente,
       COALESCE(NULLIF(TRIM(cli.sucursal),''), COALESCE(y.sucursal,ab.sucursal)) AS sucursal,
       COALESCE(NULLIF(TRIM(suc.nombre),''), COALESCE(NULLIF(TRIM(cli.sucursal),''), COALESCE(y.sucursal,ab.sucursal))) AS sucursal_nombre,
       p.periodo_anio,
       p.periodo_mes,
       p.fecha_desde,
       p.fecha_hasta,
       p.fecha_base_desde,
       p.fecha_base_hasta,
       COALESCE(ab.desc_cli,y.cliente,'') AS descripcion_cliente,
       COALESCE(ab.venta,0) AS venta_anio_base,
       COALESCE(y.venta,0) AS venta_ytd,
       COALESCE(bmp.venta,0) AS venta_base_mismo_per,
       CASE WHEN COALESCE(bmp.venta,0)>0
            THEN ROUND(((COALESCE(y.venta,0)-bmp.venta)/bmp.venta*100)::NUMERIC,2)
            ELSE NULL END AS crecimiento_pct,
       COALESCE(ab.hl,0) AS hl_anio_base, COALESCE(y.hl,0) AS hl_ytd,
       COALESCE(ab.blt,0) AS bultos_anio_base, COALESCE(y.blt,0) AS bultos_ytd,
       COALESCE(ab.pal,0) AS pallets_anio_base, COALESCE(y.pal,0) AS pallets_ytd,
       COALESCE(ab.up,0) AS up_anio_base, COALESCE(y.up,0) AS up_ytd,
       COALESCE(ab.ped,0) AS pedidos_anio_base, COALESCE(y.ped,0) AS pedidos_ytd,
       CASE WHEN COALESCE(y.ped,0)>0 THEN ROUND((y.blt/y.ped)::NUMERIC,2) ELSE 0 END AS dropsize_bultos_ytd,
       CASE WHEN COALESCE(y.ped,0)>0 THEN ROUND((y.hl /y.ped)::NUMERIC,4) ELSE 0 END AS dropsize_hl_ytd,
       CASE WHEN COALESCE(y.ped,0)>0 THEN ROUND((y.venta/y.ped)::NUMERIC,2) ELSE 0 END AS ticket_promedio_ytd,
       COALESCE(y.rec,0) AS rechazos_ytd,
       CASE WHEN COALESCE(y.ped,0)>0
            THEN ROUND((COALESCE(y.rec,0)::NUMERIC/y.ped*100),2) ELSE 0 END AS pct_rechazo_pedidos,
       COALESCE(NULLIF(TRIM(cli.localidad),''), NULLIF(TRIM(ca.localidad),''), '') AS localidad,
       COALESCE(cae.autoelevador,ca.autoelevador,FALSE) AS autoelevador,
       COALESCE(y.es_ruta_temp,FALSE) AS es_ruta_temp,
       CASE WHEN COALESCE(y.venta,0)<=0 AND COALESCE(bmp.venta,0)>0 THEN TRUE ELSE FALSE END AS es_inactivo,
       ca.nps_valor, ca.rmd_valor, ca.otif_valor,
       ROUND((COALESCE(y.hl,0)*p.costo_entrega_hl)::NUMERIC,2) AS costo_entrega,
       ROUND((COALESCE(y.hl,0)*p.costo_almacen_hl)::NUMERIC,2) AS costo_almacen,
       ROUND((COALESCE(y.hl,0)*(p.costo_entrega_hl+p.costo_almacen_hl))::NUMERIC,2) AS costo_logistico_total,
       ROUND((COALESCE(y.venta,0)-COALESCE(y.hl,0)*(p.costo_entrega_hl+p.costo_almacen_hl))::NUMERIC,2) AS margen_logistico_proxy,
       CASE WHEN COALESCE(y.venta,0)>0
            THEN ROUND((COALESCE(y.hl,0)*(p.costo_entrega_hl+p.costo_almacen_hl)/y.venta*100)::NUMERIC,2)
            ELSE 0 END AS ratio_costo_logistico_pct
FROM ytd y
FULL OUTER JOIN ab ON ab.cliente=y.cliente AND ab.sucursal=y.sucursal
LEFT JOIN bmp ON bmp.cliente=COALESCE(y.cliente,ab.cliente)
             AND bmp.sucursal=COALESCE(y.sucursal,ab.sucursal)
LEFT JOIN seg_clientes_atributos ca ON ca.cliente=COALESCE(y.cliente,ab.cliente)
LEFT JOIN cliente_autoelevador cae ON cae.is_cliente=COALESCE(y.cliente,ab.cliente)
LEFT JOIN clientes cli ON cli.cliente=COALESCE(y.cliente,ab.cliente)
                      AND COALESCE(NULLIF(TRIM(cli.sucursal),''), COALESCE(y.sucursal,ab.sucursal))=COALESCE(y.sucursal,ab.sucursal)
LEFT JOIN sucursales suc ON suc.id=COALESCE(NULLIF(TRIM(cli.sucursal),''), COALESCE(y.sucursal,ab.sucursal))
CROSS JOIN params p;

-- vw_clientes_activos_dpo -----------------------------------
DROP VIEW IF EXISTS vw_clientes_activos_dpo CASCADE;
CREATE VIEW vw_clientes_activos_dpo AS
WITH ruta AS (
    SELECT DISTINCT ON (v.cliente, v.sucursal)
           v.cliente,
           COALESCE(NULLIF(TRIM(v.sucursal),''),'1') AS sucursal,
           NULLIF(TRIM(v.ruta),'') AS ruta_venta,
           COALESCE(NULLIF(TRIM(v.descripcion_ruta),''), NULLIF(TRIM(v.descripcion_detallada_ruta),''), '') AS ruta_venta_descripcion
    FROM ventas_detalle v
    WHERE NULLIF(TRIM(v.cliente),'') IS NOT NULL
    ORDER BY v.cliente, v.sucursal, v.fecha DESC, v.id DESC
),
base AS (
    SELECT
        m.cliente AS cliente_id,
        COALESCE(NULLIF(TRIM(c.nombre_fantasia),''), NULLIF(TRIM(c.razon_social),''), m.descripcion_cliente, m.cliente) AS cliente_nombre,
        m.sucursal,
        COALESCE(NULLIF(TRIM(s.nombre),''), m.sucursal) AS sucursal_nombre,
        COALESCE(NULLIF(TRIM(c.localidad),''), NULLIF(TRIM(m.localidad),''), '') AS localidad,
        r.ruta_venta,
        COALESCE(NULLIF(TRIM(c.fuerza_venta_1_dias_visita),''), '') AS fuerza_venta_1_dias_visita,
        CASE
            WHEN NOT COALESCE(c.activo_maestro, TRUE) THEN 'Inactivo'
            WHEN COALESCE(LOWER(TRIM(c.anulado)), '') NOT IN ('no','n','0','false','f') THEN 'Inactivo'
            WHEN NULLIF(TRIM(COALESCE(c.fuerza_venta_1_dias_visita, '')), '') IS NULL THEN 'Inactivo'
            WHEN COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') = 'dom' THEN 'Inactivo'
            WHEN COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') LIKE '%oficina%' THEN 'Inactivo'
            ELSE 'Activo'
        END AS estado_cliente,
        CASE
            WHEN COALESCE(LOWER(TRIM(c.anulado)), 'no') IN ('si','s','1','true','t','y','yes') THEN 'Si'
            ELSE 'No'
        END AS estado_anulado,
        CASE
            WHEN NOT COALESCE(c.activo_maestro, TRUE) THEN FALSE
            WHEN COALESCE(LOWER(TRIM(c.anulado)), '') NOT IN ('no','n','0','false','f') THEN FALSE
            WHEN NULLIF(TRIM(COALESCE(c.fuerza_venta_1_dias_visita, '')), '') IS NULL THEN FALSE
            WHEN COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') = 'dom' THEN FALSE
            WHEN COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') LIKE '%oficina%' THEN FALSE
            ELSE TRUE
        END AS activo,
        COALESCE(r.ruta_venta_descripcion, '') AS ruta_venta_descripcion
    FROM vw_cliente_metricas m
    LEFT JOIN clientes c
           ON c.cliente = m.cliente
          AND COALESCE(NULLIF(TRIM(c.sucursal),''), m.sucursal) = m.sucursal
    LEFT JOIN sucursales s
           ON s.id = m.sucursal
    LEFT JOIN ruta r
           ON r.cliente = m.cliente
          AND r.sucursal = m.sucursal
)
SELECT
    cliente_id,
    cliente_nombre,
    sucursal,
    sucursal_nombre,
    localidad,
    ruta_venta,
    fuerza_venta_1_dias_visita,
    estado_cliente,
    estado_anulado,
    activo
FROM base
WHERE activo
  AND estado_anulado = 'No'
  AND ruta_venta_descripcion NOT ILIKE '%temp%';


-- vw_cliente_cluster_dpo ------------------------------------
DROP VIEW IF EXISTS vw_cliente_cluster_dpo CASCADE;
CREATE VIEW vw_cliente_cluster_dpo AS
WITH m AS (
    SELECT m.*
    FROM vw_cliente_metricas m
    JOIN vw_clientes_activos_dpo a
      ON a.cliente_id = m.cliente
     AND a.sucursal = m.sucursal
    WHERE m.venta_ytd > 0 OR m.venta_anio_base > 0
),
cfg AS (
    SELECT
        COALESCE(percentil_alta, 0.75) AS percentil_alta,
        COALESCE(percentil_baja, 0.25) AS percentil_baja
    FROM seg_parametros
    WHERE activo
    ORDER BY (sucursal_id IS NULL) DESC, id DESC
    LIMIT 1
),
u AS (
    SELECT
        percentile_cont((SELECT percentil_baja FROM cfg)) WITHIN GROUP (ORDER BY venta_ytd) AS p25_ingresos,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY venta_ytd) AS p50_ingresos,
        percentile_cont((SELECT percentil_alta FROM cfg)) WITHIN GROUP (ORDER BY venta_ytd) AS p75_ingresos,
        percentile_cont(0.25) WITHIN GROUP (ORDER BY COALESCE(crecimiento_pct,0)) AS p25_crecimiento,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY COALESCE(crecimiento_pct,0)) AS p50_crecimiento,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY COALESCE(crecimiento_pct,0)) AS p75_crecimiento,
        percentile_cont(0.25) WITHIN GROUP (ORDER BY dropsize_bultos_ytd) AS p25ds,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY dropsize_bultos_ytd) AS p50ds,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY ratio_costo_logistico_pct) AS p75rc
    FROM m
)
SELECT m.*,
       m.venta_ytd AS ingreso,
       m.venta_ytd AS ventas_anio_actual,
       m.venta_base_mismo_per AS ventas_anio_anterior,
       u.p25_ingresos,
       u.p50_ingresos,
       u.p75_ingresos,
       u.p25_crecimiento,
       u.p50_crecimiento,
       u.p75_crecimiento,
       u.p75_ingresos AS umbral_venta_alta,
       u.p25_ingresos AS umbral_venta_baja,
       u.p50_crecimiento AS umbral_crecimiento,
       CASE
            WHEN m.venta_ytd >= u.p75_ingresos
             AND COALESCE(m.crecimiento_pct,0) >= u.p50_crecimiento
                THEN 'Ganador'
            WHEN m.venta_ytd < u.p75_ingresos
             AND COALESCE(m.crecimiento_pct,0) >= u.p75_crecimiento
                THEN 'En crecimiento'
            WHEN m.venta_ytd <= u.p25_ingresos
             AND COALESCE(m.crecimiento_pct,0) <= u.p25_crecimiento
                THEN 'Ventas bajas'
            ELSE 'Basico'
       END AS cluster_dpo,
       CASE WHEN COALESCE(m.ratio_costo_logistico_pct,0)>u.p75rc AND m.dropsize_bultos_ytd<u.p25ds THEN 'Caro de servir'
            WHEN COALESCE(m.pct_rechazo_pedidos,0)>20 THEN 'Complejo'
            WHEN COALESCE(m.crecimiento_pct,0)>15 AND COALESCE(m.pct_rechazo_pedidos,0)<5 THEN 'Alto potencial'
            WHEN COALESCE(m.ratio_costo_logistico_pct,0)<=20 AND m.dropsize_bultos_ytd>=u.p50ds THEN 'Eficiente'
            WHEN COALESCE(m.ratio_costo_logistico_pct,0)<=25 AND COALESCE(m.margen_logistico_proxy,0)>0 THEN 'Rentable'
            ELSE 'Estandar' END AS subcluster_logistico
FROM m CROSS JOIN u;

-- vw_cliente_score ------------------------------------------
DROP VIEW IF EXISTS vw_cliente_score CASCADE;
CREATE VIEW vw_cliente_score AS
WITH m AS (
    SELECT m.*
    FROM vw_cliente_metricas m
    JOIN vw_clientes_activos_dpo a
      ON a.cliente_id = m.cliente
     AND a.sucursal = m.sucursal
    WHERE m.venta_ytd>0 OR m.venta_anio_base>0
),
md AS (SELECT COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY rmd_valor),5) AS mrmd,
              COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY nps_valor),5) AS mnps,
              COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY crecimiento_pct),0) AS mcrec FROM m),
w AS (
    SELECT
        COALESCE(MAX(peso) FILTER (WHERE variable='venta' AND activo),15) AS venta,
        COALESCE(MAX(peso) FILTER (WHERE variable='hl' AND activo),10) AS hl,
        COALESCE(MAX(peso) FILTER (WHERE variable='crecimiento' AND activo),10) AS crecimiento,
        COALESCE(MAX(peso) FILTER (WHERE variable='dropsize' AND activo),10) AS dropsize,
        COALESCE(MAX(peso) FILTER (WHERE variable='pallets_pedido' AND activo),5) AS pallets_pedido,
        COALESCE(MAX(peso) FILTER (WHERE variable='autoelevador' AND activo),5) AS autoelevador,
        COALESCE(MAX(peso) FILTER (WHERE variable='rechazos' AND activo),10) AS rechazos,
        COALESCE(MAX(peso) FILTER (WHERE variable='rmd' AND activo),5) AS rmd,
        COALESCE(MAX(peso) FILTER (WHERE variable='nps' AND activo),5) AS nps,
        COALESCE(MAX(peso) FILTER (WHERE variable='ratio_costo' AND activo),10) AS ratio_costo,
        COALESCE(MAX(peso) FILTER (WHERE variable='margen' AND activo),5) AS margen,
        COALESCE(MAX(peso) FILTER (WHERE variable='frecuencia' AND activo),7) AS frecuencia,
        COALESCE(MAX(peso) FILTER (WHERE variable='localidad' AND activo),2) AS localidad,
        COALESCE(MAX(peso) FILTER (WHERE variable='sucursal' AND activo),1) AS sucursal
    FROM seg_score_pesos
),
cl AS (
    SELECT m.*,
           GREATEST(-100,LEAST(300,COALESCE(m.crecimiento_pct,md.mcrec))) AS cc,
           COALESCE(m.rmd_valor,md.mrmd) AS ri, COALESCE(m.nps_valor,md.mnps) AS ni,
           CASE WHEN m.pedidos_ytd>0 THEN m.pallets_ytd/m.pedidos_ytd ELSE 0 END AS ppp,
           GREATEST(0,m.ratio_costo_logistico_pct) AS rcp
    FROM m CROSS JOIN md
),
rn AS (
    SELECT c.*,
           MIN(venta_ytd) OVER() AS mnv,MAX(venta_ytd) OVER() AS mxv,
           MIN(hl_ytd)    OVER() AS mnh,MAX(hl_ytd)    OVER() AS mxh,
           MIN(cc)        OVER() AS mnc,MAX(cc)        OVER() AS mxc,
           MIN(dropsize_bultos_ytd) OVER() AS mnd,MAX(dropsize_bultos_ytd) OVER() AS mxd,
           MIN(ppp)       OVER() AS mnp,MAX(ppp)       OVER() AS mxp,
           MIN(pct_rechazo_pedidos) OVER() AS mnr,MAX(pct_rechazo_pedidos) OVER() AS mxr,
           MIN(ri)        OVER() AS mnrmd,MAX(ri) OVER() AS mxrmd,
           MIN(ni)        OVER() AS mnnps,MAX(ni) OVER() AS mxnps,
           MIN(rcp)       OVER() AS mnrc,MAX(rcp)       OVER() AS mxrc,
           MIN(margen_logistico_proxy) OVER() AS mnmg,MAX(margen_logistico_proxy) OVER() AS mxmg,
           MIN(pedidos_ytd) OVER() AS mnped,MAX(pedidos_ytd) OVER() AS mxped
    FROM cl c
),
nr AS (
    SELECT r.*,
           CASE WHEN mxv>mnv THEN (venta_ytd-mnv)/(mxv-mnv) ELSE 0.5 END AS nv,
           CASE WHEN mxh>mnh THEN (hl_ytd-mnh)/(mxh-mnh)     ELSE 0.5 END AS nh,
           CASE WHEN mxc>mnc THEN (cc-mnc)/(mxc-mnc)          ELSE 0.5 END AS nc,
           CASE WHEN mxd>mnd THEN (dropsize_bultos_ytd-mnd)/(mxd-mnd) ELSE 0.5 END AS nd,
           CASE WHEN mxp>mnp THEN (ppp-mnp)/(mxp-mnp)         ELSE 0.5 END AS np,
           CASE WHEN mxr>mnr THEN 1-(pct_rechazo_pedidos-mnr)/(mxr-mnr) ELSE 0.5 END AS nr_,
           CASE WHEN mxrmd>mnrmd THEN (ri-mnrmd)/(mxrmd-mnrmd) ELSE 0.5 END AS nrmd,
           CASE WHEN mxnps>mnnps THEN (ni-mnnps)/(mxnps-mnnps) ELSE 0.5 END AS nnps,
           CASE WHEN mxrc>mnrc  THEN 1-(rcp-mnrc)/(mxrc-mnrc)  ELSE 0.5 END AS nrc,
           CASE WHEN mxmg>mnmg  THEN (margen_logistico_proxy-mnmg)/(mxmg-mnmg) ELSE 0.5 END AS nmg,
           CASE WHEN mxped>mnped THEN (pedidos_ytd-mnped)/(mxped-mnped) ELSE 0.5 END AS nped
    FROM rn r
)
SELECT n.cliente,n.descripcion_cliente,n.sucursal,n.sucursal_nombre,n.localidad,
       ROUND((n.nv*w.venta+n.nh*w.hl+n.nc*w.crecimiento)::NUMERIC,2) AS dim_negocio,
       ROUND((n.nd*w.dropsize+n.np*w.pallets_pedido+(CASE WHEN n.autoelevador THEN w.autoelevador ELSE 0.0 END))::NUMERIC,2) AS dim_productividad,
       ROUND((n.nr_*w.rechazos+n.nrmd*w.rmd+n.nnps*w.nps)::NUMERIC,2) AS dim_servicio,
       ROUND((n.nrc*w.ratio_costo+n.nmg*w.margen)::NUMERIC,2) AS dim_rentabilidad,
       ROUND((n.nped*w.frecuencia+(CASE WHEN NULLIF(n.localidad,'') IS NOT NULL THEN w.localidad ELSE 0.0 END)
             +(CASE WHEN NULLIF(n.sucursal,'') IS NOT NULL THEN w.sucursal ELSE 0.0 END))::NUMERIC,2) AS dim_geo,
       ROUND((n.nv*w.venta)::NUMERIC,2) AS pts_venta,
       ROUND((n.nh*w.hl)::NUMERIC,2) AS pts_hl,
       ROUND((n.nc*w.crecimiento)::NUMERIC,2) AS pts_crecimiento,
       ROUND((n.nd*w.dropsize)::NUMERIC,2) AS pts_dropsize,
       ROUND((n.np*w.pallets_pedido)::NUMERIC,2)  AS pts_pallets_ped,
       ROUND((CASE WHEN n.autoelevador THEN w.autoelevador ELSE 0.0 END)::NUMERIC,2) AS pts_autoelevador,
       ROUND((n.nr_*w.rechazos)::NUMERIC,2) AS pts_rechazos,
       ROUND((n.nrmd*w.rmd)::NUMERIC,2) AS pts_rmd,
       ROUND((n.nnps*w.nps)::NUMERIC,2) AS pts_nps,
       ROUND((n.nrc*w.ratio_costo)::NUMERIC,2) AS pts_ratio_costo,
       ROUND((n.nmg*w.margen)::NUMERIC,2)  AS pts_margen,
       ROUND((n.nped*w.frecuencia)::NUMERIC,2) AS pts_frecuencia,
       ROUND((n.nv*w.venta+n.nh*w.hl+n.nc*w.crecimiento+n.nd*w.dropsize+n.np*w.pallets_pedido
             +(CASE WHEN n.autoelevador THEN w.autoelevador ELSE 0.0 END)
             +n.nr_*w.rechazos+n.nrmd*w.rmd+n.nnps*w.nps+n.nrc*w.ratio_costo+n.nmg*w.margen+n.nped*w.frecuencia
             +(CASE WHEN NULLIF(n.localidad,'') IS NOT NULL THEN w.localidad ELSE 0.0 END)
             +(CASE WHEN NULLIF(n.sucursal,'') IS NOT NULL THEN w.sucursal ELSE 0.0 END))::NUMERIC,2) AS score_total
FROM nr n CROSS JOIN w;


-- vw_cliente_plan_servicio -----------------------------------
DROP VIEW IF EXISTS vw_cliente_plan_servicio CASCADE;
CREATE VIEW vw_cliente_plan_servicio AS
SELECT c.cliente,c.descripcion_cliente,c.sucursal,c.sucursal_nombre,c.localidad,c.autoelevador,
       c.cluster_dpo,c.subcluster_logistico,
       c.ingreso,c.ventas_anio_actual,c.ventas_anio_anterior,
       c.venta_anio_base,c.venta_base_mismo_per,
       s.score_total,s.dim_negocio,s.dim_productividad,s.dim_servicio,s.dim_rentabilidad,s.dim_geo,
       s.pts_venta,s.pts_hl,s.pts_crecimiento,s.pts_dropsize,s.pts_rechazos,s.pts_rmd,s.pts_nps,
       c.venta_ytd,c.crecimiento_pct,
       c.hl_ytd,c.bultos_ytd,c.pallets_ytd,c.up_ytd,c.pedidos_ytd,
       c.dropsize_bultos_ytd,c.ticket_promedio_ytd,
       c.rechazos_ytd,c.pct_rechazo_pedidos,
       c.nps_valor,c.rmd_valor,c.otif_valor,
       c.costo_entrega,c.costo_almacen,c.costo_logistico_total,
       c.margen_logistico_proxy,c.ratio_costo_logistico_pct,
       c.p25_ingresos,c.p50_ingresos,c.p75_ingresos,
       c.p25_crecimiento,c.p50_crecimiento,c.p75_crecimiento,
       c.umbral_venta_alta,c.umbral_venta_baja,c.umbral_crecimiento,
       CASE c.cluster_dpo
           WHEN 'Ganador'        THEN 'Prioridad de inventario - mejor OTIF - ventanas horarias precisas - evaluar flex/express'
           WHEN 'En crecimiento' THEN 'Seguimiento comercial-logistico - mejorar frecuencia - acompanar experiencia'
           WHEN 'Basico'         THEN 'Servicio estandar - costo controlado - frecuencia optima'
           WHEN 'Ventas bajas'   THEN 'Optimizar frecuencia - consolidar pedidos - revisar rentabilidad'
           ELSE 'Sin clasificacion' END AS plan_servicio,
       CASE c.subcluster_logistico
           WHEN 'Caro de servir' THEN 'Revisar costo logistico - negociar drop size minimo - evaluar consolidacion'
           WHEN 'Alto potencial' THEN 'Fortalecer relacion - asignar vendedor referente - mejorar OTIF'
           WHEN 'Eficiente'      THEN 'Mantener operacion - compartir benchmarks positivos'
           WHEN 'Rentable'       THEN 'Proteger cuenta - renovar acuerdo - ofrecer beneficios premium'
           WHEN 'Complejo'       THEN 'Plan mejora de rechazo - visita tecnica - acuerdo de entrega'
           ELSE                       'Monitorear indicadores mensualmente' END AS accion_prioritaria,
       CASE WHEN c.pct_rechazo_pedidos>20 THEN 'CRITICO: tasa de rechazo > 20 %'
            WHEN c.pct_rechazo_pedidos>10 THEN 'ATENCION: tasa de rechazo > 10 %'
            WHEN c.otif_valor IS NOT NULL AND c.otif_valor<85 THEN 'ATENCION: OTIF menor a 85 %'
            WHEN c.ratio_costo_logistico_pct>40 THEN 'CRITICO: ratio costo logistico > 40 %'
            WHEN COALESCE(c.crecimiento_pct,0)<-30 THEN 'ALERTA: caida de venta > 30 %'
            WHEN c.cluster_dpo='Ganador' AND COALESCE(c.crecimiento_pct,0)<0 THEN 'AVISO: Ganador con caida YTD'
            ELSE NULL END AS alerta_operativa,
       CASE c.cluster_dpo WHEN 'Ganador' THEN 1 WHEN 'En crecimiento' THEN 2
                          WHEN 'Basico' THEN 3 WHEN 'Ventas bajas' THEN 4
                          ELSE 7 END AS prioridad_gestion
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente=c.cliente AND s.sucursal=c.sucursal;

-- resumen_cluster_sucursal -----------------------------------
DROP VIEW IF EXISTS resumen_cluster_sucursal CASCADE;
CREATE VIEW resumen_cluster_sucursal AS
SELECT c.sucursal, c.cluster_dpo,
       COUNT(*) AS cantidad_clientes,
       ROUND(SUM(c.venta_ytd)::NUMERIC,2) AS venta_total_ytd,
       ROUND(SUM(c.hl_ytd)::NUMERIC,4) AS hl_total_ytd,
       ROUND(SUM(c.costo_logistico_total)::NUMERIC,2) AS costo_logistico_total,
       ROUND(SUM(c.rechazos_ytd)::NUMERIC,0) AS rechazos_total,
       ROUND(SUM(c.pedidos_ytd)::NUMERIC,0) AS pedidos_total,
       ROUND(AVG(c.pct_rechazo_pedidos)::NUMERIC,2) AS pct_rechazo_prom,
       ROUND(AVG(c.dropsize_bultos_ytd)::NUMERIC,2) AS dropsize_prom,
       ROUND(AVG(c.ratio_costo_logistico_pct)::NUMERIC,2) AS ratio_costo_prom,
       ROUND(AVG(COALESCE(c.crecimiento_pct,0))::NUMERIC,2) AS crecimiento_prom_pct,
       ROUND(AVG(c.rmd_valor)::NUMERIC,2) AS rmd_prom,
       ROUND(AVG(c.otif_valor)::NUMERIC,2) AS otif_prom,
       ROUND(AVG(c.nps_valor)::NUMERIC,2) AS nps_prom,
       ROUND(AVG(s.score_total)::NUMERIC,2) AS score_prom,
       ROUND((SUM(c.venta_ytd)/NULLIF(SUM(SUM(c.venta_ytd)) OVER (PARTITION BY c.sucursal),0)*100)::NUMERIC,2)
           AS pct_venta_en_sucursal
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente=c.cliente AND s.sucursal=c.sucursal
GROUP BY c.sucursal,c.cluster_dpo;


-- resumen_cluster_localidad ----------------------------------
DROP VIEW IF EXISTS resumen_cluster_localidad CASCADE;
CREATE VIEW resumen_cluster_localidad AS
SELECT COALESCE(NULLIF(c.localidad,''),'Sin localidad') AS localidad,
       c.sucursal, c.cluster_dpo,
       COUNT(*) AS cantidad_clientes,
       ROUND(SUM(c.venta_ytd)::NUMERIC,2) AS venta_total_ytd,
       ROUND(SUM(c.hl_ytd)::NUMERIC,4) AS hl_total_ytd,
       ROUND(SUM(c.costo_logistico_total)::NUMERIC,2) AS costo_logistico_total,
       ROUND(AVG(c.pct_rechazo_pedidos)::NUMERIC,2) AS pct_rechazo_prom,
       ROUND(AVG(c.dropsize_bultos_ytd)::NUMERIC,2) AS dropsize_prom,
       ROUND(AVG(COALESCE(c.crecimiento_pct,0))::NUMERIC,2) AS crecimiento_prom_pct,
       ROUND(AVG(c.otif_valor)::NUMERIC,2) AS otif_prom,
       ROUND(AVG(c.rmd_valor)::NUMERIC,2) AS rmd_prom,
       ROUND(AVG(c.nps_valor)::NUMERIC,2) AS nps_prom,
       ROUND(AVG(s.score_total)::NUMERIC,2) AS score_prom
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente=c.cliente AND s.sucursal=c.sucursal
GROUP BY c.localidad,c.sucursal,c.cluster_dpo;

-- vw_cliente_autoelevador -----------------------------------
DROP VIEW IF EXISTS vw_cliente_autoelevador CASCADE;
CREATE VIEW vw_cliente_autoelevador AS
SELECT
    m.cliente AS cliente_id,
    m.descripcion_cliente AS cliente_nombre,
    m.sucursal,
    m.localidad,
    m.venta_ytd AS venta,
    m.hl_ytd AS hl,
    m.pallets_ytd AS pallets,
    m.bultos_ytd AS bultos,
    m.pedidos_ytd AS pedidos,
    COALESCE(ca.autoelevador, sa.autoelevador, m.autoelevador, FALSE) AS tiene_autoelevador,
    CASE
        WHEN COALESCE(ca.autoelevador, sa.autoelevador, m.autoelevador, FALSE) THEN 1
        ELSE 3
    END AS factor_operativo,
    CASE
        WHEN ca.is_cliente IS NOT NULL THEN 'importacion_externa'
        WHEN sa.cliente IS NOT NULL THEN 'atributo_segmentacion'
        ELSE 'sin_dato'
    END AS fuente_autoelevador
FROM vw_cliente_metricas m
JOIN vw_clientes_activos_dpo a
  ON a.cliente_id = m.cliente
 AND a.sucursal = m.sucursal
LEFT JOIN cliente_autoelevador ca
  ON ca.is_cliente = m.cliente
LEFT JOIN seg_clientes_atributos sa
  ON sa.cliente = m.cliente
WHERE m.venta_ytd > 0 OR m.venta_anio_base > 0;

-- vw_cliente_costo_operativo --------------------------------
DROP VIEW IF EXISTS vw_cliente_costo_operativo CASCADE;
CREATE VIEW vw_cliente_costo_operativo AS
SELECT
    m.cliente AS cliente_id,
    m.descripcion_cliente AS cliente_nombre,
    m.sucursal,
    m.localidad,
    a.tiene_autoelevador,
    a.factor_operativo,
    m.venta_ytd AS venta,
    m.hl_ytd AS hl,
    m.pedidos_ytd AS pedidos,
    m.costo_entrega,
    m.costo_almacen,
    ROUND((m.costo_entrega * a.factor_operativo)::NUMERIC, 2) AS costo_servir_ajustado,
    ROUND((m.costo_entrega * a.factor_operativo + m.costo_almacen)::NUMERIC, 2) AS costo_logistico_ajustado_total,
    ROUND((m.venta_ytd - (m.costo_entrega * a.factor_operativo + m.costo_almacen))::NUMERIC, 2) AS margen_logistico_ajustado,
    CASE
        WHEN COALESCE(m.venta_ytd, 0) > 0 THEN
            ROUND((((m.costo_entrega * a.factor_operativo + m.costo_almacen) / m.venta_ytd) * 100)::NUMERIC, 2)
        ELSE 0
    END AS ratio_costo_logistico_ajustado_pct,
    ROUND((m.costo_entrega * 3)::NUMERIC, 2) AS costo_servir_sin_autoelevador_escenario,
    ROUND((m.costo_entrega * 1)::NUMERIC, 2) AS costo_servir_con_autoelevador_escenario,
    CASE
        WHEN a.tiene_autoelevador THEN ROUND((m.costo_entrega * 2)::NUMERIC, 2)
        ELSE 0
    END AS ahorro_actual_vs_sin_autoelevador,
    CASE
        WHEN NOT a.tiene_autoelevador THEN ROUND((m.costo_entrega * 2)::NUMERIC, 2)
        ELSE 0
    END AS sobrecosto_actual_vs_con_autoelevador,
    COALESCE(s.score_total, 0) AS score_total_base,
    CASE WHEN a.tiene_autoelevador THEN 15 ELSE 0 END AS score_bonus_autoelevador,
    LEAST(100, ROUND((COALESCE(s.score_total, 0) + CASE WHEN a.tiene_autoelevador THEN 15 ELSE 0 END)::NUMERIC, 2))
        AS score_total_operativo
FROM vw_cliente_metricas m
JOIN vw_cliente_autoelevador a
  ON a.cliente_id = m.cliente
 AND a.sucursal = m.sucursal
LEFT JOIN vw_cliente_score s
  ON s.cliente = m.cliente
 AND s.sucursal = m.sucursal
WHERE m.venta_ytd > 0 OR m.venta_anio_base > 0;

-- vw_cliente_eficiencia_operativa ---------------------------
DROP VIEW IF EXISTS vw_cliente_eficiencia_operativa CASCADE;
CREATE VIEW vw_cliente_eficiencia_operativa AS
SELECT
    c.cliente_id,
    c.cliente_nombre,
    c.sucursal,
    c.localidad,
    c.tiene_autoelevador,
    c.factor_operativo,
    c.hl,
    c.pedidos,
    GREATEST(COALESCE(c.pedidos, 0), 0) AS camiones_estimados,
    GREATEST(COALESCE(c.pedidos, 0), 0) AS choferes_equivalentes,
    CASE
        WHEN c.tiene_autoelevador THEN 0
        ELSE GREATEST(COALESCE(c.pedidos, 0), 0) * 2
    END AS acompanantes_equivalentes,
    (GREATEST(COALESCE(c.pedidos, 0), 0) * c.factor_operativo) AS dotacion_operativa_total,
    CASE
        WHEN (GREATEST(COALESCE(c.pedidos, 0), 0) * c.factor_operativo) > 0 THEN
            ROUND((c.hl / NULLIF((GREATEST(COALESCE(c.pedidos, 0), 0) * c.factor_operativo), 0))::NUMERIC, 6)
        ELSE 0
    END AS indice_eficiencia_operativa
FROM vw_cliente_costo_operativo c;

-- vw_cliente_cluster_logistico ------------------------------
DROP VIEW IF EXISTS vw_cliente_cluster_logistico CASCADE;
CREATE VIEW vw_cliente_cluster_logistico AS
WITH base AS (
    SELECT
        d.cliente,
        d.descripcion_cliente,
        d.sucursal,
        d.localidad,
        d.cluster_dpo,
        d.subcluster_logistico,
        d.venta_ytd,
        d.hl_ytd,
        d.pedidos_ytd,
        d.dropsize_bultos_ytd,
        d.pct_rechazo_pedidos,
        a.tiene_autoelevador,
        a.factor_operativo,
        c.costo_servir_ajustado,
        c.costo_logistico_ajustado_total,
        c.ratio_costo_logistico_ajustado_pct,
        c.score_total_operativo,
        e.indice_eficiencia_operativa
    FROM vw_cliente_cluster_dpo d
    JOIN vw_cliente_autoelevador a
      ON a.cliente_id = d.cliente
     AND a.sucursal = d.sucursal
    JOIN vw_cliente_costo_operativo c
      ON c.cliente_id = d.cliente
     AND c.sucursal = d.sucursal
    JOIN vw_cliente_eficiencia_operativa e
      ON e.cliente_id = d.cliente
     AND e.sucursal = d.sucursal
),
u AS (
    SELECT
        percentile_cont(0.70) WITHIN GROUP (ORDER BY venta_ytd) AS p70_venta,
        percentile_cont(0.70) WITHIN GROUP (ORDER BY hl_ytd) AS p70_hl,
        percentile_cont(0.70) WITHIN GROUP (ORDER BY pedidos_ytd) AS p70_pedidos,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY ratio_costo_logistico_ajustado_pct) AS p75_ratio_costo,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY ratio_costo_logistico_ajustado_pct) AS p50_ratio_costo,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY indice_eficiencia_operativa) AS p75_eficiencia,
        percentile_cont(0.25) WITHIN GROUP (ORDER BY pct_rechazo_pedidos) AS p25_rechazo,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY dropsize_bultos_ytd) AS p50_dropsize
    FROM base
)
SELECT
    b.*,
    CASE
        WHEN b.cluster_dpo = 'Ganador'
         AND b.tiene_autoelevador
         AND b.venta_ytd >= u.p70_venta
         AND b.hl_ytd >= u.p70_hl
            THEN 'GANADOR AUTOELEVADOR'

        WHEN b.cluster_dpo = 'Ganador'
         AND b.indice_eficiencia_operativa >= u.p75_eficiencia
         AND b.ratio_costo_logistico_ajustado_pct <= u.p50_ratio_costo
         AND b.pct_rechazo_pedidos <= u.p25_rechazo
            THEN 'GANADOR EFICIENTE'

        WHEN b.venta_ytd >= u.p70_venta
         AND b.pedidos_ytd >= u.p70_pedidos
         AND NOT b.tiene_autoelevador
         AND b.ratio_costo_logistico_ajustado_pct >= u.p75_ratio_costo
            THEN 'ALTO VALOR CARO DE SERVIR'

        WHEN b.hl_ytd >= u.p70_hl
         AND b.dropsize_bultos_ytd >= u.p50_dropsize
         AND b.pct_rechazo_pedidos <= u.p25_rechazo
         AND b.ratio_costo_logistico_ajustado_pct <= u.p50_ratio_costo
            THEN 'ALTO VOLUMEN BAJA COMPLEJIDAD'

        WHEN b.factor_operativo = 3
         AND b.ratio_costo_logistico_ajustado_pct >= u.p75_ratio_costo
            THEN 'ALTO COSTO OPERATIVO'

        ELSE UPPER(COALESCE(b.subcluster_logistico, 'ESTANDAR'))
    END AS subcluster_logistico_operativo
FROM base b
CROSS JOIN u;

-- vw_clientes_mapa ------------------------------------------
DROP VIEW IF EXISTS vw_clientes_mapa CASCADE;
CREATE VIEW vw_clientes_mapa AS
WITH base AS (
    SELECT
        d.cliente AS cliente_id,
        d.descripcion_cliente AS cliente_nombre,
        g.latitud AS geo_latitud,
        g.longitud AS geo_longitud,
        REPLACE(REGEXP_REPLACE(TRIM(COALESCE(cli.coord_y, cli.coord_y_entrega, '')), '[[:space:]]+', '', 'g'), ',', '.') AS coord_y_txt,
        REPLACE(REGEXP_REPLACE(TRIM(COALESCE(cli.coord_x, cli.coord_x_entrega, '')), '[[:space:]]+', '', 'g'), ',', '.') AS coord_x_txt,
        d.hl_ytd AS hl,
        d.venta_ytd AS venta,
        d.pallets_ytd AS pallets,
        d.bultos_ytd AS bultos,
        d.cluster_dpo,
        a.tiene_autoelevador,
        d.sucursal,
        d.sucursal_nombre,
        COALESCE(NULLIF(d.localidad,''), NULLIF(g.localidad,''), NULLIF(cli.localidad,''), 'Sin localidad') AS localidad,
        d.ratio_costo_logistico_pct,
        d.costo_logistico_total,
        d.margen_logistico_proxy
    FROM vw_cliente_cluster_dpo d
    JOIN vw_cliente_autoelevador a
      ON a.cliente_id = d.cliente
     AND a.sucursal = d.sucursal
    LEFT JOIN cliente_geografia g
      ON g.cliente_id = d.cliente
    LEFT JOIN clientes cli
      ON cli.cliente = d.cliente
     AND COALESCE(NULLIF(TRIM(cli.sucursal),''), d.sucursal) = d.sucursal
),
coords AS (
    SELECT *,
           CASE WHEN coord_y_txt ~ '^-?[0-9]+(\.[0-9]+)?$' THEN coord_y_txt::NUMERIC END AS cli_latitud,
           CASE WHEN coord_x_txt ~ '^-?[0-9]+(\.[0-9]+)?$' THEN coord_x_txt::NUMERIC END AS cli_longitud
    FROM base
)
SELECT
    cliente_id,
    cliente_nombre,
    COALESCE(geo_latitud, cli_latitud) AS latitud,
    COALESCE(geo_longitud, cli_longitud) AS longitud,
    hl,
    venta,
    pallets,
    bultos,
    cluster_dpo,
    tiene_autoelevador,
    sucursal,
    sucursal_nombre,
    localidad,
    ratio_costo_logistico_pct,
    costo_logistico_total,
    margen_logistico_proxy
FROM coords
WHERE COALESCE(geo_latitud, cli_latitud) BETWEEN -90 AND 90
  AND COALESCE(geo_longitud, cli_longitud) BETWEEN -180 AND 180
  AND NOT (
      COALESCE(geo_latitud, cli_latitud) = 0
      AND COALESCE(geo_longitud, cli_longitud) = 0
  );


-- cache materializada para dashboard -------------------------
CREATE MATERIALIZED VIEW mv_cliente_plan_servicio AS
SELECT * FROM vw_cliente_plan_servicio
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_cliente_plan_cliente_suc
    ON mv_cliente_plan_servicio(cliente, sucursal);
CREATE INDEX IF NOT EXISTS idx_mv_cliente_plan_suc_cluster_score
    ON mv_cliente_plan_servicio(sucursal, cluster_dpo, prioridad_gestion, score_total DESC);
CREATE INDEX IF NOT EXISTS idx_mv_cliente_plan_cluster_score
    ON mv_cliente_plan_servicio(cluster_dpo, score_total DESC);
CREATE INDEX IF NOT EXISTS idx_mv_cliente_plan_localidad
    ON mv_cliente_plan_servicio(localidad, sucursal, cluster_dpo);
"""


# ─────────────────────────────────────────────────────────────
# Inicialización de tablas y vistas
# ─────────────────────────────────────────────────────────────

def _parse_iso_date(value: Any, field: str) -> date | None:
    if value in (None, ''):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f'{field} debe tener formato YYYY-MM-DD') from exc


def _same_month_day_previous_year(value: date) -> date:
    year = value.year - 1
    day = min(value.day, monthrange(year, value.month)[1])
    return date(year, value.month, day)


def build_periodo_payload(data: dict | None = None, today: date | None = None) -> dict:
    """Normaliza el periodo DPO. Por defecto calcula YTD vs mismo periodo anterior."""
    data = dict(data or {})
    today = today or date.today()
    periodo_anio = int(data.get('periodo_anio') or today.year)
    periodo_mes = int(data.get('periodo_mes') or 0)
    if periodo_mes < 0 or periodo_mes > 12:
        raise ValueError('periodo_mes debe estar entre 0 y 12')

    fecha_desde = _parse_iso_date(data.get('fecha_desde'), 'fecha_desde')
    fecha_hasta = _parse_iso_date(data.get('fecha_hasta'), 'fecha_hasta')

    if fecha_desde is None:
        fecha_desde = date(periodo_anio, 1, 1)

    if fecha_hasta is None:
        if periodo_mes:
            fecha_hasta = date(periodo_anio, periodo_mes, monthrange(periodo_anio, periodo_mes)[1])
        elif periodo_anio == today.year:
            fecha_hasta = today
        else:
            fecha_hasta = date(periodo_anio, 12, 31)

    fecha_base_desde = _parse_iso_date(data.get('fecha_base_desde'), 'fecha_base_desde')
    fecha_base_hasta = _parse_iso_date(data.get('fecha_base_hasta'), 'fecha_base_hasta')

    if fecha_base_desde is None:
        fecha_base_desde = _same_month_day_previous_year(fecha_desde)
    if fecha_base_hasta is None:
        fecha_base_hasta = _same_month_day_previous_year(fecha_hasta)

    if fecha_desde > fecha_hasta:
        raise ValueError('fecha_desde no puede ser posterior a fecha_hasta')
    if fecha_base_desde > fecha_base_hasta:
        raise ValueError('fecha_base_desde no puede ser posterior a fecha_base_hasta')

    if periodo_mes and data.get('fecha_hasta') not in (None, ''):
        periodo_anio = fecha_hasta.year
        periodo_mes = fecha_hasta.month

    return {
        'empresa_id': str(data.get('empresa_id') or '1'),
        'periodo_anio': periodo_anio,
        'periodo_mes': periodo_mes,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'fecha_base_desde': fecha_base_desde,
        'fecha_base_hasta': fecha_base_hasta,
    }


def _normalize_cluster_filter(cluster: str | None) -> str | None:
    if not cluster:
        return None
    value = str(cluster).strip()
    key = value.lower()
    if not key:
        return None
    if 'ganador' in key:
        return 'Ganador'
    if 'crecimiento' in key:
        return 'En crecimiento'
    if 'inactivo' in key:
        return 'Inactivo'
    if 'temp' in key:
        return 'Ruta Temp'
    if 'sico' in key or key == 'basico':
        return 'Basico'
    if 'baja' in key:
        return 'Ventas bajas'
    return value


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    txt = str(value).strip().lower()
    if txt in {'1', 'true', 't', 'si', 's', 'yes', 'y'}:
        return True
    if txt in {'0', 'false', 'f', 'no', 'n'}:
        return False
    return default


def _first_present(row: dict, keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ''):
            return row.get(key)
    return default


def ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return
    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(2026052501)")
                for ddl in (
                    _DDL_PARAMETROS,
                    _DDL_ATRIBUTOS,
                    _DDL_CLIENTE_GEO,
                    _DDL_CLIENTE_AUTOELEVADOR,
                    _DDL_PERIODOS,
                    _DDL_SCORE_PESOS,
                    _DDL_DPO_CACHE,
                    _DDL_HISTORICO,
                    _DDL_AUDITORIA,
                    _DDL_SCHEMA_VERSION,
                ):
                    cur.execute(ddl)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS clientes (
                        cliente VARCHAR(50) PRIMARY KEY
                    );
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS sucursal VARCHAR(50);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS razon_social VARCHAR(255);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS nombre_fantasia VARCHAR(255);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS coord_x VARCHAR(100);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS coord_y VARCHAR(100);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS coord_x_entrega VARCHAR(100);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS coord_y_entrega VARCHAR(100);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS localidad VARCHAR(100);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS anulado VARCHAR(50);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS fuerza_venta_1_dias_visita VARCHAR(50);
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS activo_maestro BOOLEAN NOT NULL DEFAULT TRUE;
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ultima_importacion_clientes TIMESTAMP;
                    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS desactivado_en TIMESTAMP;

                    CREATE TABLE IF NOT EXISTS sucursales (
                        id          VARCHAR(50) PRIMARY KEY,
                        empresa_id  VARCHAR(50) NOT NULL DEFAULT '1',
                        nombre      VARCHAR(100) NOT NULL,
                        activa      BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    INSERT INTO sucursales (id, empresa_id, nombre, activa) VALUES
                        ('1', '1', 'Casa Central', TRUE),
                        ('2', '1', 'Dolores', TRUE)
                    ON CONFLICT (id) DO NOTHING;
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_seg_fecha_cliente_suc_art
                        ON ventas_detalle(fecha, cliente, sucursal, id_articulo);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_seg_cliente_suc_fecha
                        ON ventas_detalle(cliente, sucursal, fecha);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_seg_ruta_desc
                        ON ventas_detalle((LOWER(TRIM(COALESCE(descripcion_ruta,'')))));
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_seg_ruta_det_desc
                        ON ventas_detalle((LOWER(TRIM(COALESCE(descripcion_detallada_ruta,'')))));
                    CREATE INDEX IF NOT EXISTS idx_articulos_tipo_producto_id
                        ON articulos ((LOWER(TRIM(COALESCE(tipo_producto,'')))), id_articulo);
                    CREATE INDEX IF NOT EXISTS idx_clientes_seg_cliente_sucursal
                        ON clientes(cliente, sucursal);
                    CREATE INDEX IF NOT EXISTS idx_clientes_seg_anulado
                        ON clientes((LOWER(TRIM(COALESCE(anulado,'no')))));
                    CREATE INDEX IF NOT EXISTS idx_clientes_seg_fv1_dias
                        ON clientes((LOWER(TRIM(COALESCE(fuerza_venta_1_dias_visita,'')))));
                    CREATE INDEX IF NOT EXISTS idx_clientes_seg_activo_maestro
                        ON clientes(activo_maestro);
                    CREATE INDEX IF NOT EXISTS idx_clientes_seg_sucursal_localidad
                        ON clientes(sucursal, localidad);
                    CREATE INDEX IF NOT EXISTS idx_seg_params_activo ON seg_parametros(activo,empresa_id);
                    CREATE INDEX IF NOT EXISTS idx_seg_periodos_activo ON seg_periodos_calculo(empresa_id,activo,id DESC);
                    CREATE INDEX IF NOT EXISTS idx_seg_score_dimension ON seg_score_pesos(dimension,activo);
                    CREATE INDEX IF NOT EXISTS idx_seg_dpo_cache_suc_cluster
                        ON seg_cliente_dpo_cache(sucursal, cluster_dpo, venta_ytd DESC);
                    CREATE INDEX IF NOT EXISTS idx_seg_dpo_cache_localidad
                        ON seg_cliente_dpo_cache(localidad, sucursal, cluster_dpo);
                    CREATE INDEX IF NOT EXISTS idx_seg_cli_suc       ON seg_clientes_atributos(sucursal_id);
                    CREATE INDEX IF NOT EXISTS idx_seg_cli_loc       ON seg_clientes_atributos(localidad);
                    CREATE INDEX IF NOT EXISTS idx_cli_geo_sucursal   ON cliente_geografia(sucursal);
                    CREATE INDEX IF NOT EXISTS idx_cli_geo_localidad  ON cliente_geografia(localidad);
                    CREATE INDEX IF NOT EXISTS idx_cli_geo_lat_lon    ON cliente_geografia(latitud, longitud);
                    CREATE INDEX IF NOT EXISTS idx_cli_auto_flag      ON cliente_autoelevador(autoelevador);
                    CREATE INDEX IF NOT EXISTS idx_cli_auto_fecha     ON cliente_autoelevador(fecha_importacion DESC);
                    CREATE INDEX IF NOT EXISTS idx_cli_auto_updated   ON cliente_autoelevador(updated_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_seg_hist_cli      ON seg_cliente_cluster_historico(cliente);
                    CREATE INDEX IF NOT EXISTS idx_seg_hist_per      ON seg_cliente_cluster_historico(periodo_anio,periodo_mes);
                    CREATE INDEX IF NOT EXISTS idx_seg_hist_cl       ON seg_cliente_cluster_historico(cluster_dpo);
                    CREATE INDEX IF NOT EXISTS idx_seg_hist_suc_periodo
                        ON seg_cliente_cluster_historico(sucursal_id, periodo_anio, periodo_mes);
                    CREATE INDEX IF NOT EXISTS idx_seg_hist_periodo_cluster
                        ON seg_cliente_cluster_historico(periodo_anio, periodo_mes, cluster_dpo);
                    CREATE INDEX IF NOT EXISTS idx_seg_aud_at        ON seg_auditoria(ejecutado_at DESC);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS venta_base_mismo_periodo NUMERIC(18,2);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS bultos_ytd NUMERIC(18,4);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS pallets_ytd NUMERIC(18,4);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS up_ytd NUMERIC(18,4);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS rechazos_ytd NUMERIC(18,4);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS nps_valor NUMERIC(6,2);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS rmd_valor NUMERIC(6,2);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS otif_valor NUMERIC(6,2);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS costo_entrega NUMERIC(18,2);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS costo_almacen NUMERIC(18,2);
                    ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS margen_logistico_proxy NUMERIC(18,2);
                    ALTER TABLE seg_cliente_cluster_historico ALTER COLUMN crecimiento_pct TYPE NUMERIC(14,4);
                    ALTER TABLE seg_cliente_cluster_historico ALTER COLUMN ratio_costo_logistico TYPE NUMERIC(14,4);
                    ALTER TABLE seg_cliente_cluster_historico ALTER COLUMN dropsize_ytd TYPE NUMERIC(14,4);
                    ALTER TABLE seg_cliente_cluster_historico ALTER COLUMN pct_rechazo_pedidos TYPE NUMERIC(12,4);

                    ALTER TABLE seg_clientes_atributos ADD COLUMN IF NOT EXISTS promotor VARCHAR(255);
                    ALTER TABLE seg_clientes_atributos ADD COLUMN IF NOT EXISTS otif_valor NUMERIC(6,2);
                    ALTER TABLE seg_clientes_atributos ADD COLUMN IF NOT EXISTS otif_fecha DATE;

                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS descripcion_cliente TEXT;
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS sucursal_nombre TEXT;
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS autoelevador BOOLEAN DEFAULT FALSE;
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS subcluster_logistico VARCHAR(80);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS ingreso NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS ventas_anio_actual NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS ventas_anio_anterior NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS venta_anio_base NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS venta_base_mismo_per NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS bultos_ytd NUMERIC(18,4);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pallets_ytd NUMERIC(18,4);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS up_ytd NUMERIC(18,4);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pedidos_ytd INTEGER;
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS dropsize_bultos_ytd NUMERIC(18,4);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS ticket_promedio_ytd NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS rechazos_ytd NUMERIC(18,4);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pct_rechazo_pedidos NUMERIC(8,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS crecimiento_pct NUMERIC(10,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS nps_valor NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS rmd_valor NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS otif_valor NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS costo_entrega NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS costo_almacen NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS costo_logistico_total NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS margen_logistico_proxy NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS ratio_costo_logistico_pct NUMERIC(8,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS p25_ingresos NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS p50_ingresos NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS p75_ingresos NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS p25_crecimiento NUMERIC(10,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS p50_crecimiento NUMERIC(10,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS p75_crecimiento NUMERIC(10,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS umbral_venta_alta NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS umbral_venta_baja NUMERIC(18,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS umbral_crecimiento NUMERIC(10,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS score_total NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS dim_negocio NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS dim_productividad NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS dim_servicio NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS dim_rentabilidad NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS dim_geo NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pts_venta NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pts_hl NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pts_crecimiento NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pts_dropsize NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pts_rechazos NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pts_rmd NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS pts_nps NUMERIC(6,2);
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS plan_servicio TEXT;
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS accion_prioritaria TEXT;
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS alerta_operativa TEXT;
                    ALTER TABLE seg_cliente_dpo_cache ADD COLUMN IF NOT EXISTS prioridad_gestion INTEGER;
                """)
                cur.execute("""
                    INSERT INTO seg_parametros(empresa_id)
                    SELECT '1'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM seg_parametros WHERE empresa_id='1' AND activo
                    )
                """)
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO seg_score_pesos(variable,dimension,peso,mayor_es_mejor)
                       VALUES %s
                       ON CONFLICT (variable) DO NOTHING""",
                    _DEFAULT_SCORE_PESOS,
                )
                cur.execute(
                    """SELECT version FROM seg_schema_version
                       WHERE component = 'segmentacion'""",
                )
                version_row = cur.fetchone()
                cur.execute(
                    """SELECT to_regclass('public.vw_cliente_metricas') AS metricas,
                              to_regclass('public.vw_cliente_plan_servicio') AS plan,
                              to_regclass('public.mv_cliente_plan_servicio') AS cache"""
                )
                view_row = cur.fetchone()
                schema_ok = (
                    version_row
                    and version_row[0] == _SCHEMA_VERSION
                    and view_row
                    and view_row[0]
                    and view_row[1]
                    and view_row[2]
                )
                if not schema_ok:
                    cur.execute(_VIEWS_SQL)
                    cur.execute(
                        """INSERT INTO seg_schema_version(component, version, applied_at)
                           VALUES ('segmentacion', %s, NOW())
                           ON CONFLICT (component)
                           DO UPDATE SET version = EXCLUDED.version, applied_at = NOW()""",
                        (_SCHEMA_VERSION,),
                    )
        _TABLES_READY = True


# ─────────────────────────────────────────────────────────────
# Parámetros
# ─────────────────────────────────────────────────────────────

def _plan_cache_populated() -> bool:
    with pg_cursor() as cur:
        cur.execute("""
            SELECT COALESCE(c.relispopulated, FALSE) AS populated
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'mv_cliente_plan_servicio'
        """)
        row = cur.fetchone()
        if not row or not row.get('populated'):
            return False
        cur.execute("SELECT EXISTS (SELECT 1 FROM mv_cliente_plan_servicio LIMIT 1) AS has_rows")
        has_rows = cur.fetchone()
    return bool(has_rows and has_rows.get('has_rows'))


def _plan_source() -> str:
    global _PLAN_SOURCE_CACHE
    if _PLAN_SOURCE_CACHE:
        return _PLAN_SOURCE_CACHE
    _PLAN_SOURCE_CACHE = (
        'mv_cliente_plan_servicio'
        if _plan_cache_populated()
        else 'vw_cliente_plan_servicio'
    )
    return _PLAN_SOURCE_CACHE


def _use_live_plan_source() -> None:
    global _PLAN_SOURCE_CACHE
    _PLAN_SOURCE_CACHE = 'vw_cliente_plan_servicio'
    cache_svc.clear('segmentacion:')


def _use_cached_plan_source() -> None:
    global _PLAN_SOURCE_CACHE
    _PLAN_SOURCE_CACHE = 'mv_cliente_plan_servicio'


def get_cache_status() -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute("""
            SELECT COALESCE(c.reltuples, 0)::BIGINT AS estimated_rows,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'seg_cliente_dpo_cache'
        """)
        cache = dict(cur.fetchone() or {})
        cur.execute("SELECT COUNT(*) AS rows FROM seg_cliente_dpo_cache")
        count_row = cur.fetchone()
        cache['rows'] = int(count_row['rows'] or 0)
        cache['populated'] = cache['rows'] > 0
        cur.execute("""
            SELECT version, applied_at
            FROM seg_schema_version
            WHERE component = 'segmentacion_cache'
        """)
        meta = cur.fetchone()
    cache['last_refresh_at'] = meta['applied_at'] if meta else None
    cache['cache_version'] = meta['version'] if meta else None
    cache['cache'] = 'seg_cliente_dpo_cache'
    return cache


def _refresh_segmentacion_cache_from_view(ejecutado_por: str = 'sistema') -> dict:
    ensure_tables()
    t0 = time.time()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(2026052502)")
            cur.execute("TRUNCATE TABLE seg_cliente_dpo_cache")
            cur.execute("SET LOCAL statement_timeout = '90000ms'")
            cur.execute(
                f"""INSERT INTO seg_cliente_dpo_cache (
                        {_DPO_CACHE_SELECT}, payload, updated_at
                    )
                    SELECT
                        {_DPO_CACHE_SELECT}, '{{}}'::jsonb, NOW()
                    FROM vw_cliente_plan_servicio
                    ORDER BY prioridad_gestion, venta_ytd DESC NULLS LAST"""
            )
            rows = cur.rowcount
            cur.execute("ANALYZE seg_cliente_dpo_cache")
            cur.execute(
                """INSERT INTO seg_schema_version(component, version, applied_at)
                   VALUES ('segmentacion_cache', %s, NOW())
                   ON CONFLICT (component)
                   DO UPDATE SET version = EXCLUDED.version, applied_at = NOW()""",
                (f'{_SCHEMA_VERSION}:{ejecutado_por}',),
            )
    cache_svc.clear('segmentacion:')
    return {
        'filas': rows,
        'duracion_ms': int((time.time() - t0) * 1000),
        'cache': 'seg_cliente_dpo_cache',
    }


def _refresh_segmentacion_cache_legacy(ejecutado_por: str = 'sistema') -> dict:
    ensure_tables()
    t0 = time.time()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(2026052502)")
            cur.execute("TRUNCATE TABLE seg_cliente_dpo_cache")
            cur.execute("SET LOCAL statement_timeout = '90000ms'")
            cur.execute("""
                WITH params AS (
                    SELECT
                        sp.costo_entrega_hl,
                        sp.costo_almacen_hl,
                        COALESCE(pc.fecha_desde, make_date(sp.anio_ytd, 1, 1)) AS fecha_desde,
                        COALESCE(
                            pc.fecha_hasta,
                            (make_date(
                                sp.anio_ytd,
                                COALESCE(sp.mes_ytd_hasta, EXTRACT(MONTH FROM CURRENT_DATE)::INT),
                                1
                            ) + interval '1 month - 1 day')::date
                        ) AS fecha_hasta,
                        COALESCE(pc.fecha_base_desde, make_date(sp.anio_base, 1, 1)) AS fecha_base_desde,
                        COALESCE(
                            pc.fecha_base_hasta,
                            (make_date(
                                sp.anio_base,
                                COALESCE(sp.mes_ytd_hasta, EXTRACT(MONTH FROM CURRENT_DATE)::INT),
                                1
                            ) + interval '1 month - 1 day')::date
                        ) AS fecha_base_hasta
                    FROM (
                        SELECT *
                        FROM seg_parametros
                        WHERE activo
                        ORDER BY (sucursal_id IS NULL) DESC, id DESC
                        LIMIT 1
                    ) sp
                    LEFT JOIN LATERAL (
                        SELECT *
                        FROM seg_periodos_calculo
                        WHERE activo AND empresa_id = sp.empresa_id
                        ORDER BY id DESC
                        LIMIT 1
                    ) pc ON TRUE
                ),
                ytd AS (
                    SELECT
                        NULLIF(TRIM(v.cliente),'') AS cliente,
                        COALESCE(NULLIF(TRIM(v.sucursal),''),'1') AS sucursal,
                        MAX(COALESCE(NULLIF(TRIM(v.descripcion_cliente),''), NULLIF(TRIM(v.descripcion_detallada_cliente),''), '')) AS descripcion_cliente,
                        SUM(COALESCE(v.importe_neto,0)) AS venta_ytd,
                        SUM(COALESCE(v.unidad_medida,0)) AS hl_ytd,
                        SUM(COALESCE(v.bultos,0)) AS bultos_ytd,
                        SUM(COALESCE(v.unidad_paquete,0)) AS up_ytd,
                        COUNT(DISTINCT v.fecha::TEXT||'|'||NULLIF(TRIM(v.cliente),'')) AS pedidos_ytd,
                        SUM(CASE WHEN COALESCE(v.bultos_rechazados,0)>0
                                   OR COALESCE(v.unidad_medida_rechazado,0)>0
                                   OR COALESCE(v.unidad_paquete_rechazado,0)>0
                                 THEN 1 ELSE 0 END) AS rechazos_ytd,
                        BOOL_OR(
                            LOWER(TRIM(COALESCE(v.descripcion_ruta,''))) LIKE '%temp%'
                            OR LOWER(TRIM(COALESCE(v.descripcion_detallada_ruta,''))) LIKE '%temp%'
                        ) AS es_ruta_temp
                    FROM ventas_detalle v
                    CROSS JOIN params p
                    JOIN articulos a ON a.id_articulo = v.id_articulo
                    WHERE v.fecha BETWEEN p.fecha_desde AND p.fecha_hasta
                      AND LOWER(TRIM(COALESCE(a.tipo_producto,'')))='mercaderia'
                      AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%'
                      AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%'
                      AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%'
                      AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%'
                      AND NULLIF(TRIM(v.cliente),'') IS NOT NULL
                    GROUP BY 1, 2
                ),
                prev AS (
                    SELECT
                        NULLIF(TRIM(v.cliente),'') AS cliente,
                        COALESCE(NULLIF(TRIM(v.sucursal),''),'1') AS sucursal,
                        SUM(COALESCE(v.importe_neto,0)) AS venta_base_mismo_per
                    FROM ventas_detalle v
                    CROSS JOIN params p
                    JOIN articulos a ON a.id_articulo = v.id_articulo
                    WHERE v.fecha BETWEEN p.fecha_base_desde AND p.fecha_base_hasta
                      AND LOWER(TRIM(COALESCE(a.tipo_producto,'')))='mercaderia'
                      AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%'
                      AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%'
                      AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%'
                      AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%'
                      AND NULLIF(TRIM(v.cliente),'') IS NOT NULL
                    GROUP BY 1, 2
                ),
                joined AS (
                    SELECT
                        COALESCE(y.cliente, p.cliente) AS cliente,
                        COALESCE(y.sucursal, p.sucursal) AS sucursal,
                        y.descripcion_cliente,
                        COALESCE(y.venta_ytd,0) AS venta_ytd,
                        COALESCE(p.venta_base_mismo_per,0) AS venta_base_mismo_per,
                        CASE WHEN COALESCE(p.venta_base_mismo_per,0)>0
                             THEN ROUND(((COALESCE(y.venta_ytd,0)-p.venta_base_mismo_per)/p.venta_base_mismo_per*100)::NUMERIC,2)
                             ELSE NULL END AS crecimiento_pct,
                        COALESCE(y.hl_ytd,0) AS hl_ytd,
                        COALESCE(y.bultos_ytd,0) AS bultos_ytd,
                        0::NUMERIC AS pallets_ytd,
                        COALESCE(y.up_ytd,0) AS up_ytd,
                        COALESCE(y.pedidos_ytd,0) AS pedidos_ytd,
                        COALESCE(y.rechazos_ytd,0) AS rechazos_ytd,
                        COALESCE(y.es_ruta_temp,FALSE) AS es_ruta_temp
                    FROM ytd y
                    FULL OUTER JOIN prev p ON p.cliente = y.cliente AND p.sucursal = y.sucursal
                ),
                activos AS (
                    SELECT
                        j.*,
                        COALESCE(NULLIF(TRIM(c.nombre_fantasia),''), NULLIF(TRIM(c.razon_social),''), j.descripcion_cliente, j.cliente) AS cliente_nombre,
                        COALESCE(NULLIF(TRIM(c.localidad),''), 'Sin localidad') AS localidad,
                        COALESCE(NULLIF(TRIM(s.nombre),''), j.sucursal) AS sucursal_nombre,
                        COALESCE(cae.autoelevador, ca.autoelevador, FALSE) AS autoelevador,
                        ca.nps_valor,
                        ca.rmd_valor,
                        ca.otif_valor
                    FROM joined j
                    JOIN clientes c ON c.cliente = j.cliente
                                  AND COALESCE(NULLIF(TRIM(c.sucursal),''), j.sucursal) = j.sucursal
                    LEFT JOIN sucursales s ON s.id = j.sucursal
                    LEFT JOIN cliente_autoelevador cae ON cae.is_cliente = j.cliente
                    LEFT JOIN seg_clientes_atributos ca ON ca.cliente = j.cliente
                    WHERE COALESCE(c.activo_maestro, TRUE) = TRUE
                      AND COALESCE(LOWER(TRIM(c.anulado)), '') IN ('no','n','0','false','f')
                      AND NULLIF(TRIM(COALESCE(c.fuerza_venta_1_dias_visita, '')), '') IS NOT NULL
                      AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') <> 'dom'
                      AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') NOT LIKE '%oficina%'
                      AND NOT j.es_ruta_temp
                      AND (j.venta_ytd > 0 OR j.venta_base_mismo_per > 0)
                ),
                pct AS (
                    SELECT
                        percentile_cont(0.25) WITHIN GROUP (ORDER BY venta_ytd) AS p25_ingresos,
                        percentile_cont(0.50) WITHIN GROUP (ORDER BY venta_ytd) AS p50_ingresos,
                        percentile_cont(0.75) WITHIN GROUP (ORDER BY venta_ytd) AS p75_ingresos,
                        percentile_cont(0.25) WITHIN GROUP (ORDER BY COALESCE(crecimiento_pct,0)) AS p25_crecimiento,
                        percentile_cont(0.50) WITHIN GROUP (ORDER BY COALESCE(crecimiento_pct,0)) AS p50_crecimiento,
                        percentile_cont(0.75) WITHIN GROUP (ORDER BY COALESCE(crecimiento_pct,0)) AS p75_crecimiento
                    FROM activos
                ),
                final_rows AS (
                    SELECT
                        a.cliente,
                        a.cliente_nombre AS descripcion_cliente,
                        a.sucursal,
                        a.sucursal_nombre,
                        a.localidad,
                        a.autoelevador,
                        a.venta_ytd AS ingreso,
                        a.venta_ytd AS ventas_anio_actual,
                        a.venta_base_mismo_per AS ventas_anio_anterior,
                        a.venta_base_mismo_per AS venta_anio_base,
                        a.venta_base_mismo_per,
                        a.venta_ytd,
                        a.crecimiento_pct,
                        a.hl_ytd,
                        a.bultos_ytd,
                        a.pallets_ytd,
                        a.up_ytd,
                        a.pedidos_ytd,
                        CASE WHEN a.pedidos_ytd > 0 THEN ROUND((a.bultos_ytd/a.pedidos_ytd)::NUMERIC,2) ELSE 0 END AS dropsize_bultos_ytd,
                        CASE WHEN a.pedidos_ytd > 0 THEN ROUND((a.venta_ytd/a.pedidos_ytd)::NUMERIC,2) ELSE 0 END AS ticket_promedio_ytd,
                        a.rechazos_ytd,
                        CASE WHEN a.pedidos_ytd > 0 THEN ROUND((a.rechazos_ytd::NUMERIC/a.pedidos_ytd*100),2) ELSE 0 END AS pct_rechazo_pedidos,
                        a.nps_valor,
                        a.rmd_valor,
                        a.otif_valor,
                        ROUND((a.hl_ytd * p.costo_entrega_hl)::NUMERIC,2) AS costo_entrega,
                        ROUND((a.hl_ytd * p.costo_almacen_hl)::NUMERIC,2) AS costo_almacen,
                        ROUND((a.hl_ytd * (p.costo_entrega_hl + p.costo_almacen_hl))::NUMERIC,2) AS costo_logistico_total,
                        ROUND((a.venta_ytd - a.hl_ytd * (p.costo_entrega_hl + p.costo_almacen_hl))::NUMERIC,2) AS margen_logistico_proxy,
                        CASE WHEN a.venta_ytd > 0
                             THEN ROUND((a.hl_ytd * (p.costo_entrega_hl + p.costo_almacen_hl) / a.venta_ytd * 100)::NUMERIC,2)
                             ELSE 0 END AS ratio_costo_logistico_pct,
                        pct.p25_ingresos,
                        pct.p50_ingresos,
                        pct.p75_ingresos,
                        pct.p25_crecimiento,
                        pct.p50_crecimiento,
                        pct.p75_crecimiento,
                        pct.p75_ingresos AS umbral_venta_alta,
                        pct.p25_ingresos AS umbral_venta_baja,
                        pct.p50_crecimiento AS umbral_crecimiento,
                        CASE
                            WHEN a.venta_ytd >= pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p50_crecimiento THEN 'Ganador'
                            WHEN a.venta_ytd < pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p75_crecimiento THEN 'En crecimiento'
                            WHEN a.venta_ytd <= pct.p25_ingresos
                             AND COALESCE(a.crecimiento_pct,0) <= pct.p25_crecimiento THEN 'Ventas bajas'
                            ELSE 'Basico'
                        END AS cluster_dpo,
                        CASE
                            WHEN a.rechazos_ytd > 0 AND a.pedidos_ytd > 0 AND (a.rechazos_ytd::NUMERIC/a.pedidos_ytd*100) > 20 THEN 'Complejo'
                            WHEN COALESCE(a.crecimiento_pct,0) > 15 THEN 'Alto potencial'
                            WHEN a.autoelevador THEN 'Eficiente'
                            ELSE 'Estandar'
                        END AS subcluster_logistico,
                        0::NUMERIC AS score_total,
                        0::NUMERIC AS dim_negocio,
                        0::NUMERIC AS dim_productividad,
                        0::NUMERIC AS dim_servicio,
                        0::NUMERIC AS dim_rentabilidad,
                        0::NUMERIC AS dim_geo,
                        0::NUMERIC AS pts_venta,
                        0::NUMERIC AS pts_hl,
                        0::NUMERIC AS pts_crecimiento,
                        0::NUMERIC AS pts_dropsize,
                        0::NUMERIC AS pts_rechazos,
                        0::NUMERIC AS pts_rmd,
                        0::NUMERIC AS pts_nps,
                        CASE
                            WHEN a.venta_ytd >= pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p50_crecimiento
                                THEN 'Prioridad inventario - ventanas cortas - express habilitado - SLA premium'
                            WHEN a.venta_ytd < pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p75_crecimiento
                                THEN 'Potenciar servicio - flex habilitado - mayor disponibilidad'
                            WHEN a.venta_ytd <= pct.p25_ingresos
                             AND COALESCE(a.crecimiento_pct,0) <= pct.p25_crecimiento
                                THEN 'Consolidar rutas - revisar frecuencia - ventanas amplias - reducir costo'
                            ELSE 'Servicio estandar - optimizacion de frecuencia'
                        END AS plan_servicio,
                        CASE
                            WHEN a.venta_ytd <= pct.p25_ingresos THEN 'Revisar frecuencia y consolidacion'
                            WHEN COALESCE(a.crecimiento_pct,0) >= pct.p75_crecimiento THEN 'Priorizar desarrollo comercial'
                            ELSE 'Monitorear mensualmente'
                        END AS accion_prioritaria,
                        CASE
                            WHEN a.rechazos_ytd > 0 AND a.pedidos_ytd > 0 AND (a.rechazos_ytd::NUMERIC/a.pedidos_ytd*100) > 20
                                THEN 'CRITICO: tasa de rechazo > 20 %'
                            WHEN a.otif_valor IS NOT NULL AND a.otif_valor < 85 THEN 'ATENCION: OTIF menor a 85 %'
                            WHEN COALESCE(a.crecimiento_pct,0) < -30 THEN 'ALERTA: caida de venta > 30 %'
                            ELSE NULL
                        END AS alerta_operativa,
                        CASE
                            WHEN a.venta_ytd >= pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p50_crecimiento THEN 1
                            WHEN a.venta_ytd < pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p75_crecimiento THEN 2
                            WHEN a.venta_ytd <= pct.p25_ingresos
                             AND COALESCE(a.crecimiento_pct,0) <= pct.p25_crecimiento THEN 4
                            ELSE 3
                        END AS prioridad_gestion
                    FROM activos a
                    CROSS JOIN pct
                    CROSS JOIN params p
                )
                INSERT INTO seg_cliente_dpo_cache
                    (
                        cliente, descripcion_cliente, sucursal, sucursal_nombre, localidad,
                        autoelevador, cluster_dpo, subcluster_logistico,
                        ingreso, ventas_anio_actual, ventas_anio_anterior,
                        venta_anio_base, venta_base_mismo_per, venta_ytd, hl_ytd,
                        bultos_ytd, pallets_ytd, up_ytd, pedidos_ytd,
                        dropsize_bultos_ytd, ticket_promedio_ytd, rechazos_ytd,
                        pct_rechazo_pedidos, crecimiento_pct, nps_valor, rmd_valor, otif_valor,
                        costo_entrega, costo_almacen, costo_logistico_total,
                        margen_logistico_proxy, ratio_costo_logistico_pct,
                        p25_ingresos, p50_ingresos, p75_ingresos,
                        p25_crecimiento, p50_crecimiento, p75_crecimiento,
                        umbral_venta_alta, umbral_venta_baja, umbral_crecimiento,
                        score_total, dim_negocio, dim_productividad, dim_servicio,
                        dim_rentabilidad, dim_geo, pts_venta, pts_hl,
                        pts_crecimiento, pts_dropsize, pts_rechazos, pts_rmd, pts_nps,
                        plan_servicio, accion_prioritaria, alerta_operativa,
                        prioridad_gestion, payload, updated_at
                    )
                SELECT
                    cliente,
                    descripcion_cliente,
                    sucursal,
                    sucursal_nombre,
                    localidad,
                    autoelevador,
                    cluster_dpo,
                    subcluster_logistico,
                    ingreso,
                    ventas_anio_actual,
                    ventas_anio_anterior,
                    venta_anio_base,
                    venta_base_mismo_per,
                    venta_ytd,
                    hl_ytd,
                    bultos_ytd,
                    pallets_ytd,
                    up_ytd,
                    pedidos_ytd,
                    dropsize_bultos_ytd,
                    ticket_promedio_ytd,
                    rechazos_ytd,
                    pct_rechazo_pedidos,
                    crecimiento_pct,
                    nps_valor,
                    rmd_valor,
                    otif_valor,
                    costo_entrega,
                    costo_almacen,
                    costo_logistico_total,
                    margen_logistico_proxy,
                    ratio_costo_logistico_pct,
                    p25_ingresos,
                    p50_ingresos,
                    p75_ingresos,
                    p25_crecimiento,
                    p50_crecimiento,
                    p75_crecimiento,
                    umbral_venta_alta,
                    umbral_venta_baja,
                    umbral_crecimiento,
                    score_total,
                    dim_negocio,
                    dim_productividad,
                    dim_servicio,
                    dim_rentabilidad,
                    dim_geo,
                    pts_venta,
                    pts_hl,
                    pts_crecimiento,
                    pts_dropsize,
                    pts_rechazos,
                    pts_rmd,
                    pts_nps,
                    plan_servicio,
                    accion_prioritaria,
                    alerta_operativa,
                    prioridad_gestion,
                    '{}'::jsonb,
                    NOW()
                FROM final_rows
            """)
            rows = cur.rowcount
            score_rows = _update_dpo_cache_scores(cur)
            cur.execute("ANALYZE seg_cliente_dpo_cache")
            cur.execute(
                """INSERT INTO seg_schema_version(component, version, applied_at)
                   VALUES ('segmentacion_cache', %s, NOW())
                   ON CONFLICT (component)
                   DO UPDATE SET version = EXCLUDED.version, applied_at = NOW()""",
                (f'{_SCHEMA_VERSION}:{ejecutado_por}',),
            )
    cache_svc.clear('segmentacion:')
    return {
        'filas': rows,
        'score_actualizados': score_rows,
        'duracion_ms': int((time.time() - t0) * 1000),
        'cache': 'seg_cliente_dpo_cache',
        'modo': 'fast_sql',
    }


def _update_dpo_cache_scores(cur) -> int:
    cur.execute("""
        WITH md AS (
            SELECT
                COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY rmd_valor), 5)::NUMERIC AS mrmd,
                COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY nps_valor), 5)::NUMERIC AS mnps,
                COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY crecimiento_pct), 0)::NUMERIC AS mcrec
            FROM seg_cliente_dpo_cache
        ),
        w AS (
            SELECT
                COALESCE(MAX(peso) FILTER (WHERE variable='venta' AND activo),15) AS venta,
                COALESCE(MAX(peso) FILTER (WHERE variable='hl' AND activo),10) AS hl,
                COALESCE(MAX(peso) FILTER (WHERE variable='crecimiento' AND activo),10) AS crecimiento,
                COALESCE(MAX(peso) FILTER (WHERE variable='dropsize' AND activo),10) AS dropsize,
                COALESCE(MAX(peso) FILTER (WHERE variable='pallets_pedido' AND activo),5) AS pallets_pedido,
                COALESCE(MAX(peso) FILTER (WHERE variable='autoelevador' AND activo),5) AS autoelevador,
                COALESCE(MAX(peso) FILTER (WHERE variable='rechazos' AND activo),10) AS rechazos,
                COALESCE(MAX(peso) FILTER (WHERE variable='rmd' AND activo),5) AS rmd,
                COALESCE(MAX(peso) FILTER (WHERE variable='nps' AND activo),5) AS nps,
                COALESCE(MAX(peso) FILTER (WHERE variable='ratio_costo' AND activo),10) AS ratio_costo,
                COALESCE(MAX(peso) FILTER (WHERE variable='margen' AND activo),5) AS margen,
                COALESCE(MAX(peso) FILTER (WHERE variable='frecuencia' AND activo),7) AS frecuencia,
                COALESCE(MAX(peso) FILTER (WHERE variable='localidad' AND activo),2) AS localidad,
                COALESCE(MAX(peso) FILTER (WHERE variable='sucursal' AND activo),1) AS sucursal
            FROM seg_score_pesos
        ),
        cl AS (
            SELECT d.*,
                   GREATEST(-100,LEAST(300,COALESCE(d.crecimiento_pct,md.mcrec))) AS cc,
                   COALESCE(d.rmd_valor,md.mrmd) AS ri,
                   COALESCE(d.nps_valor,md.mnps) AS ni,
                   CASE WHEN COALESCE(d.pedidos_ytd,0)>0 THEN COALESCE(d.pallets_ytd,0)/d.pedidos_ytd ELSE 0 END AS ppp,
                   GREATEST(0,COALESCE(d.ratio_costo_logistico_pct,0)) AS rcp
            FROM seg_cliente_dpo_cache d
            CROSS JOIN md
        ),
        rn AS (
            SELECT c.*,
                   MIN(venta_ytd) OVER() AS mnv, MAX(venta_ytd) OVER() AS mxv,
                   MIN(hl_ytd) OVER() AS mnh, MAX(hl_ytd) OVER() AS mxh,
                   MIN(cc) OVER() AS mnc, MAX(cc) OVER() AS mxc,
                   MIN(dropsize_bultos_ytd) OVER() AS mnd, MAX(dropsize_bultos_ytd) OVER() AS mxd,
                   MIN(ppp) OVER() AS mnp, MAX(ppp) OVER() AS mxp,
                   MIN(pct_rechazo_pedidos) OVER() AS mnr, MAX(pct_rechazo_pedidos) OVER() AS mxr,
                   MIN(ri) OVER() AS mnrmd, MAX(ri) OVER() AS mxrmd,
                   MIN(ni) OVER() AS mnnps, MAX(ni) OVER() AS mxnps,
                   MIN(rcp) OVER() AS mnrc, MAX(rcp) OVER() AS mxrc,
                   MIN(margen_logistico_proxy) OVER() AS mnmg, MAX(margen_logistico_proxy) OVER() AS mxmg,
                   MIN(pedidos_ytd) OVER() AS mnped, MAX(pedidos_ytd) OVER() AS mxped
            FROM cl c
        ),
        nr AS (
            SELECT r.*,
                   CASE WHEN mxv>mnv THEN (venta_ytd-mnv)/(mxv-mnv) ELSE 0.5 END AS nv,
                   CASE WHEN mxh>mnh THEN (hl_ytd-mnh)/(mxh-mnh) ELSE 0.5 END AS nh,
                   CASE WHEN mxc>mnc THEN (cc-mnc)/(mxc-mnc) ELSE 0.5 END AS nc,
                   CASE WHEN mxd>mnd THEN (dropsize_bultos_ytd-mnd)/(mxd-mnd) ELSE 0.5 END AS nd,
                   CASE WHEN mxp>mnp THEN (ppp-mnp)/(mxp-mnp) ELSE 0.5 END AS np,
                   CASE WHEN mxr>mnr THEN 1-(pct_rechazo_pedidos-mnr)/(mxr-mnr) ELSE 0.5 END AS nr_,
                   CASE WHEN mxrmd>mnrmd THEN (ri-mnrmd)/(mxrmd-mnrmd) ELSE 0.5 END AS nrmd,
                   CASE WHEN mxnps>mnnps THEN (ni-mnnps)/(mxnps-mnnps) ELSE 0.5 END AS nnps,
                   CASE WHEN mxrc>mnrc THEN 1-(rcp-mnrc)/(mxrc-mnrc) ELSE 0.5 END AS nrc,
                   CASE WHEN mxmg>mnmg THEN (margen_logistico_proxy-mnmg)/(mxmg-mnmg) ELSE 0.5 END AS nmg,
                   CASE WHEN mxped>mnped THEN (pedidos_ytd-mnped)/(mxped-mnped) ELSE 0.5 END AS nped
            FROM rn r
        ),
        calc AS (
            SELECT n.cliente,
                   ROUND((n.nv*w.venta+n.nh*w.hl+n.nc*w.crecimiento)::NUMERIC,2) AS dim_negocio,
                   ROUND((n.nd*w.dropsize+n.np*w.pallets_pedido+(CASE WHEN n.autoelevador THEN w.autoelevador ELSE 0.0 END))::NUMERIC,2) AS dim_productividad,
                   ROUND((n.nr_*w.rechazos+n.nrmd*w.rmd+n.nnps*w.nps)::NUMERIC,2) AS dim_servicio,
                   ROUND((n.nrc*w.ratio_costo+n.nmg*w.margen)::NUMERIC,2) AS dim_rentabilidad,
                   ROUND((n.nped*w.frecuencia+(CASE WHEN NULLIF(n.localidad,'') IS NOT NULL THEN w.localidad ELSE 0.0 END)
                         +(CASE WHEN NULLIF(n.sucursal,'') IS NOT NULL THEN w.sucursal ELSE 0.0 END))::NUMERIC,2) AS dim_geo,
                   ROUND((n.nv*w.venta)::NUMERIC,2) AS pts_venta,
                   ROUND((n.nh*w.hl)::NUMERIC,2) AS pts_hl,
                   ROUND((n.nc*w.crecimiento)::NUMERIC,2) AS pts_crecimiento,
                   ROUND((n.nd*w.dropsize)::NUMERIC,2) AS pts_dropsize,
                   ROUND((n.nr_*w.rechazos)::NUMERIC,2) AS pts_rechazos,
                   ROUND((n.nrmd*w.rmd)::NUMERIC,2) AS pts_rmd,
                   ROUND((n.nnps*w.nps)::NUMERIC,2) AS pts_nps,
                   ROUND((n.nv*w.venta+n.nh*w.hl+n.nc*w.crecimiento+n.nd*w.dropsize+n.np*w.pallets_pedido
                         +(CASE WHEN n.autoelevador THEN w.autoelevador ELSE 0.0 END)
                         +n.nr_*w.rechazos+n.nrmd*w.rmd+n.nnps*w.nps+n.nrc*w.ratio_costo+n.nmg*w.margen+n.nped*w.frecuencia
                         +(CASE WHEN NULLIF(n.localidad,'') IS NOT NULL THEN w.localidad ELSE 0.0 END)
                         +(CASE WHEN NULLIF(n.sucursal,'') IS NOT NULL THEN w.sucursal ELSE 0.0 END))::NUMERIC,2) AS score_total
            FROM nr n CROSS JOIN w
        )
        UPDATE seg_cliente_dpo_cache d
           SET score_total = calc.score_total,
               dim_negocio = calc.dim_negocio,
               dim_productividad = calc.dim_productividad,
               dim_servicio = calc.dim_servicio,
               dim_rentabilidad = calc.dim_rentabilidad,
               dim_geo = calc.dim_geo,
               pts_venta = calc.pts_venta,
               pts_hl = calc.pts_hl,
               pts_crecimiento = calc.pts_crecimiento,
               pts_dropsize = calc.pts_dropsize,
               pts_rechazos = calc.pts_rechazos,
               pts_rmd = calc.pts_rmd,
               pts_nps = calc.pts_nps,
               updated_at = NOW()
          FROM calc
         WHERE d.cliente = calc.cliente
    """)
    return int(cur.rowcount or 0)


def repair_segmentacion_cache_scores(ejecutado_por: str = 'sistema') -> dict:
    ensure_tables()
    t0 = time.time()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '30000ms'")
            score_rows = _update_dpo_cache_scores(cur)
            cur.execute("ANALYZE seg_cliente_dpo_cache")
            cur.execute(
                """INSERT INTO seg_schema_version(component, version, applied_at)
                   VALUES ('segmentacion_cache', %s, NOW())
                   ON CONFLICT (component)
                   DO UPDATE SET version = EXCLUDED.version, applied_at = NOW()""",
                (f'{_SCHEMA_VERSION}:score_repair:{ejecutado_por}',),
            )
    cache_svc.clear('segmentacion:')
    return {
        'filas': score_rows,
        'score_actualizados': score_rows,
        'duracion_ms': int((time.time() - t0) * 1000),
        'cache': 'seg_cliente_dpo_cache',
        'modo': 'score_repair',
    }


def refresh_segmentacion_cache(ejecutado_por: str = 'sistema') -> dict:
    return _refresh_segmentacion_cache_legacy(ejecutado_por)


def get_parametros() -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute("""
            SELECT * FROM seg_parametros
            WHERE activo ORDER BY (sucursal_id IS NULL) DESC, id DESC LIMIT 1
        """)
        row = cur.fetchone()
        params = dict(row) if row else {}
        cur.execute(
            """SELECT * FROM seg_periodos_calculo
               WHERE activo AND empresa_id = %(empresa_id)s
               ORDER BY id DESC LIMIT 1""",
            {'empresa_id': params.get('empresa_id', '1')},
        )
        periodo = cur.fetchone()
    if periodo:
        params['periodo'] = dict(periodo)
    else:
        params['periodo'] = build_periodo_payload({
            'empresa_id': params.get('empresa_id', '1'),
            'periodo_anio': params.get('anio_ytd') or date.today().year,
            'periodo_mes': params.get('mes_ytd_hasta') or 0,
        })
    return params


def update_parametros(data: dict) -> dict:
    ensure_tables()
    if 'percentil_alta' in data or 'percentil_baja' in data:
        current = get_parametros()
        alta = float(data.get('percentil_alta', current.get('percentil_alta', 0.70)))
        baja = float(data.get('percentil_baja', current.get('percentil_baja', 0.30)))
        if not (0 <= baja < alta <= 1):
            raise ValueError('percentil_baja debe ser menor que percentil_alta y ambos deben estar entre 0 y 1')

    period_fields = {
        'empresa_id', 'periodo_anio', 'periodo_mes',
        'fecha_desde', 'fecha_hasta', 'fecha_base_desde', 'fecha_base_hasta',
    }
    periodo_updated = None
    if any(k in data for k in period_fields):
        periodo_updated = set_periodo_calculo(data)

    campos = (
        'costo_entrega_hl', 'costo_almacen_hl', 'percentil_alta', 'percentil_baja',
        'umbral_crecimiento', 'anio_base', 'anio_ytd', 'mes_ytd_hasta',
        'peso_negocio', 'peso_productividad', 'peso_servicio', 'peso_rentabilidad', 'peso_geo',
    )
    set_parts = ', '.join(f"{c} = %({c})s" for c in campos if c in data)
    if not set_parts:
        if periodo_updated:
            return get_parametros()
        raise ValueError('No se recibieron campos válidos para actualizar.')
    data['updated_at'] = datetime.now()
    set_parts += ', updated_at = %(updated_at)s, version_regla = version_regla + 1'
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE seg_parametros SET {set_parts} WHERE activo "
                "RETURNING *",
                data,
            )
            updated = cur.fetchone()
    result = dict(updated) if updated else {}
    if periodo_updated:
        result['periodo'] = periodo_updated
    _use_live_plan_source()
    return result


def get_periodo_activo(empresa_id: str = '1') -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """SELECT * FROM seg_periodos_calculo
               WHERE activo AND empresa_id = %(empresa_id)s
               ORDER BY id DESC LIMIT 1""",
            {'empresa_id': empresa_id},
        )
        row = cur.fetchone()
    return dict(row) if row else build_periodo_payload({'empresa_id': empresa_id})


def set_periodo_calculo(data: dict) -> dict:
    ensure_tables()
    payload = build_periodo_payload(data)
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """UPDATE seg_periodos_calculo
                   SET activo = FALSE
                   WHERE empresa_id = %(empresa_id)s AND activo""",
                payload,
            )
            cur.execute(
                """INSERT INTO seg_periodos_calculo (
                       empresa_id, periodo_anio, periodo_mes,
                       fecha_desde, fecha_hasta, fecha_base_desde, fecha_base_hasta
                   ) VALUES (
                       %(empresa_id)s, %(periodo_anio)s, %(periodo_mes)s,
                       %(fecha_desde)s, %(fecha_hasta)s, %(fecha_base_desde)s, %(fecha_base_hasta)s
                   )
                   RETURNING *""",
                payload,
            )
            row = cur.fetchone()
    _use_live_plan_source()
    return dict(row) if row else payload


def list_score_pesos() -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """SELECT variable, dimension, peso, mayor_es_mejor, activo
               FROM seg_score_pesos
               ORDER BY dimension, variable"""
        )
        return _dict_rows(cur)


def update_score_pesos(rows: list[dict]) -> int:
    ensure_tables()
    batch = [
        (
            str(r['variable']),
            str(r.get('dimension') or 'custom'),
            float(r['peso']),
            bool(r.get('mayor_es_mejor', True)),
            bool(r.get('activo', True)),
        )
        for r in rows
        if r.get('variable') and r.get('peso') is not None
    ]
    if not batch:
        return 0
    with pg_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO seg_score_pesos(variable,dimension,peso,mayor_es_mejor,activo)
                   VALUES %s
                   ON CONFLICT (variable) DO UPDATE SET
                       dimension = EXCLUDED.dimension,
                       peso = EXCLUDED.peso,
                       mayor_es_mejor = EXCLUDED.mayor_es_mejor,
                       activo = EXCLUDED.activo,
                       updated_at = NOW()""",
                batch,
            )
    _use_live_plan_source()
    return len(batch)


# ─────────────────────────────────────────────────────────────
# Atributos de clientes
# ─────────────────────────────────────────────────────────────

def upsert_atributos_cliente(cliente: str, data: dict) -> dict:
    ensure_tables()
    data['cliente'] = cliente.strip()
    data['updated_at'] = datetime.now()
    campos = ('cliente', 'sucursal_id', 'localidad', 'autoelevador',
              'nps_valor', 'nps_fecha', 'rmd_valor', 'rmd_fecha',
              'otif_valor', 'otif_fecha', 'updated_at')
    presentes = [c for c in campos if c in data]
    cols = ', '.join(presentes)
    vals = ', '.join(f'%({c})s' for c in presentes)
    updates = ', '.join(
        f"{c} = EXCLUDED.{c}"
        for c in presentes if c != 'cliente'
    )
    sql = (
        f"INSERT INTO seg_clientes_atributos ({cols}) VALUES ({vals}) "
        f"ON CONFLICT (cliente) DO UPDATE SET {updates} RETURNING *"
    )
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, data)
            row = cur.fetchone()
    _use_live_plan_source()
    return dict(row) if row else {}


def bulk_upsert_atributos(registros: list[dict]) -> int:
    """Carga masiva de atributos de clientes desde CSV/Excel."""
    ensure_tables()
    if not registros:
        return 0
    now = datetime.now()
    batch = [
        (
            r.get('cliente', '').strip(),
            r.get('sucursal_id'),
            r.get('localidad'),
            r.get('autoelevador'),
            r.get('nps_valor'),
            r.get('nps_fecha'),
            r.get('rmd_valor'),
            r.get('rmd_fecha'),
            r.get('otif_valor'),
            r.get('otif_fecha'),
            now,
        )
        for r in registros
        if r.get('cliente', '').strip()
    ]
    with pg_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO seg_clientes_atributos
                   (cliente,sucursal_id,localidad,autoelevador,
                    nps_valor,nps_fecha,rmd_valor,rmd_fecha,otif_valor,otif_fecha,updated_at)
                   VALUES %s
                   ON CONFLICT (cliente) DO UPDATE SET
                       sucursal_id  = COALESCE(EXCLUDED.sucursal_id, seg_clientes_atributos.sucursal_id),
                       localidad    = COALESCE(EXCLUDED.localidad, seg_clientes_atributos.localidad),
                       autoelevador = COALESCE(EXCLUDED.autoelevador, seg_clientes_atributos.autoelevador),
                       nps_valor    = COALESCE(EXCLUDED.nps_valor, seg_clientes_atributos.nps_valor),
                       nps_fecha    = COALESCE(EXCLUDED.nps_fecha, seg_clientes_atributos.nps_fecha),
                       rmd_valor    = COALESCE(EXCLUDED.rmd_valor, seg_clientes_atributos.rmd_valor),
                       rmd_fecha    = COALESCE(EXCLUDED.rmd_fecha, seg_clientes_atributos.rmd_fecha),
                       otif_valor   = COALESCE(EXCLUDED.otif_valor, seg_clientes_atributos.otif_valor),
                       otif_fecha   = COALESCE(EXCLUDED.otif_fecha, seg_clientes_atributos.otif_fecha),
                       updated_at   = EXCLUDED.updated_at""",
                batch,
                page_size=500,
            )
    _use_live_plan_source()
    return len(batch)


# ─────────────────────────────────────────────────────────────
# Consultas sobre vistas
# ─────────────────────────────────────────────────────────────

def bulk_upsert_autoelevador(clientes: list[dict | str], fuente: str = 'api') -> int:
    ensure_tables()
    dedup: dict[str, tuple[bool, str]] = {}
    for item in clientes or []:
        if isinstance(item, dict):
            cid = str(_first_present(
                item,
                ('is_cliente', 'cliente', 'cliente_id', 'id_cliente', 'cod_cliente', 'codigo_cliente', 'codigo'),
                '',
            )).strip()
            auto_value = _first_present(
                item,
                ('autoelevador', 'auto_elevador', 'tiene_autoelevador', 'auto', 'forklift'),
                True,
            )
            auto = _as_bool(auto_value, True)
        else:
            cid = str(item or '').strip()
            auto = True
        if not cid:
            continue
        dedup[cid] = (auto, str(fuente or 'api'))
    if not dedup:
        return 0
    now = datetime.now()
    values = [(c, a, now, f, now) for c, (a, f) in dedup.items()]
    with pg_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO cliente_autoelevador
                   (is_cliente, autoelevador, fecha_importacion, fuente, updated_at)
                   VALUES %s
                   ON CONFLICT (is_cliente) DO UPDATE SET
                       autoelevador = EXCLUDED.autoelevador,
                       fecha_importacion = NOW(),
                       fuente = EXCLUDED.fuente,
                       updated_at = NOW()""",
                values,
                page_size=1000,
            )
    _use_live_plan_source()
    return len(values)


_PROMOTORES_EXCLUIDOS = {'mayoristas', 'oficina mda', 'venta remota', 'oficina dolores', '50-oficina dolores'}

def bulk_upsert_promotores(rows: list[dict]) -> dict:
    """Importa la asignación cliente → promotor y marca activos según criterio."""
    ensure_tables()
    now = datetime.now()
    dedup: dict[str, str] = {}
    for row in rows or []:
        cid = str(_first_present(row,
            ('cliente', 'is_cliente', 'codigo_cliente', 'codigo_de_cliente', 'cod_cliente', 'codigo'), ''
        )).strip()
        prom = str(_first_present(row,
            ('promotor', 'fuerza_venta_1_descripcion_personal_comercial',
             'fuerza_de_venta_1_descripcion_personal_comercial',
             'fuerza_venta_1_descripcion', 'descripcion_vendedor', 'vendedor'), ''
        )).strip()
        if not cid:
            continue
        dedup[cid] = prom

    if not dedup:
        return {'actualizados': 0, 'activos': 0, 'inactivos': 0}

    activos, inactivos = 0, 0
    values = []
    for cid, prom in dedup.items():
        es_activo = bool(prom) and prom.lower() not in _PROMOTORES_EXCLUIDOS
        values.append((cid, prom or None, es_activo, now))
        if es_activo:
            activos += 1
        else:
            inactivos += 1

    with pg_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO seg_clientes_atributos (cliente, promotor, activo, updated_at)
                   VALUES %s
                   ON CONFLICT (cliente) DO UPDATE SET
                       promotor   = EXCLUDED.promotor,
                       activo     = EXCLUDED.activo,
                       updated_at = EXCLUDED.updated_at""",
                values, page_size=500,
            )
            psycopg2.extras.execute_values(
                cur,
                """UPDATE clientes AS c
                   SET fuerza_venta_1_dias_visita = data.promotor,
                       activo_maestro = data.activo,
                       desactivado_en = CASE
                           WHEN data.activo THEN NULL
                           ELSE COALESCE(c.desactivado_en, data.updated_at)
                       END
                   FROM (VALUES %s) AS data(cliente, promotor, activo, updated_at)
                   WHERE c.cliente = data.cliente""",
                values, page_size=500,
            )
    _use_live_plan_source()
    return {'actualizados': len(values), 'activos': activos, 'inactivos': inactivos}


def bulk_upsert_cliente_geografia(rows: list[dict]) -> int:
    ensure_tables()
    batch: list[tuple[str, Any, Any, Any, Any, datetime]] = []
    for row in rows or []:
        cid = str(row.get('cliente_id') or row.get('cliente') or '').strip()
        if not cid:
            continue
        batch.append((
            cid,
            row.get('latitud'),
            row.get('longitud'),
            row.get('localidad'),
            row.get('sucursal'),
            datetime.now(),
        ))
    if not batch:
        return 0
    with pg_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO cliente_geografia
                   (cliente_id, latitud, longitud, localidad, sucursal, updated_at)
                   VALUES %s
                   ON CONFLICT (cliente_id) DO UPDATE SET
                       latitud = EXCLUDED.latitud,
                       longitud = EXCLUDED.longitud,
                       localidad = EXCLUDED.localidad,
                       sucursal = EXCLUDED.sucursal,
                       updated_at = NOW()""",
                batch,
                page_size=1000,
            )
    return len(batch)


def _dict_rows(cur) -> list[dict]:
    return [dict(r) for r in (cur.fetchall() or [])]


_DPO_CACHE_COLUMNS = (
    'cliente', 'descripcion_cliente', 'sucursal', 'sucursal_nombre', 'localidad',
    'autoelevador', 'cluster_dpo', 'subcluster_logistico',
    'ingreso', 'ventas_anio_actual', 'ventas_anio_anterior',
    'venta_anio_base', 'venta_base_mismo_per', 'venta_ytd', 'hl_ytd',
    'bultos_ytd', 'pallets_ytd', 'up_ytd', 'pedidos_ytd',
    'dropsize_bultos_ytd', 'ticket_promedio_ytd', 'rechazos_ytd',
    'pct_rechazo_pedidos', 'crecimiento_pct', 'nps_valor', 'rmd_valor',
    'otif_valor',
    'costo_entrega', 'costo_almacen', 'costo_logistico_total',
    'margen_logistico_proxy', 'ratio_costo_logistico_pct',
    'p25_ingresos', 'p50_ingresos', 'p75_ingresos',
    'p25_crecimiento', 'p50_crecimiento', 'p75_crecimiento',
    'umbral_venta_alta', 'umbral_venta_baja', 'umbral_crecimiento',
    'score_total', 'dim_negocio', 'dim_productividad', 'dim_servicio',
    'dim_rentabilidad', 'dim_geo', 'pts_venta', 'pts_hl', 'pts_crecimiento',
    'pts_dropsize', 'pts_rechazos', 'pts_rmd', 'pts_nps',
    'plan_servicio', 'accion_prioritaria', 'alerta_operativa',
    'prioridad_gestion',
)
_DPO_CACHE_SELECT = ', '.join(_DPO_CACHE_COLUMNS)


def _dpo_cache_has_rows() -> bool:
    def _load() -> bool:
        with pg_cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM seg_cliente_dpo_cache LIMIT 1) AS ok")
            row = cur.fetchone()
        return bool(row and row.get('ok'))

    return bool(cache_svc.get_or_set('segmentacion:dpo_cache_has_rows', _load, ttl_seconds=30))


def _light_plan_cache_key() -> str:
    return 'segmentacion:plan_light:v2'


def _compute_plan_servicio_light_rows() -> list[dict]:
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SET LOCAL statement_timeout = '90000ms'")
            cur.execute(
                f"""SELECT {_DPO_CACHE_SELECT}
                    FROM vw_cliente_plan_servicio
                    ORDER BY prioridad_gestion, venta_ytd DESC NULLS LAST"""
            )
            return _dict_rows(cur)


def _compute_plan_servicio_light_rows_legacy() -> list[dict]:
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SET LOCAL statement_timeout = '90000ms'")
            cur.execute(
                    """
                    WITH params AS (
                        SELECT
                            sp.costo_entrega_hl,
                            sp.costo_almacen_hl,
                            COALESCE(pc.fecha_desde, make_date(sp.anio_ytd, 1, 1)) AS fecha_desde,
                            COALESCE(
                                pc.fecha_hasta,
                                (make_date(
                                    sp.anio_ytd,
                                    COALESCE(sp.mes_ytd_hasta, EXTRACT(MONTH FROM CURRENT_DATE)::INT),
                                    1
                                ) + interval '1 month - 1 day')::date
                            ) AS fecha_hasta,
                            COALESCE(pc.fecha_base_desde, make_date(sp.anio_base, 1, 1)) AS fecha_base_desde,
                            COALESCE(
                                pc.fecha_base_hasta,
                                (make_date(
                                    sp.anio_base,
                                    COALESCE(sp.mes_ytd_hasta, EXTRACT(MONTH FROM CURRENT_DATE)::INT),
                                    1
                                ) + interval '1 month - 1 day')::date
                            ) AS fecha_base_hasta
                        FROM (
                            SELECT *
                            FROM seg_parametros
                            WHERE activo
                            ORDER BY (sucursal_id IS NULL) DESC, id DESC
                            LIMIT 1
                        ) sp
                        LEFT JOIN LATERAL (
                            SELECT *
                            FROM seg_periodos_calculo
                            WHERE activo AND empresa_id = sp.empresa_id
                            ORDER BY id DESC
                            LIMIT 1
                        ) pc ON TRUE
                    ),
                    ytd AS (
                        SELECT
                            NULLIF(TRIM(v.cliente),'') AS cliente,
                            COALESCE(NULLIF(TRIM(v.sucursal),''),'1') AS sucursal,
                            MAX(COALESCE(NULLIF(TRIM(v.descripcion_cliente),''), NULLIF(TRIM(v.descripcion_detallada_cliente),''), '')) AS descripcion_cliente,
                            SUM(COALESCE(v.importe_neto,0)) AS venta_ytd,
                            SUM(COALESCE(v.unidad_medida,0)) AS hl_ytd,
                            SUM(COALESCE(v.bultos,0)) AS bultos_ytd,
                            SUM(CASE WHEN COALESCE(a.bultos_por_pallet,0)>0
                                     THEN COALESCE(v.bultos,0)/a.bultos_por_pallet ELSE 0 END) AS pallets_ytd,
                            SUM(COALESCE(v.unidad_paquete,0)) AS up_ytd,
                            COUNT(DISTINCT v.fecha::TEXT||'|'||NULLIF(TRIM(v.cliente),'')) AS pedidos_ytd,
                            SUM(CASE WHEN COALESCE(v.bultos_rechazados,0)>0
                                       OR COALESCE(v.unidad_medida_rechazado,0)>0
                                       OR COALESCE(v.unidad_paquete_rechazado,0)>0
                                     THEN 1 ELSE 0 END) AS rechazos_ytd,
                            BOOL_OR(
                                LOWER(TRIM(COALESCE(v.descripcion_ruta,''))) LIKE '%%temp%%'
                                OR LOWER(TRIM(COALESCE(v.descripcion_detallada_ruta,''))) LIKE '%%temp%%'
                            ) AS es_ruta_temp
                        FROM ventas_detalle v
                        CROSS JOIN params p
                        JOIN articulos a ON a.id_articulo = v.id_articulo
                        WHERE v.fecha BETWEEN p.fecha_desde AND p.fecha_hasta
                          AND LOWER(TRIM(COALESCE(a.tipo_producto,'')))='mercaderia'
                          AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%%'
                          AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%%'
                          AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%%'
                          AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%%'
                          AND NULLIF(TRIM(v.cliente),'') IS NOT NULL
                        GROUP BY 1, 2
                    ),
                    prev AS (
                        SELECT
                            NULLIF(TRIM(v.cliente),'') AS cliente,
                            COALESCE(NULLIF(TRIM(v.sucursal),''),'1') AS sucursal,
                            SUM(COALESCE(v.importe_neto,0)) AS venta_base_mismo_per
                        FROM ventas_detalle v
                        CROSS JOIN params p
                        JOIN articulos a ON a.id_articulo = v.id_articulo
                        WHERE v.fecha BETWEEN p.fecha_base_desde AND p.fecha_base_hasta
                          AND LOWER(TRIM(COALESCE(a.tipo_producto,'')))='mercaderia'
                          AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%%'
                          AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%%'
                          AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%%'
                          AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%%'
                          AND NULLIF(TRIM(v.cliente),'') IS NOT NULL
                        GROUP BY 1, 2
                    ),
                    joined AS (
                        SELECT
                            COALESCE(y.cliente, p.cliente) AS cliente,
                            COALESCE(y.sucursal, p.sucursal) AS sucursal,
                            COALESCE(y.descripcion_cliente, COALESCE(y.cliente, p.cliente), '') AS descripcion_cliente,
                            COALESCE(y.venta_ytd,0) AS venta_ytd,
                            COALESCE(p.venta_base_mismo_per,0) AS venta_base_mismo_per,
                            CASE WHEN COALESCE(p.venta_base_mismo_per,0)>0
                                 THEN ROUND(((COALESCE(y.venta_ytd,0)-p.venta_base_mismo_per)/p.venta_base_mismo_per*100)::NUMERIC,2)
                                 ELSE NULL END AS crecimiento_pct,
                            COALESCE(y.hl_ytd,0) AS hl_ytd,
                            COALESCE(y.bultos_ytd,0) AS bultos_ytd,
                            COALESCE(y.pallets_ytd,0) AS pallets_ytd,
                            COALESCE(y.up_ytd,0) AS up_ytd,
                            COALESCE(y.pedidos_ytd,0) AS pedidos_ytd,
                            COALESCE(y.rechazos_ytd,0) AS rechazos_ytd,
                            COALESCE(y.es_ruta_temp,FALSE) AS es_ruta_temp
                        FROM ytd y
                        FULL OUTER JOIN prev p ON p.cliente = y.cliente AND p.sucursal = y.sucursal
                    ),
                    activos AS (
                        SELECT
                            j.*,
                            COALESCE(NULLIF(TRIM(c.nombre_fantasia),''), NULLIF(TRIM(c.razon_social),''), j.descripcion_cliente, j.cliente) AS cliente_nombre,
                            COALESCE(NULLIF(TRIM(c.localidad),''), 'Sin localidad') AS localidad,
                            COALESCE(NULLIF(TRIM(s.nombre),''), j.sucursal) AS sucursal_nombre,
                            COALESCE(cae.autoelevador, ca.autoelevador, FALSE) AS autoelevador,
                            ca.nps_valor,
                            ca.rmd_valor
                        FROM joined j
                        JOIN clientes c ON c.cliente = j.cliente
                                      AND COALESCE(NULLIF(TRIM(c.sucursal),''), j.sucursal) = j.sucursal
                        LEFT JOIN sucursales s ON s.id = j.sucursal
                        LEFT JOIN cliente_autoelevador cae ON cae.is_cliente = j.cliente
                        LEFT JOIN seg_clientes_atributos ca ON ca.cliente = j.cliente
                        WHERE COALESCE(c.activo_maestro, TRUE) = TRUE
                          AND COALESCE(LOWER(TRIM(c.anulado)), '') IN ('no','n','0','false','f')
                          AND NULLIF(TRIM(COALESCE(c.fuerza_venta_1_dias_visita, '')), '') IS NOT NULL
                          AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') <> 'dom'
                          AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') NOT LIKE '%%oficina%%'
                          AND NOT j.es_ruta_temp
                          AND (j.venta_ytd > 0 OR j.venta_base_mismo_per > 0)
                    ),
                    pct AS (
                        SELECT
                            percentile_cont(0.25) WITHIN GROUP (ORDER BY venta_ytd) AS p25_ingresos,
                            percentile_cont(0.50) WITHIN GROUP (ORDER BY venta_ytd) AS p50_ingresos,
                            percentile_cont(0.75) WITHIN GROUP (ORDER BY venta_ytd) AS p75_ingresos,
                            percentile_cont(0.25) WITHIN GROUP (ORDER BY COALESCE(crecimiento_pct,0)) AS p25_crecimiento,
                            percentile_cont(0.50) WITHIN GROUP (ORDER BY COALESCE(crecimiento_pct,0)) AS p50_crecimiento,
                            percentile_cont(0.75) WITHIN GROUP (ORDER BY COALESCE(crecimiento_pct,0)) AS p75_crecimiento
                        FROM activos
                    )
                    SELECT
                        a.cliente,
                        a.cliente_nombre AS descripcion_cliente,
                        a.sucursal,
                        a.sucursal_nombre,
                        a.localidad,
                        a.autoelevador,
                        a.venta_ytd AS ingreso,
                        a.venta_ytd AS ventas_anio_actual,
                        a.venta_base_mismo_per AS ventas_anio_anterior,
                        a.venta_base_mismo_per AS venta_anio_base,
                        a.venta_base_mismo_per,
                        a.venta_ytd,
                        a.crecimiento_pct,
                        a.hl_ytd,
                        a.bultos_ytd,
                        a.pallets_ytd,
                        a.up_ytd,
                        a.pedidos_ytd,
                        CASE WHEN a.pedidos_ytd > 0 THEN ROUND((a.bultos_ytd/a.pedidos_ytd)::NUMERIC,2) ELSE 0 END AS dropsize_bultos_ytd,
                        CASE WHEN a.pedidos_ytd > 0 THEN ROUND((a.venta_ytd/a.pedidos_ytd)::NUMERIC,2) ELSE 0 END AS ticket_promedio_ytd,
                        a.rechazos_ytd,
                        CASE WHEN a.pedidos_ytd > 0 THEN ROUND((a.rechazos_ytd::NUMERIC/a.pedidos_ytd*100),2) ELSE 0 END AS pct_rechazo_pedidos,
                        a.nps_valor,
                        a.rmd_valor,
                        ROUND((a.hl_ytd * p.costo_entrega_hl)::NUMERIC,2) AS costo_entrega,
                        ROUND((a.hl_ytd * p.costo_almacen_hl)::NUMERIC,2) AS costo_almacen,
                        ROUND((a.hl_ytd * (p.costo_entrega_hl + p.costo_almacen_hl))::NUMERIC,2) AS costo_logistico_total,
                        ROUND((a.venta_ytd - a.hl_ytd * (p.costo_entrega_hl + p.costo_almacen_hl))::NUMERIC,2) AS margen_logistico_proxy,
                        CASE WHEN a.venta_ytd > 0
                             THEN ROUND((a.hl_ytd * (p.costo_entrega_hl + p.costo_almacen_hl) / a.venta_ytd * 100)::NUMERIC,2)
                             ELSE 0 END AS ratio_costo_logistico_pct,
                        pct.p25_ingresos,
                        pct.p50_ingresos,
                        pct.p75_ingresos,
                        pct.p25_crecimiento,
                        pct.p50_crecimiento,
                        pct.p75_crecimiento,
                        pct.p75_ingresos AS umbral_venta_alta,
                        pct.p25_ingresos AS umbral_venta_baja,
                        pct.p50_crecimiento AS umbral_crecimiento,
                        CASE
                            WHEN a.venta_ytd >= pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p50_crecimiento THEN 'Ganador'
                            WHEN a.venta_ytd < pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p75_crecimiento THEN 'En crecimiento'
                            WHEN a.venta_ytd <= pct.p25_ingresos
                             AND COALESCE(a.crecimiento_pct,0) <= pct.p25_crecimiento THEN 'Ventas bajas'
                            ELSE 'Basico'
                        END AS cluster_dpo,
                        CASE
                            WHEN a.rechazos_ytd > 0 AND a.pedidos_ytd > 0 AND (a.rechazos_ytd::NUMERIC/a.pedidos_ytd*100) > 20 THEN 'Complejo'
                            WHEN COALESCE(a.crecimiento_pct,0) > 15 THEN 'Alto potencial'
                            WHEN a.autoelevador THEN 'Eficiente'
                            ELSE 'Estandar'
                        END AS subcluster_logistico,
                        0::NUMERIC AS score_total,
                        0::NUMERIC AS dim_negocio,
                        0::NUMERIC AS dim_productividad,
                        0::NUMERIC AS dim_servicio,
                        0::NUMERIC AS dim_rentabilidad,
                        0::NUMERIC AS dim_geo,
                        0::NUMERIC AS pts_venta,
                        0::NUMERIC AS pts_hl,
                        0::NUMERIC AS pts_crecimiento,
                        0::NUMERIC AS pts_dropsize,
                        0::NUMERIC AS pts_rechazos,
                        0::NUMERIC AS pts_rmd,
                        0::NUMERIC AS pts_nps,
                        CASE
                            WHEN a.venta_ytd >= pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p50_crecimiento
                                THEN 'Prioridad inventario - ventanas cortas - express habilitado - SLA premium'
                            WHEN a.venta_ytd < pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p75_crecimiento
                                THEN 'Potenciar servicio - flex habilitado - mayor disponibilidad'
                            WHEN a.venta_ytd <= pct.p25_ingresos
                             AND COALESCE(a.crecimiento_pct,0) <= pct.p25_crecimiento
                                THEN 'Consolidar rutas - revisar frecuencia - ventanas amplias - reducir costo'
                            ELSE 'Servicio estandar - optimizacion de frecuencia'
                        END AS plan_servicio,
                        CASE
                            WHEN a.venta_ytd <= pct.p25_ingresos THEN 'Revisar frecuencia y consolidacion'
                            WHEN COALESCE(a.crecimiento_pct,0) >= pct.p75_crecimiento THEN 'Priorizar desarrollo comercial'
                            ELSE 'Monitorear mensualmente'
                        END AS accion_prioritaria,
                        CASE
                            WHEN a.rechazos_ytd > 0 AND a.pedidos_ytd > 0 AND (a.rechazos_ytd::NUMERIC/a.pedidos_ytd*100) > 20
                                THEN 'CRITICO: tasa de rechazo > 20 %'
                            WHEN COALESCE(a.crecimiento_pct,0) < -30 THEN 'ALERTA: caida de venta > 30 %'
                            ELSE NULL
                        END AS alerta_operativa,
                        CASE
                            WHEN a.venta_ytd >= pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p50_crecimiento THEN 1
                            WHEN a.venta_ytd < pct.p75_ingresos
                             AND COALESCE(a.crecimiento_pct,0) >= pct.p75_crecimiento THEN 2
                            WHEN a.venta_ytd <= pct.p25_ingresos
                             AND COALESCE(a.crecimiento_pct,0) <= pct.p25_crecimiento THEN 4
                            ELSE 3
                        END AS prioridad_gestion
                    FROM activos a
                    CROSS JOIN pct
                    CROSS JOIN params p
                    ORDER BY venta_ytd DESC NULLS LAST
                    """
            )
            return _dict_rows(cur)


def _get_plan_servicio_light_rows() -> list[dict]:
    def _load() -> list[dict]:
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"""
                    SELECT {_DPO_CACHE_SELECT}
                    FROM seg_cliente_dpo_cache
                    ORDER BY venta_ytd DESC NULLS LAST
                """)
                cached = _dict_rows(cur)
                if cached:
                    return cached
        return _compute_plan_servicio_light_rows()

    return cache_svc.get_or_set(_light_plan_cache_key(), _load, ttl_seconds=120)


def _filter_light_plan(
    rows: list[dict],
    sucursal: str | None = None,
    cluster: str | None = None,
) -> list[dict]:
    cluster = _normalize_cluster_filter(cluster)
    result = rows
    if sucursal and sucursal != 'TODAS':
        result = [r for r in result if str(r.get('sucursal') or '') == str(sucursal)]
    if cluster:
        result = [r for r in result if r.get('cluster_dpo') == cluster]
    return result


def _round_num(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value or 0), digits)
    except (TypeError, ValueError):
        return 0.0


def _aggregate_light_plan(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    grouped: dict[tuple[Any, ...], dict] = {}
    for row in rows:
        key = tuple(row.get(k) for k in keys)
        item = grouped.setdefault(key, {
            **{k: row.get(k) for k in keys},
            'cantidad_clientes': 0,
            'venta_total_ytd': 0.0,
            'hl_total_ytd': 0.0,
            'costo_logistico_total': 0.0,
            'rechazos_total': 0.0,
            'pedidos_total': 0.0,
            '_pct_rechazo': [],
            '_dropsize': [],
            '_crecimiento': [],
            '_rmd': [],
            '_otif': [],
            '_nps': [],
            '_score': [],
        })
        item['cantidad_clientes'] += 1
        item['venta_total_ytd'] += float(row.get('venta_ytd') or 0)
        item['hl_total_ytd'] += float(row.get('hl_ytd') or 0)
        item['costo_logistico_total'] += float(row.get('costo_logistico_total') or 0)
        item['rechazos_total'] += float(row.get('rechazos_ytd') or 0)
        item['pedidos_total'] += float(row.get('pedidos_ytd') or 0)
        item['_pct_rechazo'].append(float(row.get('pct_rechazo_pedidos') or 0))
        item['_dropsize'].append(float(row.get('dropsize_bultos_ytd') or 0))
        item['_crecimiento'].append(float(row.get('crecimiento_pct') or 0))
        if row.get('rmd_valor') is not None:
            item['_rmd'].append(float(row.get('rmd_valor') or 0))
        if row.get('otif_valor') is not None:
            item['_otif'].append(float(row.get('otif_valor') or 0))
        if row.get('nps_valor') is not None:
            item['_nps'].append(float(row.get('nps_valor') or 0))
        item['_score'].append(float(row.get('score_total') or 0))

    totals_by_sucursal: dict[Any, float] = {}
    for item in grouped.values():
        sucursal = item.get('sucursal')
        totals_by_sucursal[sucursal] = totals_by_sucursal.get(sucursal, 0.0) + item['venta_total_ytd']

    result = []
    for item in grouped.values():
        def avg(values: list[float]) -> float:
            return round(sum(values) / len(values), 2) if values else 0.0

        venta_total = item['venta_total_ytd']
        suc_total = totals_by_sucursal.get(item.get('sucursal'), 0.0)
        cleaned = {k: v for k, v in item.items() if not k.startswith('_')}
        cleaned.update({
            'venta_total_ytd': round(venta_total, 2),
            'hl_total_ytd': round(item['hl_total_ytd'], 4),
            'costo_logistico_total': round(item['costo_logistico_total'], 2),
            'rechazos_total': round(item['rechazos_total'], 0),
            'pedidos_total': round(item['pedidos_total'], 0),
            'pct_rechazo_prom': avg(item['_pct_rechazo']),
            'dropsize_prom': avg(item['_dropsize']),
            'crecimiento_prom_pct': avg(item['_crecimiento']),
            'rmd_prom': avg(item['_rmd']),
            'otif_prom': avg(item['_otif']),
            'nps_prom': avg(item['_nps']),
            'score_prom': avg(item['_score']),
            'pct_venta_en_sucursal': round((venta_total / suc_total * 100), 2) if suc_total else 0.0,
        })
        result.append(cleaned)
    return result


def get_metricas_clientes(
    sucursal: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    ensure_tables()
    filters = "WHERE 1=1"
    params: dict[str, Any] = {'lim': limit, 'off': offset}
    if sucursal and sucursal != 'TODAS':
        filters += " AND sucursal = %(suc)s"
        params['suc'] = sucursal
    with pg_cursor() as cur:
        cur.execute(
            f"SELECT * FROM vw_cliente_metricas {filters} "
            "ORDER BY venta_ytd DESC NULLS LAST LIMIT %(lim)s OFFSET %(off)s",
            params,
        )
        return _dict_rows(cur)


def get_clientes_activos_dpo(sucursal: str | None = None, limit: int = 1000) -> list[dict]:
    ensure_tables()
    params: dict[str, Any] = {'lim': limit}
    where = 'WHERE 1=1'
    if sucursal and sucursal != 'TODAS':
        where += ' AND sucursal = %(suc)s'
        params['suc'] = sucursal
    with pg_cursor() as cur:
        cur.execute(
            f"""SELECT *
                FROM vw_clientes_activos_dpo
                {where}
                ORDER BY sucursal, cliente_id
                LIMIT %(lim)s""",
            params,
        )
        return _dict_rows(cur)


def get_clusters(
    sucursal: str | None = None,
    cluster: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    ensure_tables()
    if _dpo_cache_has_rows():
        conds, params = ['1=1'], {'lim': limit, 'off': offset}
        cluster = _normalize_cluster_filter(cluster)
        if sucursal and sucursal != 'TODAS':
            conds.append('sucursal = %(suc)s')
            params['suc'] = sucursal
        if cluster:
            conds.append('cluster_dpo = %(cl)s')
            params['cl'] = cluster
        with pg_cursor() as cur:
            cur.execute(
                f"""SELECT {_DPO_CACHE_SELECT}
                    FROM seg_cliente_dpo_cache
                    WHERE {' AND '.join(conds)}
                    ORDER BY venta_ytd DESC NULLS LAST
                    LIMIT %(lim)s OFFSET %(off)s""",
                params,
            )
            return _dict_rows(cur)
    if not _plan_cache_populated():
        rows = _filter_light_plan(_get_plan_servicio_light_rows(), sucursal, cluster)
        return rows[offset:offset + limit]
    conds, params = ['1=1'], {}
    cluster = _normalize_cluster_filter(cluster)
    if sucursal and sucursal != 'TODAS':
        conds.append('sucursal = %(suc)s')
        params['suc'] = sucursal
    if cluster:
        conds.append('cluster_dpo = %(cl)s')
        params['cl'] = cluster
    params.update({'lim': limit, 'off': offset})
    where = ' AND '.join(conds)
    with pg_cursor() as cur:
        cur.execute(
            f"SELECT * FROM vw_cliente_cluster_dpo WHERE {where} "
            "ORDER BY venta_ytd DESC NULLS LAST LIMIT %(lim)s OFFSET %(off)s",
            params,
        )
        return _dict_rows(cur)


def get_plan_servicio(
    sucursal: str | None = None,
    cluster: str | None = None,
    solo_alertas: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    ensure_tables()
    if _dpo_cache_has_rows():
        conds, params = ['1=1'], {'lim': limit, 'off': offset}
        cluster = _normalize_cluster_filter(cluster)
        if sucursal and sucursal != 'TODAS':
            conds.append('sucursal = %(suc)s')
            params['suc'] = sucursal
        if cluster:
            conds.append('cluster_dpo = %(cl)s')
            params['cl'] = cluster
        if solo_alertas:
            conds.append('alerta_operativa IS NOT NULL')
        with pg_cursor() as cur:
            cur.execute(
                f"""SELECT {_DPO_CACHE_SELECT}
                    FROM seg_cliente_dpo_cache
                    WHERE {' AND '.join(conds)}
                    ORDER BY prioridad_gestion, venta_ytd DESC NULLS LAST
                    LIMIT %(lim)s OFFSET %(off)s""",
                params,
            )
            return _dict_rows(cur)
    if not _plan_cache_populated():
        rows = _filter_light_plan(_get_plan_servicio_light_rows(), sucursal, cluster)
        if solo_alertas:
            rows = [r for r in rows if r.get('alerta_operativa')]
        rows = sorted(
            rows,
            key=lambda r: (
                int(r.get('prioridad_gestion') or 7),
                -float(r.get('venta_ytd') or 0),
            ),
        )
        return rows[offset:offset + limit]
    conds, params = ['1=1'], {}
    cluster = _normalize_cluster_filter(cluster)
    if sucursal and sucursal != 'TODAS':
        conds.append('sucursal = %(suc)s')
        params['suc'] = sucursal
    if cluster:
        conds.append('cluster_dpo = %(cl)s')
        params['cl'] = cluster
    if solo_alertas:
        conds.append('alerta_operativa IS NOT NULL')
    params.update({'lim': limit, 'off': offset})
    where = ' AND '.join(conds)
    source = _plan_source()
    try:
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = '45000ms'")
                cur.execute(
                    f"SELECT * FROM {source} WHERE {where} "
                    "ORDER BY prioridad_gestion, score_total DESC NULLS LAST "
                    "LIMIT %(lim)s OFFSET %(off)s",
                    params,
                )
                return _dict_rows(cur)
    except Exception:
        return []


def get_resumen_sucursal() -> list[dict]:
    ensure_tables()
    if _dpo_cache_has_rows():
        with pg_cursor() as cur:
            cur.execute(
                """WITH agg AS (
                    SELECT sucursal,
                           COALESCE(MAX(NULLIF(sucursal_nombre,'')), sucursal) AS sucursal_nombre,
                           cluster_dpo,
                           COUNT(*) AS cantidad_clientes,
                           ROUND(SUM(venta_ytd)::NUMERIC,2) AS venta_total_ytd,
                           ROUND(SUM(hl_ytd)::NUMERIC,4) AS hl_total_ytd,
                           ROUND(SUM(costo_logistico_total)::NUMERIC,2) AS costo_logistico_total,
                           ROUND(SUM(rechazos_ytd)::NUMERIC,0) AS rechazos_total,
                           ROUND(SUM(pedidos_ytd)::NUMERIC,0) AS pedidos_total,
                           ROUND(AVG(pct_rechazo_pedidos)::NUMERIC,2) AS pct_rechazo_prom,
                           ROUND(AVG(dropsize_bultos_ytd)::NUMERIC,2) AS dropsize_prom,
                           ROUND(AVG(ratio_costo_logistico_pct)::NUMERIC,2) AS ratio_costo_prom,
                           ROUND(AVG(COALESCE(crecimiento_pct,0))::NUMERIC,2) AS crecimiento_prom_pct,
                           ROUND(AVG(rmd_valor)::NUMERIC,2) AS rmd_prom,
                           ROUND(AVG(otif_valor)::NUMERIC,2) AS otif_prom,
                           ROUND(AVG(nps_valor)::NUMERIC,2) AS nps_prom,
                           ROUND(AVG(score_total)::NUMERIC,2) AS score_prom
                    FROM seg_cliente_dpo_cache
                    GROUP BY sucursal, cluster_dpo
                )
                SELECT *,
                       ROUND((venta_total_ytd/NULLIF(SUM(venta_total_ytd) OVER (PARTITION BY sucursal),0)*100)::NUMERIC,2)
                           AS pct_venta_en_sucursal
                FROM agg
                ORDER BY sucursal, cluster_dpo"""
            )
            return _dict_rows(cur)
    if not _plan_cache_populated():
        rows = _get_plan_servicio_light_rows()
        result = _aggregate_light_plan(rows, ('sucursal', 'sucursal_nombre', 'cluster_dpo'))
        return sorted(result, key=lambda r: (str(r.get('sucursal') or ''), str(r.get('cluster_dpo') or '')))
    source = _plan_source()
    try:
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = '45000ms'")
                cur.execute(
                    f"""WITH agg AS (
                            SELECT sucursal,
                                   COALESCE(MAX(NULLIF(sucursal_nombre,'')), sucursal) AS sucursal_nombre,
                                   cluster_dpo,
                                   COUNT(*) AS cantidad_clientes,
                                   ROUND(SUM(venta_ytd)::NUMERIC,2) AS venta_total_ytd,
                                   ROUND(SUM(hl_ytd)::NUMERIC,4) AS hl_total_ytd,
                                   ROUND(SUM(costo_logistico_total)::NUMERIC,2) AS costo_logistico_total,
                                   ROUND(SUM(rechazos_ytd)::NUMERIC,0) AS rechazos_total,
                                   ROUND(SUM(pedidos_ytd)::NUMERIC,0) AS pedidos_total,
                                   ROUND(AVG(pct_rechazo_pedidos)::NUMERIC,2) AS pct_rechazo_prom,
                                   ROUND(AVG(dropsize_bultos_ytd)::NUMERIC,2) AS dropsize_prom,
                                   ROUND(AVG(ratio_costo_logistico_pct)::NUMERIC,2) AS ratio_costo_prom,
                                   ROUND(AVG(COALESCE(crecimiento_pct,0))::NUMERIC,2) AS crecimiento_prom_pct,
                                   ROUND(AVG(rmd_valor)::NUMERIC,2) AS rmd_prom,
                                   ROUND(AVG(otif_valor)::NUMERIC,2) AS otif_prom,
                                   ROUND(AVG(nps_valor)::NUMERIC,2) AS nps_prom,
                                   ROUND(AVG(score_total)::NUMERIC,2) AS score_prom
                            FROM {source}
                            GROUP BY sucursal, cluster_dpo
                        )
                        SELECT *,
                               ROUND((venta_total_ytd/NULLIF(SUM(venta_total_ytd) OVER (PARTITION BY sucursal),0)*100)::NUMERIC,2)
                                   AS pct_venta_en_sucursal
                        FROM agg
                        ORDER BY sucursal, cluster_dpo"""
                )
                return _dict_rows(cur)
    except Exception:
        return []


def get_resumen_localidad(sucursal: str | None = None) -> list[dict]:
    ensure_tables()
    if _dpo_cache_has_rows():
        params: dict[str, Any] = {}
        where = 'WHERE 1=1'
        if sucursal and sucursal != 'TODAS':
            where += ' AND sucursal = %(suc)s'
            params['suc'] = sucursal
        with pg_cursor() as cur:
            cur.execute(
                f"""SELECT COALESCE(NULLIF(localidad,''),'Sin localidad') AS localidad,
                           sucursal,
                           COALESCE(MAX(NULLIF(sucursal_nombre,'')), sucursal) AS sucursal_nombre,
                           cluster_dpo,
                           COUNT(*) AS cantidad_clientes,
                           ROUND(SUM(venta_ytd)::NUMERIC,2) AS venta_total_ytd,
                           ROUND(SUM(hl_ytd)::NUMERIC,4) AS hl_total_ytd,
                           ROUND(SUM(costo_logistico_total)::NUMERIC,2) AS costo_logistico_total,
                           ROUND(AVG(pct_rechazo_pedidos)::NUMERIC,2) AS pct_rechazo_prom,
                           ROUND(AVG(dropsize_bultos_ytd)::NUMERIC,2) AS dropsize_prom,
                           ROUND(AVG(COALESCE(crecimiento_pct,0))::NUMERIC,2) AS crecimiento_prom_pct,
                           ROUND(AVG(rmd_valor)::NUMERIC,2) AS rmd_prom,
                           ROUND(AVG(otif_valor)::NUMERIC,2) AS otif_prom,
                           ROUND(AVG(nps_valor)::NUMERIC,2) AS nps_prom,
                           ROUND(AVG(score_total)::NUMERIC,2) AS score_prom
                    FROM seg_cliente_dpo_cache
                    {where}
                    GROUP BY localidad, sucursal, cluster_dpo
                    ORDER BY localidad, cluster_dpo""",
                params,
            )
            return _dict_rows(cur)
    if not _plan_cache_populated():
        rows = _filter_light_plan(_get_plan_servicio_light_rows(), sucursal, None)
        result = _aggregate_light_plan(rows, ('localidad', 'sucursal', 'sucursal_nombre', 'cluster_dpo'))
        return sorted(result, key=lambda r: (str(r.get('localidad') or ''), str(r.get('cluster_dpo') or '')))
    source = _plan_source()
    params: dict = {}
    where = ''
    if sucursal and sucursal != 'TODAS':
        where = 'WHERE sucursal = %(suc)s'
        params['suc'] = sucursal
    try:
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = '45000ms'")
                cur.execute(
                    f"""SELECT COALESCE(NULLIF(localidad,''),'Sin localidad') AS localidad,
                               sucursal,
                               COALESCE(MAX(NULLIF(sucursal_nombre,'')), sucursal) AS sucursal_nombre,
                               cluster_dpo,
                               COUNT(*) AS cantidad_clientes,
                               ROUND(SUM(venta_ytd)::NUMERIC,2) AS venta_total_ytd,
                               ROUND(SUM(hl_ytd)::NUMERIC,4) AS hl_total_ytd,
                               ROUND(SUM(costo_logistico_total)::NUMERIC,2) AS costo_logistico_total,
                               ROUND(AVG(pct_rechazo_pedidos)::NUMERIC,2) AS pct_rechazo_prom,
                               ROUND(AVG(dropsize_bultos_ytd)::NUMERIC,2) AS dropsize_prom,
                               ROUND(AVG(COALESCE(crecimiento_pct,0))::NUMERIC,2) AS crecimiento_prom_pct,
                               ROUND(AVG(rmd_valor)::NUMERIC,2) AS rmd_prom,
                               ROUND(AVG(otif_valor)::NUMERIC,2) AS otif_prom,
                               ROUND(AVG(nps_valor)::NUMERIC,2) AS nps_prom,
                               ROUND(AVG(score_total)::NUMERIC,2) AS score_prom
                        FROM {source}
                        {where}
                        GROUP BY localidad, sucursal, cluster_dpo
                        ORDER BY localidad, cluster_dpo""",
                    params,
                )
                return _dict_rows(cur)
    except Exception:
        return []


def get_resumen_activos_localidad(sucursal: str | None = None) -> list[dict]:
    ensure_tables()
    params: dict[str, Any] = {}
    where = 'WHERE 1=1'
    if sucursal and sucursal != 'TODAS':
        where += " AND COALESCE(NULLIF(TRIM(c.sucursal),''), '1') = %(suc)s"
        params['suc'] = sucursal
    try:
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = '45000ms'")
                cur.execute(
                    f"""WITH agg AS (
                            SELECT
                                COALESCE(NULLIF(TRIM(c.sucursal),''), '1') AS sucursal,
                                COALESCE(NULLIF(TRIM(s.nombre),''), COALESCE(NULLIF(TRIM(c.sucursal),''), '1')) AS sucursal_nombre,
                                COALESCE(NULLIF(TRIM(c.localidad),''), 'Sin localidad') AS localidad,
                                COUNT(DISTINCT c.cliente)::INT AS clientes_activos_localidad
                            FROM clientes c
                            LEFT JOIN sucursales s
                                   ON s.id = COALESCE(NULLIF(TRIM(c.sucursal),''), '1')
                            {where}
                              AND NULLIF(TRIM(c.cliente),'') IS NOT NULL
                              AND COALESCE(c.activo_maestro, TRUE) = TRUE
                              AND COALESCE(LOWER(TRIM(c.anulado)), '') IN ('no','n','0','false','f')
                              AND NULLIF(TRIM(COALESCE(c.fuerza_venta_1_dias_visita, '')), '') IS NOT NULL
                              AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') <> 'dom'
                              AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') NOT LIKE '%%oficina%%'
                            GROUP BY
                                COALESCE(NULLIF(TRIM(c.sucursal),''), '1'),
                                COALESCE(NULLIF(TRIM(s.nombre),''), COALESCE(NULLIF(TRIM(c.sucursal),''), '1')),
                                COALESCE(NULLIF(TRIM(c.localidad),''), 'Sin localidad')
                        )
                        SELECT *,
                               SUM(clientes_activos_localidad) OVER (PARTITION BY sucursal)::INT
                                   AS clientes_activos_sucursal,
                               ROUND((
                                   clientes_activos_localidad::NUMERIC
                                   / NULLIF(SUM(clientes_activos_localidad) OVER (PARTITION BY sucursal), 0)
                                   * 100
                               )::NUMERIC, 2) AS pct_localidad_sucursal
                        FROM agg
                        ORDER BY sucursal, clientes_activos_localidad DESC, localidad""",
                    params,
                )
                return _dict_rows(cur)
    except Exception:
        return []


def get_clientes_mapa(
    sucursal: str | None = None,
    cluster: str | None = None,
    peso: str = 'hl',
    limit: int = 5000,
) -> list[dict]:
    ensure_tables()
    cluster = _normalize_cluster_filter(cluster)
    light_cluster_ids: list[str] | None = None
    if cluster and not _plan_cache_populated():
        light_cluster_ids = [
            str(r.get('cliente') or '')
            for r in _filter_light_plan(_get_plan_servicio_light_rows(), sucursal, cluster)
            if r.get('cliente')
        ]
        if not light_cluster_ids:
            return []
    weight_col = {
        'hl': 'hl',
        'pallets': 'pallets',
        'venta': 'venta',
        'bultos': 'bultos',
    }.get(str(peso or 'hl').lower(), 'hl')
    cache_weight_col = {
        'hl': 'hl_ytd',
        'pallets': 'pallets_ytd',
        'venta': 'venta_ytd',
        'bultos': 'bultos_ytd',
    }.get(str(peso or 'hl').lower(), 'hl_ytd')
    if _dpo_cache_has_rows():
        cache_conds = ['1=1']
        cache_params: dict[str, Any] = {'lim': limit}
        if sucursal and sucursal != 'TODAS':
            cache_conds.append('d.sucursal = %(suc)s')
            cache_params['suc'] = sucursal
        if cluster:
            cache_conds.append('d.cluster_dpo = %(cl)s')
            cache_params['cl'] = cluster
        with pg_cursor() as cur:
            cur.execute(
                f"""WITH base AS (
                        SELECT
                            d.cliente AS cliente_id,
                            d.descripcion_cliente AS cliente_nombre,
                            g.latitud AS geo_latitud,
                            g.longitud AS geo_longitud,
                            REPLACE(REGEXP_REPLACE(TRIM(COALESCE(c.coord_y, c.coord_y_entrega, '')), '[[:space:]]+', '', 'g'), ',', '.') AS coord_y_txt,
                            REPLACE(REGEXP_REPLACE(TRIM(COALESCE(c.coord_x, c.coord_x_entrega, '')), '[[:space:]]+', '', 'g'), ',', '.') AS coord_x_txt,
                            d.hl_ytd AS hl,
                            d.venta_ytd AS venta,
                            d.pallets_ytd AS pallets,
                            d.bultos_ytd AS bultos,
                            d.cluster_dpo,
                            d.autoelevador AS tiene_autoelevador,
                            d.sucursal,
                            d.sucursal_nombre,
                            d.localidad,
                            d.ratio_costo_logistico_pct,
                            d.costo_logistico_total,
                            d.margen_logistico_proxy,
                            d.{cache_weight_col} AS peso_mapa
                        FROM seg_cliente_dpo_cache d
                        JOIN clientes c
                          ON c.cliente = d.cliente
                         AND COALESCE(NULLIF(TRIM(c.sucursal),''), d.sucursal) = d.sucursal
                        LEFT JOIN cliente_geografia g
                          ON g.cliente_id = d.cliente
                         AND COALESCE(NULLIF(TRIM(g.sucursal),''), d.sucursal) = d.sucursal
                        WHERE {' AND '.join(cache_conds)}
                    ),
                    coords AS (
                        SELECT *,
                               CASE WHEN coord_y_txt ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN coord_y_txt::NUMERIC END AS cli_latitud,
                               CASE WHEN coord_x_txt ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN coord_x_txt::NUMERIC END AS cli_longitud
                        FROM base
                    )
                    SELECT
                        cliente_id, cliente_nombre,
                        COALESCE(geo_latitud, cli_latitud) AS latitud,
                        COALESCE(geo_longitud, cli_longitud) AS longitud,
                        hl, venta, pallets, bultos, cluster_dpo, tiene_autoelevador,
                        sucursal, sucursal_nombre, localidad,
                        ratio_costo_logistico_pct, costo_logistico_total,
                        margen_logistico_proxy, COALESCE(peso_mapa, 0) AS peso_mapa
                    FROM coords
                    WHERE COALESCE(geo_latitud, cli_latitud) BETWEEN -90 AND 90
                      AND COALESCE(geo_longitud, cli_longitud) BETWEEN -180 AND 180
                      AND NOT (
                          COALESCE(geo_latitud, cli_latitud) = 0
                          AND COALESCE(geo_longitud, cli_longitud) = 0
                      )
                    ORDER BY COALESCE(peso_mapa, 0) DESC
                    LIMIT %(lim)s""",
                cache_params,
            )
            return _dict_rows(cur)
    conds = ['1=1']
    params: dict[str, Any] = {'lim': limit}
    if sucursal and sucursal != 'TODAS':
        conds.append('sucursal = %(suc)s')
        params['suc'] = sucursal
    if cluster:
        conds.append('cluster_dpo = %(cl)s')
        params['cl'] = cluster
    where = ' AND '.join(conds)
    try:
        if not _plan_cache_populated():
            raise RuntimeError('cache DPO no disponible para mapa enriquecido')
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = '45000ms'")
                cur.execute(
                    f"""SELECT *,
                               COALESCE({weight_col}, 0) AS peso_mapa
                        FROM vw_clientes_mapa
                        WHERE {where}
                        ORDER BY COALESCE({weight_col}, 0) DESC
                        LIMIT %(lim)s""",
                    params,
                )
                return _dict_rows(cur)
    except Exception:
        # Fallback liviano para evitar timeout en vistas complejas: usa la tabla maestra clientes.
        fallback_where = ['1=1']
        fallback_params: dict[str, Any] = {'lim': limit, 'cluster_label': cluster or 'Sin datos'}
        if sucursal and sucursal != 'TODAS':
            fallback_where.append("COALESCE(NULLIF(TRIM(c.sucursal),''), '1') = %(suc)s")
            fallback_params['suc'] = sucursal
        if light_cluster_ids is not None:
            fallback_where.append("c.cliente = ANY(%(cluster_clientes)s)")
            fallback_params['cluster_clientes'] = light_cluster_ids
        fallback_sql = ' AND '.join(fallback_where)
        with pg_cursor() as cur:
            cur.execute(
                f"""WITH base AS (
                        SELECT
                            c.cliente AS cliente_id,
                            COALESCE(NULLIF(TRIM(c.nombre_fantasia),''), NULLIF(TRIM(c.razon_social),''), c.cliente) AS cliente_nombre,
                            COALESCE(NULLIF(TRIM(c.sucursal),''), '1') AS sucursal,
                            COALESCE(NULLIF(TRIM(s.nombre),''), COALESCE(NULLIF(TRIM(c.sucursal),''), '1')) AS sucursal_nombre,
                            COALESCE(NULLIF(TRIM(c.localidad),''), 'Sin localidad') AS localidad,
                            COALESCE(ca.autoelevador, sa.autoelevador, FALSE) AS tiene_autoelevador,
                            g.latitud AS geo_latitud,
                            g.longitud AS geo_longitud,
                            REPLACE(REGEXP_REPLACE(TRIM(COALESCE(c.coord_y, c.coord_y_entrega, '')), '[[:space:]]+', '', 'g'), ',', '.') AS coord_y_txt,
                            REPLACE(REGEXP_REPLACE(TRIM(COALESCE(c.coord_x, c.coord_x_entrega, '')), '[[:space:]]+', '', 'g'), ',', '.') AS coord_x_txt
                        FROM clientes c
                        LEFT JOIN sucursales s
                               ON s.id = COALESCE(NULLIF(TRIM(c.sucursal),''), '1')
                        LEFT JOIN cliente_geografia g
                               ON g.cliente_id = c.cliente
                              AND COALESCE(NULLIF(TRIM(g.sucursal),''), COALESCE(NULLIF(TRIM(c.sucursal),''), '1')) = COALESCE(NULLIF(TRIM(c.sucursal),''), '1')
                        LEFT JOIN cliente_autoelevador ca
                               ON ca.is_cliente = c.cliente
                        LEFT JOIN seg_clientes_atributos sa
                               ON sa.cliente = c.cliente
                        WHERE {fallback_sql}
                          AND NULLIF(TRIM(c.cliente),'') IS NOT NULL
                          AND COALESCE(c.activo_maestro, TRUE) = TRUE
                          AND COALESCE(LOWER(TRIM(c.anulado)), '') IN ('no','n','0','false','f')
                          AND NULLIF(TRIM(COALESCE(c.fuerza_venta_1_dias_visita, '')), '') IS NOT NULL
                          AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') <> 'dom'
                          AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') NOT LIKE '%%oficina%%'
                    ),
                    coords AS (
                        SELECT *,
                               CASE WHEN coord_y_txt ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN coord_y_txt::NUMERIC END AS cli_latitud,
                               CASE WHEN coord_x_txt ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN coord_x_txt::NUMERIC END AS cli_longitud
                        FROM base
                    )
                    SELECT
                        cliente_id,
                        cliente_nombre,
                        COALESCE(geo_latitud, cli_latitud) AS latitud,
                        COALESCE(geo_longitud, cli_longitud) AS longitud,
                        0::NUMERIC AS hl,
                        0::NUMERIC AS venta,
                        0::NUMERIC AS pallets,
                        0::NUMERIC AS bultos,
                        %(cluster_label)s::VARCHAR AS cluster_dpo,
                        tiene_autoelevador,
                        sucursal,
                        sucursal_nombre,
                        localidad,
                        0::NUMERIC AS ratio_costo_logistico_pct,
                        0::NUMERIC AS costo_logistico_total,
                        0::NUMERIC AS margen_logistico_proxy,
                        0::NUMERIC AS peso_mapa
                    FROM coords
                    WHERE COALESCE(geo_latitud, cli_latitud) BETWEEN -90 AND 90
                      AND COALESCE(geo_longitud, cli_longitud) BETWEEN -180 AND 180
                      AND NOT (
                          COALESCE(geo_latitud, cli_latitud) = 0
                          AND COALESCE(geo_longitud, cli_longitud) = 0
                      )
                    ORDER BY cliente_id
                    LIMIT %(lim)s""",
                fallback_params,
            )
            return _dict_rows(cur)


def get_autoelevador_resumen(sucursal: str | None = None) -> dict:
    ensure_tables()
    if _dpo_cache_has_rows():
        params: dict[str, Any] = {}
        where = 'WHERE 1=1'
        if sucursal and sucursal != 'TODAS':
            where += ' AND sucursal = %(suc)s'
            params['suc'] = sucursal
        with pg_cursor() as cur:
            cur.execute(
                f"""SELECT
                        COUNT(*)::INT AS clientes_total,
                        COUNT(*)::INT AS clientes_totales,
                        SUM(CASE WHEN autoelevador THEN 1 ELSE 0 END)::INT AS clientes_autoelevador,
                        ROUND(SUM(CASE WHEN autoelevador THEN hl_ytd ELSE 0 END)::NUMERIC, 2) AS hl_autoelevador,
                        ROUND(SUM(CASE WHEN autoelevador THEN costo_logistico_total ELSE 0 END)::NUMERIC, 2) AS costo_autoelevador,
                        0::NUMERIC AS ahorro_estimado,
                        SUM(CASE WHEN autoelevador THEN 0 ELSE COALESCE(pedidos_ytd,0) * 2 END)::BIGINT AS acompanantes_estimados
                    FROM seg_cliente_dpo_cache
                    {where}""",
                params,
            )
            row = dict(cur.fetchone() or {})
        total = int(row.get('clientes_total') or 0)
        auto = int(row.get('clientes_autoelevador') or 0)
        row['pct_clientes_autoelevador'] = round((auto / total * 100), 2) if total else 0.0
        return row
    if not _plan_cache_populated():
        rows = _filter_light_plan(_get_plan_servicio_light_rows(), sucursal, None)
        total = len(rows)
        auto_rows = [r for r in rows if r.get('autoelevador')]
        return {
            'clientes_total': total,
            'clientes_totales': total,
            'clientes_autoelevador': len(auto_rows),
            'pct_clientes_autoelevador': round((len(auto_rows) / total * 100), 2) if total else 0.0,
            'hl_autoelevador': round(sum(float(r.get('hl_ytd') or 0) for r in auto_rows), 2),
            'costo_autoelevador': round(sum(float(r.get('costo_logistico_total') or 0) for r in auto_rows), 2),
            'ahorro_estimado': 0.0,
            'acompanantes_estimados': sum(int(r.get('pedidos_ytd') or 0) * 2 for r in rows if not r.get('autoelevador')),
        }
    params: dict[str, Any] = {}
    where = ''
    if sucursal and sucursal != 'TODAS':
        where = 'WHERE sucursal = %(suc)s'
        params['suc'] = sucursal
    try:
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = '45000ms'")
                cur.execute(
                    f"""SELECT
                            COUNT(*)::INT AS clientes_total,
                            SUM(CASE WHEN tiene_autoelevador THEN 1 ELSE 0 END)::INT AS clientes_autoelevador,
                            ROUND(SUM(CASE WHEN tiene_autoelevador THEN hl ELSE 0 END)::NUMERIC, 2) AS hl_autoelevador,
                            ROUND(SUM(CASE WHEN tiene_autoelevador THEN costo_logistico_ajustado_total ELSE 0 END)::NUMERIC, 2) AS costo_autoelevador,
                            ROUND(SUM(CASE WHEN tiene_autoelevador THEN ahorro_actual_vs_sin_autoelevador ELSE 0 END)::NUMERIC, 2) AS ahorro_estimado,
                            SUM(CASE WHEN tiene_autoelevador THEN 0 ELSE COALESCE(pedidos,0) * 2 END)::BIGINT AS acompanantes_estimados
                        FROM vw_cliente_costo_operativo
                        {where}""",
                    params,
                )
                row = dict(cur.fetchone() or {})
    except Exception:
        # Fallback rapido sin metricas pesadas, evita 500/timeout.
        with pg_cursor() as cur:
            cur.execute(
                f"""SELECT
                        COUNT(DISTINCT a.is_cliente)::INT AS clientes_total,
                        COUNT(DISTINCT CASE WHEN a.autoelevador THEN a.is_cliente END)::INT AS clientes_autoelevador,
                        0::NUMERIC AS hl_autoelevador,
                        0::NUMERIC AS costo_autoelevador,
                        0::NUMERIC AS ahorro_estimado,
                        0::BIGINT AS acompanantes_estimados
                    FROM cliente_autoelevador a
                    LEFT JOIN clientes c ON c.cliente = a.is_cliente
                    WHERE NULLIF(TRIM(c.cliente),'') IS NOT NULL
                      AND COALESCE(c.activo_maestro, TRUE) = TRUE
                      AND COALESCE(LOWER(TRIM(c.anulado)), '') IN ('no','n','0','false','f')
                      AND NULLIF(TRIM(COALESCE(c.fuerza_venta_1_dias_visita, '')), '') IS NOT NULL
                      AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') <> 'dom'
                      AND COALESCE(LOWER(TRIM(c.fuerza_venta_1_dias_visita)), '') NOT LIKE '%%oficina%%'
                      {('AND c.sucursal = %(suc)s' if sucursal and sucursal != 'TODAS' else '')}""",
                ({'suc': sucursal} if sucursal and sucursal != 'TODAS' else {}),
            )
            row = dict(cur.fetchone() or {})
    total = int(row.get('clientes_total') or 0)
    auto = int(row.get('clientes_autoelevador') or 0)
    row['pct_clientes_autoelevador'] = round((auto / total * 100), 2) if total else 0.0
    return row


def get_cliente_cluster_logistico(
    sucursal: str | None = None,
    cluster: str | None = None,
    limit: int = 500,
) -> list[dict]:
    ensure_tables()
    cluster = _normalize_cluster_filter(cluster)
    conds = ['1=1']
    params: dict[str, Any] = {'lim': limit}
    if sucursal and sucursal != 'TODAS':
        conds.append('sucursal = %(suc)s')
        params['suc'] = sucursal
    if cluster:
        conds.append('cluster_dpo = %(cl)s')
        params['cl'] = cluster
    where = ' AND '.join(conds)
    try:
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = '45000ms'")
                cur.execute(
                    f"""SELECT *
                        FROM vw_cliente_cluster_logistico
                        WHERE {where}
                        ORDER BY score_total_operativo DESC NULLS LAST
                        LIMIT %(lim)s""",
                    params,
                )
                return _dict_rows(cur)
    except Exception:
        return []


def get_cliente_detalle(cliente: str) -> dict | None:
    ensure_tables()
    if _dpo_cache_has_rows():
        with pg_cursor() as cur:
            cur.execute(
                f"""SELECT {_DPO_CACHE_SELECT}
                    FROM seg_cliente_dpo_cache
                    WHERE cliente = %(c)s""",
                {'c': cliente},
            )
            row = cur.fetchone()
        if row:
            return dict(row)
    source = _plan_source()
    with pg_cursor() as cur:
        cur.execute(
            f"SELECT * FROM {source} WHERE cliente = %(c)s",
            {'c': cliente},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_evolucion_cluster(cliente: str) -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """SELECT periodo_anio, periodo_mes, cluster_dpo, subcluster_logistico,
                      score_total, venta_ytd, crecimiento_pct,
                      rmd_valor, otif_valor, nps_valor, fecha_calculo
               FROM seg_cliente_cluster_historico
               WHERE cliente = %(c)s
               ORDER BY periodo_anio DESC, periodo_mes DESC""",
            {'c': cliente},
        )
        return _dict_rows(cur)


def get_evolucion_mensual_clusters(
    anio: int | None = None,
    sucursal: str | None = None,
) -> list[dict]:
    ensure_tables()
    conds, params = ['1=1'], {}
    if anio:
        conds.append('periodo_anio = %(anio)s')
        params['anio'] = anio
    if sucursal and sucursal != 'TODAS':
        conds.append('sucursal_id = %(suc)s')
        params['suc'] = sucursal
    where = ' AND '.join(conds)
    with pg_cursor() as cur:
        cur.execute(
            f"""SELECT periodo_anio, periodo_mes, cluster_dpo,
                       COUNT(*) AS clientes,
                       ROUND(SUM(venta_ytd)::NUMERIC,2) AS venta_total,
                       ROUND(AVG(rmd_valor)::NUMERIC,2) AS rmd_prom,
                       ROUND(AVG(otif_valor)::NUMERIC,2) AS otif_prom,
                       ROUND(AVG(nps_valor)::NUMERIC,2) AS nps_prom,
                       ROUND(AVG(score_total)::NUMERIC,2) AS score_prom
                FROM seg_cliente_cluster_historico WHERE {where}
                GROUP BY periodo_anio, periodo_mes, cluster_dpo
                ORDER BY periodo_anio, periodo_mes, cluster_dpo""",
            params,
        )
        return _dict_rows(cur)


def get_auditoria(limit: int = 50) -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            "SELECT * FROM seg_auditoria ORDER BY ejecutado_at DESC LIMIT %(l)s",
            {'l': limit},
        )
        return _dict_rows(cur)


# ─────────────────────────────────────────────────────────────
# Recalcular y guardar histórico
# ─────────────────────────────────────────────────────────────

def _iter_months(
    desde_anio: int,
    desde_mes: int,
    hasta_anio: int,
    hasta_mes: int,
) -> Iterable[tuple[int, int]]:
    if not 1 <= desde_mes <= 12 or not 1 <= hasta_mes <= 12:
        raise ValueError('desde_mes y hasta_mes deben estar entre 1 y 12')
    current = date(int(desde_anio), int(desde_mes), 1)
    end = date(int(hasta_anio), int(hasta_mes), 1)
    if current > end:
        raise ValueError('El periodo desde no puede ser posterior al periodo hasta')
    while current <= end:
        yield current.year, current.month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def _periodo_mensual_payload(anio: int, mes: int, empresa_id: str = '1') -> dict:
    fecha_hasta = date(anio, mes, monthrange(anio, mes)[1])
    return {
        'empresa_id': empresa_id,
        'periodo_anio': anio,
        'periodo_mes': mes,
        'fecha_desde': date(anio, 1, 1),
        'fecha_hasta': fecha_hasta,
        'fecha_base_desde': date(anio - 1, 1, 1),
        'fecha_base_hasta': _same_month_day_previous_year(fecha_hasta),
    }


def _period_end_from_payload(periodo: dict) -> tuple[int, int]:
    fecha_hasta = periodo.get('fecha_hasta')
    if isinstance(fecha_hasta, datetime):
        return fecha_hasta.year, fecha_hasta.month
    if isinstance(fecha_hasta, date):
        return fecha_hasta.year, fecha_hasta.month
    if fecha_hasta:
        parsed = date.fromisoformat(str(fecha_hasta)[:10])
        return parsed.year, parsed.month
    anio = int(periodo.get('periodo_anio') or date.today().year)
    mes = int(periodo.get('periodo_mes') or date.today().month)
    return anio, max(1, min(12, mes))


def recalcular_historico_mensual(
    desde_anio: int = 2025,
    desde_mes: int = 1,
    hasta_anio: int | None = None,
    hasta_mes: int | None = None,
    ejecutado_por: str = 'dashboard_historico',
) -> dict:
    ensure_tables()
    original_periodo = get_periodo_activo()
    empresa_id = str(original_periodo.get('empresa_id') or '1')
    default_hasta_anio, default_hasta_mes = _period_end_from_payload(original_periodo)
    hasta_anio = int(hasta_anio or default_hasta_anio)
    hasta_mes = int(hasta_mes or default_hasta_mes)

    periodos = list(_iter_months(int(desde_anio), int(desde_mes), hasta_anio, hasta_mes))
    resultados: list[dict] = []
    errores: list[dict] = []
    t0 = time.time()

    try:
        for anio, mes in periodos:
            payload = _periodo_mensual_payload(anio, mes, empresa_id)
            try:
                result = recalcular_clusters(
                    anio,
                    mes,
                    f'{ejecutado_por}:{anio}-{mes:02d}',
                    periodo_data=payload,
                )
                resultados.append({
                    'periodo_anio': anio,
                    'periodo_mes': mes,
                    'procesados': result.get('procesados', 0),
                    'por_cluster': result.get('por_cluster', {}),
                    'duracion_ms': result.get('duracion_ms', 0),
                })
            except Exception as exc:
                errores.append({
                    'periodo_anio': anio,
                    'periodo_mes': mes,
                    'error': str(exc),
                })
    finally:
        set_periodo_calculo(original_periodo)
        refresh_segmentacion_cache(f'{ejecutado_por}:restore')

    return {
        'desde_anio': int(desde_anio),
        'desde_mes': int(desde_mes),
        'hasta_anio': hasta_anio,
        'hasta_mes': hasta_mes,
        'periodos_solicitados': len(periodos),
        'periodos_procesados': len(resultados),
        'errores': errores,
        'resultados': resultados,
        'duracion_ms': int((time.time() - t0) * 1000),
    }


def recalcular_clusters(
    periodo_anio: int | None = None,
    periodo_mes: int = 0,
    ejecutado_por: str = 'sistema',
    periodo_data: dict | None = None,
) -> dict:
    """
    Lee vw_cliente_plan_servicio, guarda snapshot en el histórico
    y registra la ejecución en auditoría.

    Args:
        periodo_anio: año del snapshot (ej. 2026)
        periodo_mes: mes (1-12) o 0 para cálculo anual
        ejecutado_por: usuario o proceso que dispara el cálculo

    Returns:
        Resumen con conteos por cluster y tiempo de ejecución.
    """
    ensure_tables()
    t0 = time.time()

    periodo_input = dict(periodo_data or {})
    if periodo_anio is not None:
        periodo_input.setdefault('periodo_anio', periodo_anio)
        periodo_input.setdefault('periodo_mes', periodo_mes)
    periodo = set_periodo_calculo(periodo_input) if periodo_input else get_periodo_activo()
    periodo_anio = int(periodo['periodo_anio'])
    periodo_mes = int(periodo['periodo_mes'])

    # 1. Leer parámetros para auditoría
    params_row = get_parametros()
    version = params_row.get('version_regla', 1)

    # 2. Refrescar cache y usarla como fuente del snapshot
    cache_info = refresh_segmentacion_cache(ejecutado_por)
    with pg_cursor() as cur:
        cur.execute("""
            SELECT cliente, descripcion_cliente, sucursal AS sucursal_id, localidad,
                   cluster_dpo, subcluster_logistico,
                   score_total, dim_negocio, dim_productividad, dim_servicio,
                   dim_rentabilidad, dim_geo,
                   venta_base_mismo_per, venta_ytd, bultos_ytd, pallets_ytd,
                   up_ytd, hl_ytd, rechazos_ytd, nps_valor, rmd_valor, otif_valor,
                   costo_entrega, costo_almacen, margen_logistico_proxy,
                   crecimiento_pct, costo_logistico_total, ratio_costo_logistico_pct,
                   pedidos_ytd, dropsize_bultos_ytd, pct_rechazo_pedidos
            FROM seg_cliente_dpo_cache
            ORDER BY score_total DESC NULLS LAST
        """)
        rows = cur.fetchall()

    if not rows:
        return {'procesados': 0, 'error': 'Sin datos en seg_cliente_dpo_cache'}

    # 3. Conteo por cluster
    conteos: dict[str, int] = {}
    for r in rows:
        conteos[r['cluster_dpo'] or 'Sin clasificar'] = \
            conteos.get(r['cluster_dpo'] or 'Sin clasificar', 0) + 1

    # 4. Batch upsert en historico
    batch = [
        (
            r['cliente'], r['descripcion_cliente'], r['sucursal_id'], r['localidad'],
            periodo_anio, periodo_mes,
            r['cluster_dpo'], r['subcluster_logistico'],
            r['score_total'], r['dim_negocio'], r['dim_productividad'],
            r['dim_servicio'], r['dim_rentabilidad'], r['dim_geo'],
            r['venta_base_mismo_per'], r['venta_ytd'], r['bultos_ytd'],
            r['pallets_ytd'], r['up_ytd'], r['hl_ytd'], r['rechazos_ytd'],
            r['nps_valor'], r['rmd_valor'], r['otif_valor'], r['costo_entrega'],
            r['costo_almacen'], r['margen_logistico_proxy'],
            r['crecimiento_pct'], r['costo_logistico_total'], r['ratio_costo_logistico_pct'],
            r['pedidos_ytd'], r['dropsize_bultos_ytd'], r['pct_rechazo_pedidos'],
            version, ejecutado_por,
        )
        for r in rows
    ]

    duracion = int((time.time() - t0) * 1000)

    with pg_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO seg_cliente_cluster_historico (
                       cliente, descripcion_cliente, sucursal_id, localidad,
                       periodo_anio, periodo_mes,
                       cluster_dpo, subcluster_logistico,
                       score_total, dim_negocio, dim_productividad, dim_servicio,
                       dim_rentabilidad, dim_geo,
                       venta_base_mismo_periodo, venta_ytd, bultos_ytd, pallets_ytd,
                       up_ytd, hl_ytd, rechazos_ytd, nps_valor, rmd_valor, otif_valor,
                       costo_entrega, costo_almacen, margen_logistico_proxy,
                       crecimiento_pct, costo_logistico_total, ratio_costo_logistico,
                       pedidos_ytd, dropsize_ytd, pct_rechazo_pedidos,
                       version_regla, proceso
                   ) VALUES %s
                   ON CONFLICT (cliente, periodo_anio, periodo_mes) DO UPDATE SET
                       cluster_dpo           = EXCLUDED.cluster_dpo,
                       subcluster_logistico  = EXCLUDED.subcluster_logistico,
                       score_total           = EXCLUDED.score_total,
                       dim_negocio           = EXCLUDED.dim_negocio,
                       dim_productividad     = EXCLUDED.dim_productividad,
                       dim_servicio          = EXCLUDED.dim_servicio,
                       dim_rentabilidad      = EXCLUDED.dim_rentabilidad,
                       dim_geo               = EXCLUDED.dim_geo,
                       venta_base_mismo_periodo = EXCLUDED.venta_base_mismo_periodo,
                       venta_ytd             = EXCLUDED.venta_ytd,
                       bultos_ytd            = EXCLUDED.bultos_ytd,
                       pallets_ytd           = EXCLUDED.pallets_ytd,
                       up_ytd                = EXCLUDED.up_ytd,
                       hl_ytd                = EXCLUDED.hl_ytd,
                       rechazos_ytd          = EXCLUDED.rechazos_ytd,
                       nps_valor             = EXCLUDED.nps_valor,
                       rmd_valor             = EXCLUDED.rmd_valor,
                       otif_valor            = EXCLUDED.otif_valor,
                       costo_entrega         = EXCLUDED.costo_entrega,
                       costo_almacen         = EXCLUDED.costo_almacen,
                       margen_logistico_proxy = EXCLUDED.margen_logistico_proxy,
                       crecimiento_pct       = EXCLUDED.crecimiento_pct,
                       costo_logistico_total = EXCLUDED.costo_logistico_total,
                       ratio_costo_logistico = EXCLUDED.ratio_costo_logistico,
                       pedidos_ytd           = EXCLUDED.pedidos_ytd,
                       dropsize_ytd          = EXCLUDED.dropsize_ytd,
                       pct_rechazo_pedidos   = EXCLUDED.pct_rechazo_pedidos,
                       fecha_calculo         = NOW(),
                       version_regla         = EXCLUDED.version_regla,
                       proceso               = EXCLUDED.proceso""",
                batch,
                page_size=500,
            )
            cur.execute(
                """INSERT INTO seg_auditoria (
                       accion, periodo_anio, periodo_mes,
                       clientes_procesados, clientes_ganador, clientes_en_crecimiento,
                       clientes_basico, clientes_ventas_bajas,
                       version_regla, parametros, ejecutado_por, duracion_ms
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    'recalcular_clusters',
                    periodo_anio, periodo_mes,
                    len(rows),
                    conteos.get('Ganador', 0),
                    conteos.get('En crecimiento', 0),
                    conteos.get('Basico', 0),
                    conteos.get('Ventas bajas', 0),
                    version,
                    json.dumps(params_row, default=str),
                    ejecutado_por,
                    duracion_ms := int((time.time() - t0) * 1000),
                ),
            )

    return {
        'procesados': len(rows),
        'por_cluster': conteos,
        'periodo_anio': periodo_anio,
        'periodo_mes': periodo_mes,
        'periodo': periodo,
        'cache': cache_info,
        'version_regla': version,
        'duracion_ms': duracion_ms,
    }
