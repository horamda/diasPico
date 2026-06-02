"""
Tests unitarios para sync_sheets_service.
No requieren DB ni acceso a Google Sheets — todo es mockeado.
"""

import unittest
from unittest.mock import patch, MagicMock


# ── Helpers de la función privada _sucursal_from_url ──────────────────────────

# Importamos el módulo aislado para probar las funciones puras sin Flask
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.sync_sheets_service import _sucursal_from_url, _parse_rows


class TestSucursalFromUrl(unittest.TestCase):

    def test_gid_0_es_casa_central(self):
        url = "https://docs.google.com/spreadsheets/d/e/XXX/pub?output=csv&gid=0"
        self.assertEqual(_sucursal_from_url(url), "1")

    def test_gid_1883083406_es_casa_central(self):
        url = "https://docs.google.com/spreadsheets/d/e/XXX/pub?output=csv&gid=1883083406"
        self.assertEqual(_sucursal_from_url(url), "1")

    def test_gid_249846040_es_dolores(self):
        url = "https://docs.google.com/spreadsheets/d/e/XXX/pub?output=csv&gid=249846040"
        self.assertEqual(_sucursal_from_url(url), "2")

    def test_gid_680588527_es_dolores(self):
        url = "https://docs.google.com/spreadsheets/d/e/XXX/pub?output=csv&gid=680588527"
        self.assertEqual(_sucursal_from_url(url), "2")

    def test_gid_desconocido_default_casa_central(self):
        url = "https://docs.google.com/spreadsheets/d/e/XXX/pub?output=csv&gid=9999999"
        self.assertEqual(_sucursal_from_url(url), "1")

    def test_url_sin_gid_default(self):
        url = "https://docs.google.com/spreadsheets/d/e/XXX/pub?output=csv"
        self.assertEqual(_sucursal_from_url(url), "1")


class TestParseRows(unittest.TestCase):

    def _row(self, fecha, chofer, ay1="", ay2=""):
        return {"fecha": fecha, "chofer / responsable billetera": chofer,
                "ayudante1": ay1, "ayudante2": ay2}

    def test_fila_valida_se_parsea(self):
        raw = [self._row("10/05/2025", "Juan Pérez", "Carlos López")]
        result = _parse_rows(raw, sucursal_id="1", nro_salida=1, empresa_id="1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["chofer"], "Juan Pérez")
        self.assertEqual(result[0]["ayudante_1"], "Carlos López")
        self.assertIsNone(result[0]["ayudante_2"])
        self.assertEqual(result[0]["nro_salida"], 1)
        self.assertEqual(result[0]["sucursal_id"], "1")

    def test_fila_sin_chofer_se_ignora(self):
        raw = [self._row("10/05/2025", "")]
        result = _parse_rows(raw, "1", 1, "1")
        self.assertEqual(len(result), 0)

    def test_fila_sin_fecha_se_ignora(self):
        raw = [self._row("", "Juan Pérez")]
        result = _parse_rows(raw, "1", 1, "1")
        self.assertEqual(len(result), 0)

    def test_ayudante_vacio_queda_none(self):
        raw = [self._row("10/05/2025", "Juan Pérez", "", "")]
        result = _parse_rows(raw, "1", 1, "1")
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["ayudante_1"])
        self.assertIsNone(result[0]["ayudante_2"])

    def test_multiples_filas(self):
        raw = [
            self._row("10/05/2025", "Chofer A", "Ayd 1"),
            self._row("10/05/2025", "Chofer B"),
            self._row("11/05/2025", "Chofer C"),
        ]
        result = _parse_rows(raw, "2", 2, "1")
        self.assertEqual(len(result), 3)
        self.assertTrue(all(r["nro_salida"] == 2 for r in result))
        self.assertTrue(all(r["sucursal_id"] == "2" for r in result))

    def test_nro_salida_se_asigna_correctamente(self):
        raw = [self._row("01/05/2025", "Pedro")]
        r1 = _parse_rows(raw, "1", 1, "1")[0]
        r2 = _parse_rows(raw, "1", 2, "1")[0]
        self.assertEqual(r1["nro_salida"], 1)
        self.assertEqual(r2["nro_salida"], 2)


class TestSyncOperacionCamiones(unittest.TestCase):
    """
    sync_operacion_camiones usa current_app (Flask proxy).
    Creamos una mini app con la config necesaria para cada test.
    """

    _ENTREGA_URL  = ("https://sheets.example.com/pub?output=csv&gid=0;"
                     "https://sheets.example.com/pub?output=csv&gid=249846040")
    _RECARGAS_URL = ("https://sheets.example.com/pub?output=csv&gid=1883083406;"
                     "https://sheets.example.com/pub?output=csv&gid=680588527")

    def _app(self):
        from flask import Flask
        app = Flask(__name__)
        app.config["DOTACION_ENTREGA_URL"]  = self._ENTREGA_URL
        app.config["DOTACION_RECARGAS_URL"] = self._RECARGAS_URL
        return app

    def _row(self):
        return {"fecha": "10/05/2025", "chofer / responsable billetera": "Juan",
                "ayudante1": "", "ayudante2": ""}

    @patch("app.services.sync_sheets_service.repo.replace_rows", return_value=3)
    @patch("app.services.sync_sheets_service._fetch_rows")
    def test_sync_llama_4_tabs(self, mock_fetch, mock_upsert):
        mock_fetch.return_value = [self._row()]
        with self._app().app_context():
            from app.services.sync_sheets_service import sync_operacion_camiones
            result = sync_operacion_camiones("1")

        self.assertEqual(mock_fetch.call_count, 4)
        self.assertEqual(mock_upsert.call_count, 4)
        self.assertEqual(result["insertados"], 12)   # 3 upsertados × 4 tabs
        self.assertEqual(result["errores"], [])

    @patch("app.services.sync_sheets_service.repo.upsert_rows", return_value=0)
    @patch("app.services.sync_sheets_service._fetch_rows", side_effect=Exception("HTTP 401"))
    def test_sync_captura_errores_por_tab(self, mock_fetch, mock_upsert):
        with self._app().app_context():
            from app.services.sync_sheets_service import sync_operacion_camiones
            result = sync_operacion_camiones("1")

        self.assertEqual(len(result["errores"]), 4)
        self.assertEqual(result["insertados"], 0)
        for err in result["errores"]:
            self.assertIn("HTTP 401", err)

    @patch("app.services.sync_sheets_service._fetch_rows")
    def test_sync_asigna_sucursal_correcta_por_gid(self, mock_fetch):
        mock_fetch.return_value = [self._row()]
        llamadas_upsert = []

        def capture_replace(rows, sucursal_id, nro_salida):
            llamadas_upsert.extend(rows)
            return len(rows)

        with patch("app.services.sync_sheets_service.repo.replace_rows", side_effect=capture_replace):
            with self._app().app_context():
                from app.services.sync_sheets_service import sync_operacion_camiones
                sync_operacion_camiones("1")

        suc_ids = {r["sucursal_id"] for r in llamadas_upsert}
        nros    = {r["nro_salida"]  for r in llamadas_upsert}
        self.assertIn("1", suc_ids)
        self.assertIn("2", suc_ids)
        self.assertIn(1, nros)
        self.assertIn(2, nros)

    @patch("app.services.sync_sheets_service.repo.replace_rows", return_value=0)
    @patch("app.services.sync_sheets_service._fetch_rows", return_value=[])
    def test_sync_sin_datos_retorna_cero(self, _f, _u):
        with self._app().app_context():
            from app.services.sync_sheets_service import sync_operacion_camiones
            result = sync_operacion_camiones("1")

        self.assertEqual(result["insertados"], 0)
        self.assertEqual(result["errores"], [])


if __name__ == "__main__":
    unittest.main()
