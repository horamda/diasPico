from collections import defaultdict
from datetime import date

from flask import Blueprint, jsonify, request

from app.services import articulos_svc
from app.database import pg_cursor


bp = Blueprint('articulos', __name__, url_prefix='/api/articulos')


@bp.get('/count')
def count():
    try:
        return jsonify({'total': articulos_svc.get_count()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/sin-clasificar')
def sin_clasificar():
    try:
        return jsonify(articulos_svc.get_sin_clasificar(
            mes=request.args.get('mes'),
            sucursal=request.args.get('sucursal', 'TODAS'),
            limit=request.args.get('limit', 20, type=int),
        ))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/bultos-por-calibre')
def bultos_por_calibre():
    """Bultos y pallets vendidos por calibre (ml/unidad) y mes. tipo_producto=MERCADERIA."""
    try:
        anio     = request.args.get('anio', date.today().year, type=int)
        sucursal = request.args.get('sucursal', 'TODAS')
        division = request.args.get('division')

        suc_filter = "" if sucursal == 'TODAS' else "AND COALESCE(NULLIF(TRIM(v.sucursal),''),'1') = %(suc)s"
        div_filter = "" if not division else "AND LOWER(TRIM(a.division)) = LOWER(%(div)s)"

        with pg_cursor() as cur:
            cur.execute(f"""
                SELECT
                    ROUND(a.valor_unidad_medida * 100000
                          / NULLIF(a.unidades_por_bulto, 0)) AS calibre_ml,
                    a.division,
                    EXTRACT(MONTH FROM v.fecha)::int AS mes,
                    SUM(COALESCE(v.bultos, 0)) AS bultos,
                    SUM(CASE WHEN COALESCE(a.bultos_por_pallet, 0) > 0
                             THEN COALESCE(v.bultos, 0) / a.bultos_por_pallet
                             ELSE 0 END) AS pallets
                FROM ventas_detalle v
                JOIN articulos a ON v.id_articulo = a.id_articulo
                WHERE LOWER(TRIM(COALESCE(a.tipo_producto, ''))) = 'mercaderia'
                  AND EXTRACT(YEAR FROM v.fecha) = %(anio)s
                  AND a.unidades_por_bulto > 0
                  AND a.valor_unidad_medida > 0
                  AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE '%%remit%%'
                  AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE '%%comod%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE '%%remit%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE '%%comod%%'
                  {suc_filter}
                  {div_filter}
                GROUP BY calibre_ml, a.division, mes
                ORDER BY calibre_ml, mes
            """, {'anio': anio, 'suc': sucursal, 'div': division})
            rows = cur.fetchall()

            cur.execute("""
                SELECT DISTINCT division FROM articulos
                WHERE LOWER(TRIM(COALESCE(tipo_producto, ''))) = 'mercaderia'
                  AND division IS NOT NULL AND division != ''
                ORDER BY division
            """)
            divisiones = [r['division'] for r in cur.fetchall()]

        pivot_blt: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        pivot_plt: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        for r in rows:
            cal = int(r['calibre_ml'] or 0)
            pivot_blt[cal][int(r['mes'])] += float(r['bultos']  or 0)
            pivot_plt[cal][int(r['mes'])] += float(r['pallets'] or 0)

        calibres_total = {c: sum(m.values()) for c, m in pivot_blt.items()}
        calibres_ord   = sorted(calibres_total, key=lambda c: calibres_total[c], reverse=True)
        meses_nombres  = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

        resultado = [
            {
                'calibre_ml':    cal,
                'calibre_label': _label_calibre(cal),
                'total_bultos':  round(calibres_total[cal], 1),
                'total_pallets': round(sum(pivot_plt[cal].values()), 2),
                'bultos':        {m: round(pivot_blt[cal].get(m, 0), 1) for m in range(1, 13)},
                'pallets':       {m: round(pivot_plt[cal].get(m, 0), 2) for m in range(1, 13)},
            }
            for cal in calibres_ord if calibres_total[cal] >= 1
        ]

        return jsonify({
            'anio': anio, 'sucursal': sucursal,
            'meses_nombres': meses_nombres,
            'calibres': resultado,
            'divisiones': divisiones,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _label_calibre(ml: int) -> str:
    if ml <= 0:   return 'Sin calibre'
    if ml < 1000: return f'{ml} ml'
    if ml % 1000 == 0: return f'{ml // 1000} L'
    return f'{ml / 1000:.3g} L'
