"""
google_sheets_import.py
=======================
Módulo ETL: descarga 4 hojas de Google Sheets publicadas en CSV
y sincroniza los datos con la tabla MySQL `planilla_logistica`.

Uso standalone:
    python google_sheets_import.py

Integración Flask (importar la función):
    from google_sheets_import import actualizar_google_sheets
    resumen = actualizar_google_sheets()

Variables de entorno requeridas (en .env o entorno):
    MYSQL_HOST     — host del servidor MySQL (default: localhost)
    MYSQL_USER     — usuario MySQL
    MYSQL_PASSWORD — contraseña MySQL
    MYSQL_DATABASE — nombre de la base de datos
                     (también acepta MYSQL_DB por compatibilidad)
"""

from __future__ import annotations

import csv
import io
import logging
import os
import time
from datetime import datetime, date
from typing import Any

import pymysql
import pymysql.cursors
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('google_sheets_import')

# ---------------------------------------------------------------------------
# Variables de entorno
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# URLs y hojas
# ---------------------------------------------------------------------------
_SPREADSHEET_BASE = (
    'https://docs.google.com/spreadsheets/d/e/'
    '2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX'
    '/pub?single=true&output=csv&gid={gid}'
)

# Las 4 hojas a importar, en orden de procesamiento
HOJAS: list[dict[str, str]] = [
    {'nombre': 'datos_mda',   'gid': '1241670089'},
    {'nombre': 'datos_dol',   'gid': '1883083406'},
    {'nombre': 'recarga_mda', 'gid': '249846040'},
    {'nombre': 'recarga_dol', 'gid': '680588527'},
]

# Timeout de requests: (connect_timeout, read_timeout) en segundos
_REQUEST_TIMEOUT = (10, 30)

# ---------------------------------------------------------------------------
# DDL de la tabla destino
# ---------------------------------------------------------------------------
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS planilla_logistica (
    id                           INT AUTO_INCREMENT PRIMARY KEY,
    origen_hoja                  VARCHAR(50)   NOT NULL,
    fecha                        DATE,
    camion                       VARCHAR(100),
    chofer_responsable_billetera VARCHAR(200),
    ayudante1                    VARCHAR(150),
    ayudante2                    VARCHAR(150),
    numero_camion_1              VARCHAR(50),
    up                           DECIMAL(10,2),
    clientes                     INT,
    personas                     INT,
    observaciones                TEXT,
    numero_camion_2              VARCHAR(50),
    pallets                      DECIMAL(10,2),
    mes                          INT,
    anio                         INT,
    cargado_a_tiempo             VARCHAR(30),
    sucursal_id                  INT,
    fecha_actualizacion          DATETIME,
    UNIQUE KEY uk_registro (
        origen_hoja,
        fecha,
        camion(100),
        chofer_responsable_billetera(100)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# ---------------------------------------------------------------------------
# SQL de upsert en batch
# ---------------------------------------------------------------------------
_UPSERT_SQL = """
INSERT INTO planilla_logistica (
    origen_hoja, fecha, camion, chofer_responsable_billetera,
    ayudante1, ayudante2, numero_camion_1, up, clientes, personas,
    observaciones, numero_camion_2, pallets, mes, anio,
    cargado_a_tiempo, sucursal_id, fecha_actualizacion
) VALUES (
    %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s
)
ON DUPLICATE KEY UPDATE
    ayudante1                    = VALUES(ayudante1),
    ayudante2                    = VALUES(ayudante2),
    numero_camion_1              = VALUES(numero_camion_1),
    up                           = VALUES(up),
    clientes                     = VALUES(clientes),
    personas                     = VALUES(personas),
    observaciones                = VALUES(observaciones),
    numero_camion_2              = VALUES(numero_camion_2),
    pallets                      = VALUES(pallets),
    mes                          = VALUES(mes),
    anio                         = VALUES(anio),
    cargado_a_tiempo             = VALUES(cargado_a_tiempo),
    sucursal_id                  = VALUES(sucursal_id),
    fecha_actualizacion          = VALUES(fecha_actualizacion)
"""


# ---------------------------------------------------------------------------
# Helpers de conversión de tipos
# ---------------------------------------------------------------------------

def _to_date(v: Any) -> date | None:
    """Convierte string a date. Soporta dd/mm/yyyy, yyyy-mm-dd, dd-mm-yyyy."""
    if v is None or str(v).strip() == '':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    raw = str(v).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _to_decimal(v: Any) -> float | None:
    """Convierte string a float. Acepta coma como separador decimal."""
    if v is None or str(v).strip() == '':
        return None
    try:
        return float(str(v).strip().replace(',', '.').replace(' ', ''))
    except (ValueError, TypeError):
        return None


def _to_int(v: Any) -> int | None:
    """Convierte string a entero."""
    if v is None or str(v).strip() == '':
        return None
    try:
        return int(float(str(v).strip().replace(',', '.')))
    except (ValueError, TypeError):
        return None


def _clean(v: Any, maxlen: int | None = None) -> str | None:
    """Strip y None si vacío. Trunca si maxlen está definido."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s[:maxlen] if maxlen and len(s) > maxlen else s


# ---------------------------------------------------------------------------
# Descarga y parseo de CSV
# ---------------------------------------------------------------------------

def _build_url(gid: str) -> str:
    return _SPREADSHEET_BASE.format(gid=gid)


def _fetch_csv(url: str) -> str:
    """Descarga el CSV. Lanza ValueError si la respuesta es HTML."""
    resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
    resp.encoding = 'utf-8'
    resp.raise_for_status()
    text = resp.text.strip()
    if text.startswith('<!') or text.lower().startswith('<html'):
        raise ValueError(
            'La hoja devolvió HTML en vez de CSV. '
            'Verificá que esté publicada en Archivo → Publicar en la web.'
        )
    return text


def _parse_rows_positional(text: str) -> list[list[str]]:
    """
    Parsea el CSV por posición de columna (NO usa DictReader) para manejar
    las dos columnas con el mismo nombre 'N° Camion'.
    Descarta la primera fila (encabezado).
    """
    reader = csv.reader(io.StringIO(text))
    all_rows = list(reader)
    return all_rows[1:] if len(all_rows) > 1 else []


def _row_to_tuple(
    row: list[str],
    origen_hoja: str,
    ts: datetime,
) -> tuple | None:
    """
    Mapea una fila posicional a la tupla de 18 valores para el INSERT.

    Columnas esperadas (índices 0-15):
      0  Fecha
      1  Camion
      2  Chofer / Responsable billetera
      3  Ayudante1
      4  Ayudante2
      5  N° Camion              → numero_camion_1
      6  UP
      7  CLIENTES
      8  PERSONAS
      9  Observaciones
     10  N° Camion              → numero_camion_2
     11  Pallets
     12  Mes
     13  Año
     14  Cargado a tiempo?
     15  sucursal_id
    """
    # Pad a 16 columnas para evitar IndexError en filas cortas
    p = (row + [''] * 16)[:16]

    fecha  = _to_date(p[0])
    camion = _clean(p[1], 100)
    chofer = _clean(p[2], 200)

    # Fila completamente vacía de datos de negocio → descartar
    if fecha is None and camion is None and chofer is None:
        return None

    return (
        origen_hoja,
        fecha,
        camion,
        chofer,
        _clean(p[3], 150),      # ayudante1
        _clean(p[4], 150),      # ayudante2
        _clean(p[5], 50),       # numero_camion_1
        _to_decimal(p[6]),      # up
        _to_int(p[7]),          # clientes
        _to_int(p[8]),          # personas
        _clean(p[9]),           # observaciones
        _clean(p[10], 50),      # numero_camion_2
        _to_decimal(p[11]),     # pallets
        _to_int(p[12]),         # mes
        _to_int(p[13]),         # anio
        _clean(p[14], 30),      # cargado_a_tiempo
        _to_int(p[15]),         # sucursal_id
        ts,
    )


# ---------------------------------------------------------------------------
# Conexión MySQL
# ---------------------------------------------------------------------------

def _get_connection() -> pymysql.connections.Connection:
    """
    Crea una conexión MySQL desde variables de entorno.
    Acepta MYSQL_DATABASE o MYSQL_DB indistintamente.
    """
    host     = os.getenv('MYSQL_HOST', 'localhost')
    user     = os.getenv('MYSQL_USER')
    password = os.getenv('MYSQL_PASSWORD', '')
    database = os.getenv('MYSQL_DATABASE') or os.getenv('MYSQL_DB')

    if not user:
        raise EnvironmentError('Variable de entorno MYSQL_USER no está configurada.')
    if not database:
        raise EnvironmentError(
            'Variable de entorno MYSQL_DATABASE (o MYSQL_DB) no está configurada.'
        )

    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.Cursor,
        connect_timeout=10,
        autocommit=False,
    )


def _ensure_table(conn: pymysql.connections.Connection) -> None:
    """Crea planilla_logistica si no existe. Idempotente."""
    with conn.cursor() as cur:
        cur.execute(_CREATE_TABLE_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# Procesamiento de una hoja individual
# ---------------------------------------------------------------------------

def actualizar_hoja(nombre: str, gid: str) -> dict:
    """
    Descarga y sincroniza una hoja Google Sheets con MySQL.

    Args:
        nombre: Identificador de la hoja (ej. 'datos_mda').
        gid:    GID de la hoja en Google Sheets.

    Returns:
        dict con: nombre, procesados, insertados, actualizados, errores, tiempo_s.
    """
    logger.info('=' * 60)
    logger.info('Procesando %s  (gid=%s)', nombre, gid)

    result: dict[str, Any] = {
        'nombre':      nombre,
        'procesados':  0,
        'insertados':  0,
        'actualizados': 0,
        'errores':     0,
        'tiempo_s':    0.0,
    }
    t0 = time.time()

    try:
        # — Descargar CSV —
        url = _build_url(gid)
        logger.info('  URL: %s', url)
        csv_text = _fetch_csv(url)

        # — Parsear por posición —
        raw_rows = _parse_rows_positional(csv_text)
        logger.info('  Filas en CSV (sin encabezado): %d', len(raw_rows))

        if not raw_rows:
            logger.warning('  Hoja %s sin filas de datos. Se omite.', nombre)
            return result

        # — Convertir a tuplas —
        ts = datetime.now()
        batch: list[tuple] = []
        descartadas = 0

        for raw in raw_rows:
            tpl = _row_to_tuple(raw, nombre, ts)
            if tpl is None:
                descartadas += 1
            else:
                batch.append(tpl)

        logger.info(
            '  Válidas: %d | Descartadas (vacías): %d',
            len(batch), descartadas,
        )

        if not batch:
            logger.warning('  Sin filas válidas en %s.', nombre)
            return result

        result['procesados'] = len(batch)

        # — Upsert en MySQL —
        conn = _get_connection()
        try:
            _ensure_table(conn)

            with conn.cursor() as cur:
                # Snapshot previo para calcular inserts vs updates
                cur.execute(
                    'SELECT COUNT(*) FROM planilla_logistica WHERE origen_hoja = %s',
                    (nombre,),
                )
                count_antes: int = cur.fetchone()[0]

                # Batch upsert — UN solo commit al final
                cur.executemany(_UPSERT_SQL, batch)

                cur.execute(
                    'SELECT COUNT(*) FROM planilla_logistica WHERE origen_hoja = %s',
                    (nombre,),
                )
                count_despues: int = cur.fetchone()[0]

            conn.commit()

            insertados  = max(0, count_despues - count_antes)
            actualizados = max(0, len(batch) - insertados)
            result['insertados']   = insertados
            result['actualizados'] = actualizados

            logger.info(
                '  Insertados: %d | Actualizados: %d',
                insertados, actualizados,
            )

        except Exception as db_err:
            conn.rollback()
            raise db_err
        finally:
            conn.close()

    except Exception as exc:
        result['errores'] += 1
        logger.error('  ERROR en hoja %s: %s', nombre, exc, exc_info=True)

    result['tiempo_s'] = round(time.time() - t0, 2)
    logger.info('  Tiempo hoja: %.2fs', result['tiempo_s'])
    return result


# ---------------------------------------------------------------------------
# Función principal pública
# ---------------------------------------------------------------------------

def actualizar_google_sheets(hojas: list[dict] | None = None) -> dict:
    """
    Sincroniza todas las hojas configuradas con MySQL.

    Continúa aunque una hoja individual falle (try/except por hoja).

    Args:
        hojas: Lista de dicts {'nombre': str, 'gid': str}.
               Por defecto usa la constante HOJAS del módulo.

    Returns:
        Resumen agregado:
            total_procesados, total_insertados, total_actualizados,
            total_errores, tiempo_total_s, detalle_hojas.
    """
    hojas = hojas or HOJAS
    t0 = time.time()

    resumen: dict[str, Any] = {
        'total_procesados':  0,
        'total_insertados':  0,
        'total_actualizados': 0,
        'total_errores':     0,
        'tiempo_total_s':    0.0,
        'detalle_hojas':     [],
    }

    logger.info('Iniciando sincronización Google Sheets → MySQL')
    logger.info('Hojas: %s', [h['nombre'] for h in hojas])

    for hoja in hojas:
        try:
            r = actualizar_hoja(hoja['nombre'], hoja['gid'])
        except Exception as exc:
            # Captura cualquier fallo no esperado para que el loop continúe
            logger.error(
                'Fallo inesperado en hoja %s: %s',
                hoja.get('nombre', '?'), exc, exc_info=True,
            )
            r = {
                'nombre':      hoja.get('nombre', '?'),
                'procesados':  0,
                'insertados':  0,
                'actualizados': 0,
                'errores':     1,
                'tiempo_s':    0.0,
            }

        resumen['total_procesados']  += r['procesados']
        resumen['total_insertados']  += r['insertados']
        resumen['total_actualizados'] += r['actualizados']
        resumen['total_errores']     += r['errores']
        resumen['detalle_hojas'].append(r)

    resumen['tiempo_total_s'] = round(time.time() - t0, 2)

    logger.info('=' * 60)
    logger.info('RESUMEN FINAL')
    logger.info('  Total registros procesados : %d', resumen['total_procesados'])
    logger.info('  Total insertados           : %d', resumen['total_insertados'])
    logger.info('  Total actualizados         : %d', resumen['total_actualizados'])
    logger.info('  Total errores              : %d', resumen['total_errores'])
    logger.info('  Tiempo total               : %.2fs', resumen['tiempo_total_s'])
    logger.info('=' * 60)

    return resumen


# ---------------------------------------------------------------------------
# INTEGRACIÓN APSCHEDULER (opcional — descomentar para activar)
# ---------------------------------------------------------------------------
#
# from apscheduler.schedulers.background import BackgroundScheduler
#
# scheduler = BackgroundScheduler(timezone='America/Argentina/Buenos_Aires')
# scheduler.add_job(
#     actualizar_google_sheets,
#     trigger='interval',
#     hours=1,
#     id='sync_planilla_logistica',
#     replace_existing=True,
#     max_instances=1,       # evita ejecuciones solapadas
#     misfire_grace_time=60,
# )
#
# Para arrancar junto con Flask (en app/__init__.py o run.py):
#
#   from google_sheets_import import scheduler
#   if not scheduler.running:
#       scheduler.start()
#   import atexit
#   atexit.register(lambda: scheduler.shutdown(wait=False))
#
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Entry point standalone
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    resumen = actualizar_google_sheets()
    raise SystemExit(1 if resumen['total_errores'] > 0 else 0)
