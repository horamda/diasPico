from datetime import date
import calendar as cal_mod

from app.database import mysql_conn


def _rango_mes(y: int, m: int) -> tuple[date, date]:
    return date(y, m, 1), date(y, m, cal_mod.monthrange(y, m)[1])


def get_ausentismo(
    sucursal: str | None = None,
    fecha: str | None = None,
    mes: str | None = None,
) -> dict:
    if not fecha and not mes:
        return {'data': [], 'disponible': False, 'error': 'fecha o mes requerido'}

    with mysql_conn() as conn:
        with conn.cursor() as cur:
            if fecha:
                cur.execute("""
                    SELECT * FROM ausentismo
                    WHERE DATE(fecha) = %s AND (%s IS NULL OR sucursal = %s)
                    ORDER BY empleado
                """, (fecha, sucursal, sucursal))
            else:
                y, m = mes.split('-')
                ini, fin = _rango_mes(int(y), int(m))
                cur.execute("""
                    SELECT DATE(fecha) AS fecha,
                        COUNT(*) AS ausentes,
                        SUM(CASE WHEN tipo = 'justificado' THEN 1 ELSE 0 END) AS justificados
                    FROM ausentismo
                    WHERE DATE(fecha) BETWEEN %s AND %s
                      AND (%s IS NULL OR sucursal = %s)
                    GROUP BY DATE(fecha)
                    ORDER BY fecha
                """, (ini, fin, sucursal, sucursal))
            return {'data': cur.fetchall(), 'disponible': True}
