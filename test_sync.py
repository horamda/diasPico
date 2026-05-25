"""
Script de diagnóstico del sync de Google Sheets.
Correlo con: python test_sync.py
No necesita el servidor Flask corriendo.
"""
import csv
import io
import os
import sys
from dotenv import load_dotenv

load_dotenv()

BASE_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX"
    "/pub?output=csv&gid={gid}"
)

TABS = [
    ("datos mda    (CC  s1)", "0",          "1", 1),
    ("datos dol    (DOL s1)", "249846040",  "2", 1),
    ("recargas mda (CC  s2)", "1883083406", "1", 2),
    ("recargas dol (DOL s2)", "680588527",  "2", 2),
]


def fetch_csv(gid):
    import requests
    url = BASE_URL.format(gid=gid)
    print(f"  Fetching: {url}")
    resp = requests.get(url, timeout=30, allow_redirects=True)
    resp.encoding = "utf-8"
    print(f"  Status: {resp.status_code}  Content-Type: {resp.headers.get('Content-Type','?')}")
    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}")
    text = resp.text.strip()
    if text.startswith("<!") or text.lower().startswith("<html"):
        raise Exception("Respuesta HTML (no CSV) — el sheet no está publicado correctamente")
    return text


def parse_csv(text):
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        rows.append({k.strip().lower(): str(v).strip() for k, v in row.items() if k})
    return rows


def check_date(val):
    from datetime import datetime
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(val.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def main():
    total_ok = 0
    total_sin_fecha = 0
    total_sin_chofer = 0

    for tab_name, gid, sucursal_id, nro_salida in TABS:
        print(f"\n{'='*60}")
        print(f"TAB: {tab_name}  (gid={gid})")
        print(f"{'='*60}")
        try:
            text = fetch_csv(gid)
        except Exception as e:
            print(f"  ❌ ERROR al descargar: {e}")
            continue

        rows = parse_csv(text)
        print(f"  Filas CSV: {len(rows)}")

        if not rows:
            print("  ❌ Sin filas")
            continue

        print(f"  Columnas: {list(rows[0].keys())}")
        print(f"  Primeras 2 filas:")
        for r in rows[:2]:
            print(f"    {dict(r)}")

        ok = sin_fecha = sin_chofer = 0
        for r in rows:
            fecha_raw = r.get("fecha", "")
            chofer_raw = r.get("chofer / responsable billetera", "") or r.get("chofer", "")
            fecha_ok = check_date(fecha_raw) if fecha_raw else None
            if not fecha_raw or not fecha_ok:
                sin_fecha += 1
                continue
            if not chofer_raw.strip():
                sin_chofer += 1
                continue
            ok += 1

        print(f"\n  OK Parseables: {ok}")
        print(f"  ~~ Sin fecha válida: {sin_fecha}")
        print(f"  ~~ Sin chofer: {sin_chofer}")
        total_ok += ok
        total_sin_fecha += sin_fecha
        total_sin_chofer += sin_chofer

    print(f"\n{'='*60}")
    print(f"TOTAL filas que se van a insertar en DB: {total_ok}")
    print(f"TOTAL descartadas por fecha inválida:    {total_sin_fecha}")
    print(f"TOTAL descartadas por sin chofer:        {total_sin_chofer}")

    if total_ok == 0:
        print("\nERROR: No se insertaria nada. Revisa los errores arriba.")
    else:
        print(f"\nTOTAL OK: {total_ok}  SIN_FECHA: {total_sin_fecha}  SIN_CHOFER: {total_sin_chofer}")
        print("\nEl sync deberia funcionar.")
        # Verificar conexion DB
        railway_url = os.getenv("RAILWAY_URL")
        if railway_url:
            print("\nVerificando conexion a Railway...")
            try:
                import psycopg2
                conn = psycopg2.connect(railway_url, connect_timeout=30)
                cur = conn.cursor()
                # Tabla puede no existir aun
                cur.execute("SELECT to_regclass('public.operacion_camiones')")
                exists = cur.fetchone()[0]
                if exists:
                    cur.execute("SELECT COUNT(*) FROM operacion_camiones")
                    count = cur.fetchone()[0]
                    print(f"  CONECTADO. Filas actuales en operacion_camiones: {count}")
                else:
                    print("  CONECTADO. Tabla operacion_camiones NO existe aun (se creara en el primer sync).")
                conn.close()
            except Exception as e:
                print(f"  ERROR DB: {e}")
        else:
            print("\nRAILWAY_URL no encontrada en .env")


if __name__ == "__main__":
    main()
