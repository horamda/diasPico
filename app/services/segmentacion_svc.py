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
from datetime import datetime
from typing import Any

import psycopg2.extras

from app.database import pg_conn, pg_cursor

_TABLES_READY = False

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
    autoelevador    BOOLEAN     DEFAULT FALSE,
    nps_valor       NUMERIC(6,2),
    nps_fecha       DATE,
    rmd_valor       NUMERIC(6,2),
    rmd_fecha       DATE,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMP   NOT NULL DEFAULT NOW()
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
    venta_ytd               NUMERIC(18,2),
    hl_ytd                  NUMERIC(18,4),
    crecimiento_pct         NUMERIC(10,4),
    costo_logistico_total   NUMERIC(18,2),
    ratio_costo_logistico   NUMERIC(8,4),
    pedidos_ytd             INTEGER,
    dropsize_ytd            NUMERIC(10,4),
    pct_rechazo_pedidos     NUMERIC(8,4),
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

# ─────────────────────────────────────────────────────────────
# DDL — vistas (CREATE OR REPLACE)
# Se importan desde el archivo SQL de referencia en producción;
# aquí se recrean en ensure_tables() para arranque automático.
# ─────────────────────────────────────────────────────────────
_VIEWS_SQL = r"""
-- vw_cliente_metricas ----------------------------------------
DROP VIEW IF EXISTS vw_cliente_metricas CASCADE;
CREATE VIEW vw_cliente_metricas AS
WITH params AS (
    SELECT costo_entrega_hl, costo_almacen_hl, anio_base, anio_ytd,
           COALESCE(mes_ytd_hasta, EXTRACT(MONTH FROM CURRENT_DATE)::INT) AS mes_ytd_hasta
    FROM seg_parametros WHERE activo ORDER BY (sucursal_id IS NULL) DESC, id DESC LIMIT 1
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
           v.fecha::TEXT||'|'||NULLIF(TRIM(v.cliente),'') AS pedido_key
    FROM ventas_detalle v
    JOIN articulos a ON a.id_articulo=v.id_articulo
    LEFT JOIN LATERAL (
        SELECT tomar FROM rechazos r
        WHERE LOWER(TRIM(COALESCE(v.motivo_rechazo,'')))=r.motivo_key
           OR LOWER(TRIM(COALESCE(v.motivo_rechazo,''))) LIKE r.motivo_key||' %'
        ORDER BY LENGTH(r.motivo_key) DESC LIMIT 1
    ) rz ON TRUE
    WHERE LOWER(TRIM(COALESCE(a.tipo_producto,'')))='mercaderia'
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
    WHERE EXTRACT(YEAR FROM b.fecha)::INT=p.anio_base GROUP BY b.cliente,b.sucursal
),
ytd AS (
    SELECT b.cliente,b.sucursal,
           SUM(b.importe) AS venta,SUM(b.hl) AS hl,SUM(b.bultos) AS blt,
           SUM(b.pallets) AS pal,SUM(b.up) AS up,
           COUNT(DISTINCT b.pedido_key) AS ped,SUM(b.es_rechazo) AS rec
    FROM base b CROSS JOIN params p
    WHERE EXTRACT(YEAR FROM b.fecha)::INT=p.anio_ytd
      AND EXTRACT(MONTH FROM b.fecha)::INT<=p.mes_ytd_hasta
    GROUP BY b.cliente,b.sucursal
),
bmp AS (
    SELECT b.cliente,b.sucursal,SUM(b.importe) AS venta,COUNT(DISTINCT b.pedido_key) AS ped
    FROM base b CROSS JOIN params p
    WHERE EXTRACT(YEAR FROM b.fecha)::INT=p.anio_base
      AND EXTRACT(MONTH FROM b.fecha)::INT<=p.mes_ytd_hasta
    GROUP BY b.cliente,b.sucursal
)
SELECT COALESCE(y.cliente,ab.cliente) AS cliente,
       COALESCE(y.sucursal,ab.sucursal) AS sucursal,
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
       COALESCE(ca.localidad,'') AS localidad,
       COALESCE(ca.autoelevador,FALSE) AS autoelevador,
       ca.nps_valor, ca.rmd_valor,
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
CROSS JOIN params p;


-- vw_cliente_cluster_dpo ------------------------------------
DROP VIEW IF EXISTS vw_cliente_cluster_dpo CASCADE;
CREATE VIEW vw_cliente_cluster_dpo AS
WITH m AS (SELECT * FROM vw_cliente_metricas WHERE venta_ytd>0 OR venta_anio_base>0),
u AS (
    SELECT
        percentile_cont(
            COALESCE((SELECT percentil_alta FROM seg_parametros
                      WHERE activo ORDER BY (sucursal_id IS NULL) DESC,id DESC LIMIT 1),0.70)
        ) WITHIN GROUP (ORDER BY venta_ytd) AS va,
        percentile_cont(
            COALESCE((SELECT percentil_baja FROM seg_parametros
                      WHERE activo ORDER BY (sucursal_id IS NULL) DESC,id DESC LIMIT 1),0.30)
        ) WITHIN GROUP (ORDER BY venta_ytd) AS vb,
        COALESCE(
            (SELECT umbral_crecimiento FROM seg_parametros
             WHERE activo AND umbral_crecimiento IS NOT NULL
             ORDER BY (sucursal_id IS NULL) DESC,id DESC LIMIT 1),
            percentile_cont(0.5) WITHIN GROUP (ORDER BY crecimiento_pct)
        ) AS uc,
        percentile_cont(0.25) WITHIN GROUP (ORDER BY dropsize_bultos_ytd) AS p25ds,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY dropsize_bultos_ytd) AS p50ds,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY ratio_costo_logistico_pct) AS p75rc
    FROM m
)
SELECT m.*,u.va AS umbral_venta_alta,u.vb AS umbral_venta_baja,u.uc AS umbral_crecimiento,
       CASE WHEN m.venta_ytd>=u.va AND COALESCE(m.crecimiento_pct,0)>COALESCE(u.uc,0) THEN 'Ganador'
            WHEN COALESCE(m.crecimiento_pct,0)>COALESCE(u.uc,0) THEN 'En crecimiento'
            WHEN m.venta_ytd>=u.vb THEN 'Básico'
            ELSE 'Ventas bajas' END AS cluster_dpo,
       CASE WHEN COALESCE(m.ratio_costo_logistico_pct,0)>u.p75rc AND m.dropsize_bultos_ytd<u.p25ds THEN 'Caro de servir'
            WHEN COALESCE(m.pct_rechazo_pedidos,0)>20 THEN 'Complejo'
            WHEN COALESCE(m.crecimiento_pct,0)>15 AND COALESCE(m.pct_rechazo_pedidos,0)<5 THEN 'Alto potencial'
            WHEN COALESCE(m.ratio_costo_logistico_pct,0)<=20 AND m.dropsize_bultos_ytd>=u.p50ds THEN 'Eficiente'
            WHEN COALESCE(m.ratio_costo_logistico_pct,0)<=25 AND COALESCE(m.margen_logistico_proxy,0)>0 THEN 'Rentable'
            ELSE 'Estándar' END AS subcluster_logistico
FROM m CROSS JOIN u;


-- vw_cliente_score ------------------------------------------
DROP VIEW IF EXISTS vw_cliente_score CASCADE;
CREATE VIEW vw_cliente_score AS
WITH m AS (SELECT * FROM vw_cliente_metricas WHERE venta_ytd>0 OR venta_anio_base>0),
md AS (SELECT COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY rmd_valor),5) AS mrmd,
              COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY nps_valor),5) AS mnps,
              COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY crecimiento_pct),0) AS mcrec FROM m),
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
SELECT cliente,descripcion_cliente,sucursal,localidad,
       ROUND((nv*15+nh*10+nc*10)::NUMERIC,2) AS dim_negocio,
       ROUND((nd*10+np*5+(CASE WHEN autoelevador THEN 5.0 ELSE 0.0 END))::NUMERIC,2) AS dim_productividad,
       ROUND((nr_*10+nrmd*5+nnps*5)::NUMERIC,2) AS dim_servicio,
       ROUND((nrc*10+nmg*5)::NUMERIC,2) AS dim_rentabilidad,
       ROUND((nped*7+(CASE WHEN NULLIF(localidad,'') IS NOT NULL THEN 2.0 ELSE 0.0 END)
             +(CASE WHEN NULLIF(sucursal,'') IS NOT NULL THEN 1.0 ELSE 0.0 END))::NUMERIC,2) AS dim_geo,
       ROUND((nv*15)::NUMERIC,2) AS pts_venta,
       ROUND((nh*10)::NUMERIC,2) AS pts_hl,
       ROUND((nc*10)::NUMERIC,2) AS pts_crecimiento,
       ROUND((nd*10)::NUMERIC,2) AS pts_dropsize,
       ROUND((np*5)::NUMERIC,2)  AS pts_pallets_ped,
       ROUND((CASE WHEN autoelevador THEN 5.0 ELSE 0.0 END)::NUMERIC,2) AS pts_autoelevador,
       ROUND((nr_*10)::NUMERIC,2) AS pts_rechazos,
       ROUND((nrmd*5)::NUMERIC,2) AS pts_rmd,
       ROUND((nnps*5)::NUMERIC,2) AS pts_nps,
       ROUND((nrc*10)::NUMERIC,2) AS pts_ratio_costo,
       ROUND((nmg*5)::NUMERIC,2)  AS pts_margen,
       ROUND((nped*7)::NUMERIC,2) AS pts_frecuencia,
       ROUND((nv*15+nh*10+nc*10+nd*10+np*5
             +(CASE WHEN autoelevador THEN 5.0 ELSE 0.0 END)
             +nr_*10+nrmd*5+nnps*5+nrc*10+nmg*5+nped*7
             +(CASE WHEN NULLIF(localidad,'') IS NOT NULL THEN 2.0 ELSE 0.0 END)
             +(CASE WHEN NULLIF(sucursal,'') IS NOT NULL THEN 1.0 ELSE 0.0 END))::NUMERIC,2) AS score_total
FROM nr;


-- vw_cliente_plan_servicio -----------------------------------
DROP VIEW IF EXISTS vw_cliente_plan_servicio CASCADE;
CREATE VIEW vw_cliente_plan_servicio AS
SELECT c.cliente,c.descripcion_cliente,c.sucursal,c.localidad,c.autoelevador,
       c.cluster_dpo,c.subcluster_logistico,
       s.score_total,s.dim_negocio,s.dim_productividad,s.dim_servicio,s.dim_rentabilidad,s.dim_geo,
       s.pts_venta,s.pts_hl,s.pts_crecimiento,s.pts_dropsize,s.pts_rechazos,s.pts_rmd,s.pts_nps,
       c.venta_ytd,c.venta_anio_base,c.crecimiento_pct,
       c.hl_ytd,c.bultos_ytd,c.pallets_ytd,c.pedidos_ytd,
       c.dropsize_bultos_ytd,c.ticket_promedio_ytd,
       c.rechazos_ytd,c.pct_rechazo_pedidos,
       c.nps_valor,c.rmd_valor,
       c.costo_entrega,c.costo_almacen,c.costo_logistico_total,
       c.margen_logistico_proxy,c.ratio_costo_logistico_pct,
       CASE c.cluster_dpo
           WHEN 'Ganador'        THEN 'Prioridad de inventario · mejor OTIF · ventanas horarias precisas · evaluar flex/express'
           WHEN 'En crecimiento' THEN 'Seguimiento comercial-logístico · mejorar frecuencia · acompañar experiencia'
           WHEN 'Básico'         THEN 'Servicio estándar · costo controlado · frecuencia óptima'
           WHEN 'Ventas bajas'   THEN 'Optimizar frecuencia · consolidar pedidos · revisar rentabilidad'
           ELSE 'Sin clasificación' END AS plan_servicio,
       CASE c.subcluster_logistico
           WHEN 'Caro de servir' THEN 'Revisar costo logístico · negociar drop size mínimo · evaluar consolidación'
           WHEN 'Alto potencial' THEN 'Fortalecer relación · asignar vendedor referente · mejorar OTIF'
           WHEN 'Eficiente'      THEN 'Mantener operación · compartir benchmarks positivos'
           WHEN 'Rentable'       THEN 'Proteger cuenta · renovar acuerdo · ofrecer beneficios premium'
           WHEN 'Complejo'       THEN 'Plan mejora de rechazo · visita técnica · acuerdo de entrega'
           ELSE                       'Monitorear indicadores mensualmente' END AS accion_prioritaria,
       CASE WHEN c.pct_rechazo_pedidos>20 THEN 'CRÍTICO: tasa de rechazo > 20 %'
            WHEN c.pct_rechazo_pedidos>10 THEN 'ATENCIÓN: tasa de rechazo > 10 %'
            WHEN c.ratio_costo_logistico_pct>40 THEN 'CRÍTICO: ratio costo logístico > 40 %'
            WHEN COALESCE(c.crecimiento_pct,0)<-30 THEN 'ALERTA: caída de venta > 30 %'
            WHEN c.cluster_dpo='Ganador' AND COALESCE(c.crecimiento_pct,0)<0 THEN 'AVISO: Ganador con caída YTD'
            ELSE NULL END AS alerta_operativa,
       CASE c.cluster_dpo WHEN 'Ganador' THEN 1 WHEN 'En crecimiento' THEN 2
                          WHEN 'Básico' THEN 3 WHEN 'Ventas bajas' THEN 4 ELSE 5 END AS prioridad_gestion
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente=c.cliente;


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
       ROUND(AVG(c.nps_valor)::NUMERIC,2) AS nps_prom,
       ROUND(AVG(s.score_total)::NUMERIC,2) AS score_prom,
       ROUND((SUM(c.venta_ytd)/NULLIF(SUM(SUM(c.venta_ytd)) OVER (PARTITION BY c.sucursal),0)*100)::NUMERIC,2)
           AS pct_venta_en_sucursal
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente=c.cliente
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
       ROUND(AVG(s.score_total)::NUMERIC,2) AS score_prom
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente=c.cliente
GROUP BY c.localidad,c.sucursal,c.cluster_dpo;
"""


# ─────────────────────────────────────────────────────────────
# Inicialización de tablas y vistas
# ─────────────────────────────────────────────────────────────

def ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return
    with pg_conn() as conn:
        with conn.cursor() as cur:
            for ddl in (_DDL_PARAMETROS, _DDL_ATRIBUTOS, _DDL_HISTORICO, _DDL_AUDITORIA):
                cur.execute(ddl)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_seg_params_activo ON seg_parametros(activo,empresa_id);
                CREATE INDEX IF NOT EXISTS idx_seg_cli_suc       ON seg_clientes_atributos(sucursal_id);
                CREATE INDEX IF NOT EXISTS idx_seg_cli_loc       ON seg_clientes_atributos(localidad);
                CREATE INDEX IF NOT EXISTS idx_seg_hist_cli      ON seg_cliente_cluster_historico(cliente);
                CREATE INDEX IF NOT EXISTS idx_seg_hist_per      ON seg_cliente_cluster_historico(periodo_anio,periodo_mes);
                CREATE INDEX IF NOT EXISTS idx_seg_hist_cl       ON seg_cliente_cluster_historico(cluster_dpo);
                CREATE INDEX IF NOT EXISTS idx_seg_aud_at        ON seg_auditoria(ejecutado_at DESC);
            """)
            cur.execute("INSERT INTO seg_parametros(empresa_id) VALUES('1') ON CONFLICT DO NOTHING")
            # Crear/recrear vistas
            cur.execute(_VIEWS_SQL)
    _TABLES_READY = True


# ─────────────────────────────────────────────────────────────
# Parámetros
# ─────────────────────────────────────────────────────────────

def get_parametros() -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute("""
            SELECT * FROM seg_parametros
            WHERE activo ORDER BY (sucursal_id IS NULL) DESC, id DESC LIMIT 1
        """)
        row = cur.fetchone()
    return dict(row) if row else {}


def update_parametros(data: dict) -> dict:
    ensure_tables()
    campos = (
        'costo_entrega_hl', 'costo_almacen_hl', 'percentil_alta', 'percentil_baja',
        'umbral_crecimiento', 'anio_base', 'anio_ytd', 'mes_ytd_hasta',
        'peso_negocio', 'peso_productividad', 'peso_servicio', 'peso_rentabilidad', 'peso_geo',
    )
    set_parts = ', '.join(f"{c} = %({c})s" for c in campos if c in data)
    if not set_parts:
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
    return dict(updated) if updated else {}


# ─────────────────────────────────────────────────────────────
# Atributos de clientes
# ─────────────────────────────────────────────────────────────

def upsert_atributos_cliente(cliente: str, data: dict) -> dict:
    ensure_tables()
    data['cliente'] = cliente.strip()
    data['updated_at'] = datetime.now()
    campos = ('cliente', 'sucursal_id', 'localidad', 'autoelevador',
              'nps_valor', 'nps_fecha', 'rmd_valor', 'rmd_fecha', 'updated_at')
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
            r.get('autoelevador', False),
            r.get('nps_valor'),
            r.get('nps_fecha'),
            r.get('rmd_valor'),
            r.get('rmd_fecha'),
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
                    nps_valor,nps_fecha,rmd_valor,rmd_fecha,updated_at)
                   VALUES %s
                   ON CONFLICT (cliente) DO UPDATE SET
                       sucursal_id  = EXCLUDED.sucursal_id,
                       localidad    = EXCLUDED.localidad,
                       autoelevador = EXCLUDED.autoelevador,
                       nps_valor    = EXCLUDED.nps_valor,
                       nps_fecha    = EXCLUDED.nps_fecha,
                       rmd_valor    = EXCLUDED.rmd_valor,
                       rmd_fecha    = EXCLUDED.rmd_fecha,
                       updated_at   = EXCLUDED.updated_at""",
                batch,
                page_size=500,
            )
    return len(batch)


# ─────────────────────────────────────────────────────────────
# Consultas sobre vistas
# ─────────────────────────────────────────────────────────────

def _dict_rows(cur) -> list[dict]:
    return [dict(r) for r in (cur.fetchall() or [])]


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


def get_clusters(
    sucursal: str | None = None,
    cluster: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    ensure_tables()
    conds, params = ['1=1'], {}
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
    conds, params = ['1=1'], {}
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
    with pg_cursor() as cur:
        cur.execute(
            f"SELECT * FROM vw_cliente_plan_servicio WHERE {where} "
            "ORDER BY prioridad_gestion, score_total DESC NULLS LAST "
            "LIMIT %(lim)s OFFSET %(off)s",
            params,
        )
        return _dict_rows(cur)


def get_resumen_sucursal() -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            "SELECT * FROM resumen_cluster_sucursal "
            "ORDER BY sucursal, prioridad_gestion"
            if False  # prioridad_gestion no existe en esta vista
            else "SELECT * FROM resumen_cluster_sucursal ORDER BY sucursal, cluster_dpo"
        )
        return _dict_rows(cur)


def get_resumen_localidad(sucursal: str | None = None) -> list[dict]:
    ensure_tables()
    params: dict = {}
    where = ''
    if sucursal and sucursal != 'TODAS':
        where = 'WHERE sucursal = %(suc)s'
        params['suc'] = sucursal
    with pg_cursor() as cur:
        cur.execute(
            f"SELECT * FROM resumen_cluster_localidad {where} "
            "ORDER BY localidad, cluster_dpo",
            params,
        )
        return _dict_rows(cur)


def get_cliente_detalle(cliente: str) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            "SELECT * FROM vw_cliente_plan_servicio WHERE cliente = %(c)s",
            {'c': cliente},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_evolucion_cluster(cliente: str) -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """SELECT periodo_anio, periodo_mes, cluster_dpo, subcluster_logistico,
                      score_total, venta_ytd, crecimiento_pct, fecha_calculo
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

def recalcular_clusters(
    periodo_anio: int,
    periodo_mes: int = 0,
    ejecutado_por: str = 'sistema',
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

    # 1. Leer parámetros para auditoría
    params_row = get_parametros()
    version = params_row.get('version_regla', 1)

    # 2. Obtener datos actuales desde las vistas
    with pg_cursor() as cur:
        cur.execute("""
            SELECT cliente, descripcion_cliente, sucursal AS sucursal_id, localidad,
                   cluster_dpo, subcluster_logistico,
                   score_total, dim_negocio, dim_productividad, dim_servicio,
                   dim_rentabilidad, dim_geo,
                   venta_ytd, hl_ytd, crecimiento_pct,
                   costo_logistico_total, ratio_costo_logistico_pct,
                   pedidos_ytd, dropsize_bultos_ytd, pct_rechazo_pedidos
            FROM vw_cliente_plan_servicio
            ORDER BY score_total DESC NULLS LAST
        """)
        rows = cur.fetchall()

    if not rows:
        return {'procesados': 0, 'error': 'Sin datos en vw_cliente_plan_servicio'}

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
            r['venta_ytd'], r['hl_ytd'], r['crecimiento_pct'],
            r['costo_logistico_total'], r['ratio_costo_logistico_pct'],
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
                       venta_ytd, hl_ytd, crecimiento_pct,
                       costo_logistico_total, ratio_costo_logistico,
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
                       venta_ytd             = EXCLUDED.venta_ytd,
                       hl_ytd                = EXCLUDED.hl_ytd,
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
                    conteos.get('Básico', 0),
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
        'version_regla': version,
        'duracion_ms': duracion_ms,
    }
