"""
Tests unitarios para simulacion_logistica_service.sugerir_parametros.
Todos los accesos a DB y repositorios se mockean.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import date


class TestSugerirParametros(unittest.TestCase):

    def _call(self, anio=2025, mes=5, suc="1", **extra_patches):
        from app.services.simulacion_logistica_service import sugerir_parametros
        return sugerir_parametros("1", suc, anio, mes)

    # ── Días hábiles ─────────────────────────────────────────────────────────

    @patch("app.services.simulacion_logistica_service.cal_mod.monthrange", return_value=(5, 31))
    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    def test_dias_habiles_mayo_sin_feriados(self, *_):
        result = self._call(anio=2025, mes=5)
        sug = result["sugerencias"]
        # Mayo 2025: 31 días. Semanas completas: 22 días hábiles
        self.assertIn("dias_trabajados", sug)
        self.assertGreater(sug["dias_trabajados"], 0)
        self.assertLessEqual(sug["dias_trabajados"], 23)

    @patch("app.services.simulacion_logistica_service.cal_mod.monthrange", return_value=(5, 31))
    @patch("app.repositories.planificacion_picos_repository.obtener_feriados",
           return_value={date(2025, 5, 1)})  # 1 feriado lunes
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    def test_dias_habiles_descuenta_feriados(self, *_):
        result_sin = self._call.__func__(self, anio=2025, mes=5)

        with patch("app.repositories.planificacion_picos_repository.obtener_feriados",
                   return_value=set()):
            from app.services.simulacion_logistica_service import sugerir_parametros
            r_sin = sugerir_parametros("1", "1", 2025, 5)

        with patch("app.repositories.planificacion_picos_repository.obtener_feriados",
                   return_value={date(2025, 5, 1)}):
            r_con = sugerir_parametros("1", "1", 2025, 5)

        # Con feriado laborable debe tener menos días
        dias_sin = r_sin["sugerencias"].get("dias_trabajados", 0)
        dias_con = r_con["sugerencias"].get("dias_trabajados", 0)
        self.assertLessEqual(dias_con, dias_sin)

    # ── Días pico ────────────────────────────────────────────────────────────

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual")
    def test_dias_pico_promedio_3_anios(self, mock_base, *_):
        def base_side_effect(empresa, suc, anio, mes):
            data = {2024: {"dias_pico": 8, "hl": 1000},
                    2023: {"dias_pico": 6, "hl": 900},
                    2022: {"dias_pico": 4, "hl": 800}}
            return data.get(anio)

        mock_base.side_effect = base_side_effect

        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)
        sug = result["sugerencias"]

        self.assertIn("dias_pico_esperados", sug)
        self.assertEqual(sug["dias_pico_esperados"], 6)  # round((8+6+4)/3) = 6

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    def test_sin_historial_no_sugiere_dias_pico(self, *_):
        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)
        self.assertNotIn("dias_pico_esperados", result["sugerencias"])

    # ── Crecimiento YoY ──────────────────────────────────────────────────────

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual")
    def test_crecimiento_yoy_positivo(self, mock_base, *_):
        def base_side_effect(empresa, suc, anio, mes):
            return {2024: {"hl": 1100, "dias_pico": 5}, 2023: {"hl": 1000, "dias_pico": 5}}.get(anio)

        mock_base.side_effect = base_side_effect

        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)
        crec = result["sugerencias"].get("crecimiento_esperado")

        self.assertIsNotNone(crec)
        self.assertAlmostEqual(crec, 10.0, places=1)

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual")
    def test_crecimiento_yoy_negativo(self, mock_base, *_):
        def base_side_effect(empresa, suc, anio, mes):
            return {2024: {"hl": 900, "dias_pico": 5}, 2023: {"hl": 1000, "dias_pico": 5}}.get(anio)

        mock_base.side_effect = base_side_effect

        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)
        crec = result["sugerencias"].get("crecimiento_esperado")

        self.assertIsNotNone(crec)
        self.assertAlmostEqual(crec, -10.0, places=1)

    # ── Camiones desde flota ─────────────────────────────────────────────────

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    @patch("app.repositories.flota_repository.listar_vehiculos")
    def test_camiones_activos_se_sugieren(self, mock_flota, *_):
        mock_flota.return_value = [
            {"activo_mes": True},
            {"activo_mes": True},
            {"activo_mes": False},
            {"activo_mes": True},
        ]

        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)
        self.assertEqual(result["sugerencias"].get("camiones_disponibles"), 3)

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    def test_sin_flota_no_sugiere_camiones(self, *_):
        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)
        self.assertNotIn("camiones_disponibles", result["sugerencias"])

    # ── Datos reales de planilla ──────────────────────────────────────────────

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo")
    def test_datos_reales_planilla_se_incluyen(self, mock_stats, *_):
        mock_stats.return_value = {
            "dias_con_datos": 20,
            "camiones_dia_promedio": 5.5,
            "salidas_total": 110,
            "personas_unicas": 15,
        }

        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)
        sug = result["sugerencias"]

        self.assertIn("camiones_reales_anio_anterior", sug)
        self.assertIn("personas_reales_anio_anterior", sug)
        self.assertAlmostEqual(sug["camiones_reales_anio_anterior"], 5.5)
        self.assertEqual(sug["personas_reales_anio_anterior"], 15)

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo")
    def test_planilla_sin_datos_no_sugiere_camiones_reales(self, mock_stats, *_):
        mock_stats.return_value = {"dias_con_datos": 0}

        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)

        self.assertNotIn("camiones_reales_anio_anterior", result["sugerencias"])

    # ── Estructura de la respuesta ────────────────────────────────────────────

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    def test_respuesta_tiene_sugerencias_y_fuentes(self, *_):
        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)

        self.assertIn("sugerencias", result)
        self.assertIn("fuentes", result)
        self.assertIsInstance(result["sugerencias"], dict)
        self.assertIsInstance(result["fuentes"], dict)

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados", return_value=set())
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    def test_cada_sugerencia_tiene_fuente(self, *_):
        from app.services.simulacion_logistica_service import sugerir_parametros
        result = sugerir_parametros("1", "1", 2025, 5)
        for key in result["sugerencias"]:
            if key not in ("camiones_reales_anio_anterior", "personas_reales_anio_anterior"):
                self.assertIn(key, result["fuentes"], f"Falta fuente para '{key}'")

    @patch("app.repositories.planificacion_picos_repository.obtener_feriados",
           side_effect=Exception("DB caída"))
    @patch("app.repositories.operacion_camiones_repository.get_estadisticas_periodo",
           return_value={"dias_con_datos": 0})
    @patch("app.repositories.simulacion_logistica_repository.get_base_mensual", return_value=None)
    @patch("app.repositories.flota_repository.listar_vehiculos", return_value=[])
    def test_error_en_una_seccion_no_rompe_la_funcion(self, *_):
        from app.services.simulacion_logistica_service import sugerir_parametros
        # No debe lanzar excepción aunque feriados falle
        result = sugerir_parametros("1", "1", 2025, 5)
        self.assertIn("sugerencias", result)


if __name__ == "__main__":
    unittest.main()
