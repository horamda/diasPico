"""
Tests unitarios para operacion_camiones_repository.
La DB se mockea completamente con unittest.mock.
"""

import unittest
from unittest.mock import patch, MagicMock, call
from datetime import date


class TestUpsertRows(unittest.TestCase):

    def _make_row(self, fecha="2025-05-10", chofer="Juan", suc="1", nro=1):
        return {
            "empresa_id": "1",
            "sucursal_id": suc,
            "fecha": fecha,
            "nro_salida": nro,
            "chofer": chofer,
            "ayudante_1": "Pedro",
            "ayudante_2": None,
        }

    @patch("app.repositories.operacion_camiones_repository.pg_conn")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_upsert_lista_vacia_no_ejecuta_sql(self, mock_pg_conn):
        from app.repositories.operacion_camiones_repository import upsert_rows
        result = upsert_rows([])
        mock_pg_conn.assert_not_called()
        self.assertEqual(result, 0)

    @patch("app.repositories.operacion_camiones_repository.pg_conn")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_upsert_llama_executemany(self, mock_pg_conn):
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_cur.rowcount = 2
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__  = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__  = MagicMock(return_value=False)
        mock_pg_conn.return_value = mock_conn

        from app.repositories.operacion_camiones_repository import upsert_rows
        rows = [self._make_row(), self._make_row(chofer="Ana")]
        result = upsert_rows(rows)

        mock_cur.executemany.assert_called_once()
        sql_arg = mock_cur.executemany.call_args[0][0]
        self.assertIn("ON CONFLICT", sql_arg)
        self.assertIn("DO UPDATE", sql_arg)
        self.assertEqual(result, 2)

    @patch("app.repositories.operacion_camiones_repository.pg_conn")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_upsert_pasa_todas_las_columnas(self, mock_pg_conn):
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_cur.rowcount = 1
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__  = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__  = MagicMock(return_value=False)
        mock_pg_conn.return_value = mock_conn

        from app.repositories.operacion_camiones_repository import upsert_rows
        row = self._make_row()
        upsert_rows([row])

        rows_arg = mock_cur.executemany.call_args[0][1]
        self.assertEqual(len(rows_arg), 1)
        self.assertIn("empresa_id", rows_arg[0])
        self.assertIn("chofer", rows_arg[0])
        self.assertIn("nro_salida", rows_arg[0])


class TestGetDetalleMensual(unittest.TestCase):

    def _make_db_row(self, sucursal_id, fecha, nro_salida, camiones, choferes, ayudantes, personas):
        row = {
            "sucursal_id": sucursal_id,
            "fecha": date.fromisoformat(fecha),
            "nro_salida": nro_salida,
            "camiones": camiones,
            "choferes": choferes,
            "ayudantes": ayudantes,
            "personas": personas,
        }
        m = MagicMock()
        m.__iter__ = MagicMock(return_value=iter(row.items()))
        m.keys = MagicMock(return_value=row.keys())
        # Hacerlo comportar como dict para dict(r)
        m.__getitem__ = MagicMock(side_effect=row.__getitem__)
        return m

    @patch("app.repositories.operacion_camiones_repository.pg_cursor")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_retorna_lista_de_dicts(self, mock_pg_cursor):
        # Simular dos filas: CC 1ra salida + DOL 1ra salida
        row1 = {"sucursal_id": "1", "fecha": date(2025, 5, 10), "nro_salida": 1,
                "camiones": 5, "choferes": 5, "ayudantes": 8, "personas": 13}
        row2 = {"sucursal_id": "2", "fecha": date(2025, 5, 10), "nro_salida": 1,
                "camiones": 3, "choferes": 3, "ayudantes": 4, "personas": 7}

        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [row1, row2]
        mock_pg_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_pg_cursor.return_value.__exit__  = MagicMock(return_value=False)

        from app.repositories.operacion_camiones_repository import get_detalle_mensual
        result = get_detalle_mensual("1", "TODAS", 2025, 5)

        self.assertEqual(len(result), 2)
        # fecha debe estar serializada como string ISO
        self.assertIsInstance(result[0]["fecha"], str)
        self.assertEqual(result[0]["fecha"], "2025-05-10")

    @patch("app.repositories.operacion_camiones_repository.pg_cursor")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_sin_datos_retorna_lista_vacia(self, mock_pg_cursor):
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_pg_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_pg_cursor.return_value.__exit__  = MagicMock(return_value=False)

        from app.repositories.operacion_camiones_repository import get_detalle_mensual
        result = get_detalle_mensual("1", "1", 2025, 1)
        self.assertEqual(result, [])

    @patch("app.repositories.operacion_camiones_repository.pg_cursor")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_filtro_sucursal_agrega_where(self, mock_pg_cursor):
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_pg_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_pg_cursor.return_value.__exit__  = MagicMock(return_value=False)

        from app.repositories.operacion_camiones_repository import get_detalle_mensual
        get_detalle_mensual("1", "2", 2025, 5)

        sql_called = mock_cur.execute.call_args[0][0]
        self.assertIn("sucursal_id", sql_called)

    @patch("app.repositories.operacion_camiones_repository.pg_cursor")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_filtro_todas_no_filtra_sucursal(self, mock_pg_cursor):
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_pg_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_pg_cursor.return_value.__exit__  = MagicMock(return_value=False)

        from app.repositories.operacion_camiones_repository import get_detalle_mensual
        get_detalle_mensual("1", "TODAS", 2025, 5)

        sql_called = mock_cur.execute.call_args[0][0]
        # El where de sucursal solo aparece cuando no es TODAS
        self.assertNotIn("AND sucursal_id", sql_called)

    @patch("app.repositories.operacion_camiones_repository.pg_cursor")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_anio_mes_se_pasan_correctamente(self, mock_pg_cursor):
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_pg_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_pg_cursor.return_value.__exit__  = MagicMock(return_value=False)

        from app.repositories.operacion_camiones_repository import get_detalle_mensual
        get_detalle_mensual("1", "TODAS", 2025, 3)

        params = mock_cur.execute.call_args[0][1]
        self.assertEqual(params["anio_mes"], "2025-03-01")


class TestGetEstadisticasPeriodo(unittest.TestCase):

    @patch("app.repositories.operacion_camiones_repository.pg_cursor")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_sin_datos_retorna_ceros(self, mock_pg_cursor):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_pg_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_pg_cursor.return_value.__exit__  = MagicMock(return_value=False)

        from app.repositories.operacion_camiones_repository import get_estadisticas_periodo
        result = get_estadisticas_periodo("1", "1", 2025, 5)

        self.assertEqual(result["camiones_dia_promedio"], 0.0)
        self.assertEqual(result["salidas_total"], 0)
        self.assertEqual(result["dias_con_datos"], 0)
        self.assertEqual(result["personas_unicas"], 0)

    @patch("app.repositories.operacion_camiones_repository.pg_cursor")
    @patch("app.repositories.operacion_camiones_repository._READY", True)
    def test_con_datos_retorna_valores(self, mock_pg_cursor):
        row = {
            "camiones_dia_promedio": 4.5,
            "salidas_total": 90,
            "dias_con_datos": 20,
            "personas_unicas": 12,
        }
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = row
        mock_pg_cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_pg_cursor.return_value.__exit__  = MagicMock(return_value=False)

        from app.repositories.operacion_camiones_repository import get_estadisticas_periodo
        result = get_estadisticas_periodo("1", "1", 2025, 5)

        self.assertEqual(result["camiones_dia_promedio"], 4.5)
        self.assertEqual(result["salidas_total"], 90)
        self.assertEqual(result["dias_con_datos"], 20)
        self.assertEqual(result["personas_unicas"], 12)


if __name__ == "__main__":
    unittest.main()
