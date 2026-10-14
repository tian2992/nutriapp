import io
import logging
import os
import sys
import warnings
from unittest.mock import patch

from django.conf import settings
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, override_settings
from django.urls import path

from nutriapp.settings import RequestFormatter, resolve_log_level


# Custom URLconf for testing 500 behavioral error logging
def error_view(request):
    raise RuntimeError("Simulated server crash for logging test")


urlpatterns = [
    path("trigger-500/", error_view),
]


class LoggingSettingsTests(SimpleTestCase):
    def test_logging_configuration_present(self):
        self.assertTrue(hasattr(settings, "LOGGING"))
        logging_dict = settings.LOGGING
        self.assertEqual(logging_dict["version"], 1)
        self.assertFalse(logging_dict["disable_existing_loggers"])

    def test_formatters_defined(self):
        formatters = settings.LOGGING.get("formatters", {})
        self.assertIn("verbose", formatters)
        self.assertIn("simple", formatters)
        self.assertEqual(formatters["verbose"].get("()"), RequestFormatter)
        self.assertIn("%(asctime)s", formatters["verbose"]["format"])
        self.assertIn("%(levelname)s", formatters["verbose"]["format"])
        self.assertIn("%(name)s", formatters["verbose"]["format"])
        self.assertIn("%(lineno)d", formatters["verbose"]["format"])

    def test_handlers_defined(self):
        handlers = settings.LOGGING.get("handlers", {})
        self.assertIn("console", handlers)
        self.assertIn("console_stderr", handlers)
        self.assertEqual(handlers["console"]["stream"], "ext://sys.stdout")
        self.assertEqual(handlers["console_stderr"]["stream"], "ext://sys.stderr")

    def test_loggers_defined(self):
        loggers = settings.LOGGING.get("loggers", {})
        expected_loggers = [
            "django",
            "django.request",
            "django.server",
            "django.db.backends",
            "anthrocalc",
            "pygrowup",
            "matplotlib",
            "PIL",
        ]
        for logger_name in expected_loggers:
            self.assertIn(logger_name, loggers)
            self.assertFalse(
                loggers[logger_name].get("propagate", True),
                f"Logger {logger_name} should set propagate=False to avoid duplication",
            )

        # Check django parent handler & level
        self.assertEqual(loggers["django"]["level"], "INFO")
        self.assertIn("console", loggers["django"]["handlers"])

        # Check django.request error stream
        self.assertEqual(loggers["django.request"]["level"], "ERROR")
        self.assertIn("console_stderr", loggers["django.request"]["handlers"])

        # Check third-party loggers default to WARNING to prevent flood
        self.assertEqual(loggers["django.db.backends"]["level"], "WARNING")
        self.assertEqual(loggers["pygrowup"]["level"], "WARNING")
        self.assertEqual(loggers["matplotlib"]["level"], "WARNING")
        self.assertEqual(loggers["PIL"]["level"], "WARNING")

        # Root logger
        self.assertIn("root", settings.LOGGING)
        self.assertIn("console", settings.LOGGING["root"]["handlers"])

    def test_resolve_log_level_function(self):
        # 1. Valid DJANGO_LOG_LEVEL (case-insensitive with whitespace)
        env = {"DJANGO_LOG_LEVEL": "  warning  "}
        self.assertEqual(resolve_log_level(environ=env, debug=False), "WARNING")

        # 2. Fallback to LOG_LEVEL when DJANGO_LOG_LEVEL is empty/missing
        env = {"DJANGO_LOG_LEVEL": "", "LOG_LEVEL": "error"}
        self.assertEqual(resolve_log_level(environ=env, debug=False), "ERROR")

        # 3. Fallback to LOG_LEVEL when DJANGO_LOG_LEVEL is invalid (warns non-fatally)
        env = {"DJANGO_LOG_LEVEL": "bogus_level", "LOG_LEVEL": "DEBUG"}
        with warnings.catch_warnings(record=True) as captured_warnings:
            warnings.simplefilter("always")
            level = resolve_log_level(environ=env, debug=False)
            self.assertEqual(level, "DEBUG")
            self.assertEqual(len(captured_warnings), 1)
            self.assertIn("Invalid log level 'bogus_level'", str(captured_warnings[0].message))

        # 4. Default fallback when both are invalid
        env = {"DJANGO_LOG_LEVEL": "invalid1", "LOG_LEVEL": "invalid2"}
        with warnings.catch_warnings(record=True) as captured_warnings:
            warnings.simplefilter("always")
            self.assertEqual(resolve_log_level(environ=env, debug=True), "DEBUG")
            self.assertEqual(resolve_log_level(environ=env, debug=False), "INFO")
            self.assertGreaterEqual(len(captured_warnings), 2)

        # 5. Default fallback when both are unset
        env = {}
        self.assertEqual(resolve_log_level(environ=env, debug=True), "DEBUG")
        self.assertEqual(resolve_log_level(environ=env, debug=False), "INFO")

    def test_request_formatter_unit(self):
        formatter = RequestFormatter(
            fmt="[%(levelname)s] [%(name)s] %(message)s"
        )

        # Record with HttpRequest-like object and status_code
        class MockRequest:
            method = "POST"
            path = "/api/v1/calculate/"

        record = logging.LogRecord(
            name="django.request",
            level=logging.ERROR,
            pathname=__file__,
            lineno=100,
            msg="Internal Server Error: %s",
            args=("/api/v1/calculate/",),
            exc_info=None,
        )
        record.request = MockRequest()
        record.status_code = 500

        formatted = formatter.format(record)
        self.assertIn("[ERROR]", formatted)
        self.assertIn("[django.request]", formatted)
        self.assertIn("method=POST", formatted)
        self.assertIn("path=/api/v1/calculate/", formatted)
        self.assertIn("status=500", formatted)
        self.assertIn("Internal Server Error: /api/v1/calculate/", formatted)

        # Non-request record
        std_record = logging.LogRecord(
            name="anthrocalc",
            level=logging.INFO,
            pathname=__file__,
            lineno=105,
            msg="Standard application message",
            args=(),
            exc_info=None,
        )
        std_formatted = formatter.format(std_record)
        self.assertEqual(std_formatted, "[INFO] [anthrocalc] Standard application message")

    @override_settings(ROOT_URLCONF=__name__, ALLOWED_HOSTS=["*"], DEBUG=False)
    def test_http_500_behavioral_logging_to_stderr(self):
        """
        Behavioral test: sending a request that raises an uncaught exception
        must emit a django.request ERROR log to stderr containing HTTP method,
        path, status code (500), and full traceback.
        """
        client = Client(raise_request_exception=False)

        req_logger = logging.getLogger("django.request")
        self.assertTrue(len(req_logger.handlers) > 0)
        stderr_handler = req_logger.handlers[0]

        # Verify that handler is configured to write to sys.stderr and not propagate
        self.assertEqual(stderr_handler.stream, sys.stderr)
        self.assertFalse(req_logger.propagate)

        captured_stderr = io.StringIO()
        with patch.object(stderr_handler, "stream", captured_stderr):
            response = client.post("/trigger-500/")

        self.assertEqual(response.status_code, 500)

        stderr_output = captured_stderr.getvalue()

        # Stderr should contain the formatted error log and full traceback
        self.assertIn("[ERROR]", stderr_output)
        self.assertIn("django.request", stderr_output)
        self.assertIn("method=POST", stderr_output)
        self.assertIn("path=/trigger-500/", stderr_output)
        self.assertIn("status=500", stderr_output)
        self.assertIn("RuntimeError: Simulated server crash for logging test", stderr_output)
        self.assertIn("Traceback (most recent call last):", stderr_output)

    def test_settings_module_reload_with_env_override(self):
        import importlib
        import nutriapp.settings as app_settings

        with patch.dict(os.environ, {"DJANGO_LOG_LEVEL": "WARNING"}, clear=False):
            importlib.reload(app_settings)
            self.assertEqual(app_settings.LOG_LEVEL, "WARNING")
            self.assertEqual(app_settings.LOGGING["root"]["level"], "WARNING")
            self.assertEqual(app_settings.LOGGING["loggers"]["anthrocalc"]["level"], "WARNING")

        with patch.dict(os.environ, {"DJANGO_LOG_LEVEL": "", "LOG_LEVEL": "ERROR"}, clear=False):
            importlib.reload(app_settings)
            self.assertEqual(app_settings.LOG_LEVEL, "ERROR")
            self.assertEqual(app_settings.LOGGING["root"]["level"], "ERROR")

        # Reload back with current default
        importlib.reload(app_settings)

    def test_django_parent_and_third_party_isolation(self):
        """
        Verify django parent logger and noisy third-party loggers have propagate=False
        to prevent duplicate console output and excessive debug log spam.
        """
        loggers = settings.LOGGING["loggers"]

        # django parent prevents duplicate logs to root and suppresses Django DEBUG noise
        self.assertEqual(loggers["django"]["level"], "INFO")
        self.assertFalse(loggers["django"]["propagate"])

        # Noisy third-party libraries pinned to WARNING
        for noisy_lib in ("matplotlib", "PIL", "pygrowup", "django.db.backends"):
            self.assertEqual(
                loggers[noisy_lib]["level"],
                "WARNING",
                f"{noisy_lib} logger should be pinned to WARNING",
            )
            self.assertFalse(
                loggers[noisy_lib]["propagate"],
                f"{noisy_lib} logger should have propagate=False",
            )

    def test_module_named_loggers_instantiated(self):
        """
        Verify that all target anthrocalc modules instantiate logger = logging.getLogger(__name__).
        """
        import anthrocalc.anthrocalc as m_anthrocalc
        import anthrocalc.bulk_import as m_bulk_import
        import anthrocalc.demo as m_demo
        import anthrocalc.person_utils as m_person_utils
        import anthrocalc.views as m_views

        self.assertIsInstance(m_person_utils.logger, logging.Logger)
        self.assertEqual(m_person_utils.logger.name, "anthrocalc.person_utils")

        self.assertIsInstance(m_anthrocalc.logger, logging.Logger)
        self.assertEqual(m_anthrocalc.logger.name, "anthrocalc.anthrocalc")

        self.assertIsInstance(m_demo.logger, logging.Logger)
        self.assertEqual(m_demo.logger.name, "anthrocalc.demo")

        self.assertIsInstance(m_views.logger, logging.Logger)
        self.assertEqual(m_views.logger.name, "anthrocalc.views")

        self.assertIsInstance(m_bulk_import.logger, logging.Logger)
        self.assertEqual(m_bulk_import.logger.name, "anthrocalc.bulk_import")

    def test_person_utils_logging_unknown_gender(self):
        import datetime
        from unittest.mock import MagicMock
        from anthrocalc.person_utils import calculate_zscore_for_metric

        mock_patient = MagicMock()
        mock_patient.dob = datetime.date(2020, 1, 1)
        mock_patient.gender = "UnknownGender"

        mock_visit = MagicMock()
        mock_visit.patient = mock_patient
        mock_visit.date = MagicMock()
        mock_visit.date.date.return_value = datetime.date(2022, 1, 1)

        mock_metric = MagicMock()
        mock_metric.visit = mock_visit

        with self.assertLogs("anthrocalc.person_utils", level="ERROR") as cm:
            calculate_zscore_for_metric(mock_metric)
            self.assertTrue(any("Unknown gender: UnknownGender" in out for out in cm.output))

    def test_person_utils_logging_calculation_warning_and_exception(self):
        import datetime
        from unittest.mock import MagicMock
        from anthrocalc.person_utils import calculate_zscore_for_metric

        mock_patient = MagicMock()
        mock_patient.dob = datetime.date(2020, 1, 1)
        mock_patient.gender = "male"

        mock_visit = MagicMock()
        mock_visit.patient = mock_patient
        mock_visit.date = MagicMock()
        mock_visit.date.date.return_value = datetime.date(2022, 1, 1)

        mock_metric = MagicMock()
        mock_metric.visit = mock_visit
        mock_metric.weight = "invalid_weight_string"
        mock_metric.height = 80.0
        mock_metric.standing_or_upright = True

        # Should log warning on WAZ calculation failure without crashing
        with self.assertLogs("anthrocalc.person_utils", level="WARNING") as cm:
            calculate_zscore_for_metric(mock_metric)
            self.assertTrue(any("Error calculating WAZ" in out for out in cm.output))

        # When an unhandled unexpected error occurs, logger.exception must record traceback
        mock_metric_broken = MagicMock()
        mock_metric_broken.visit.patient.gender = None  # None.lower() will raise AttributeError

        with self.assertLogs("anthrocalc.person_utils", level="ERROR") as cm:
            calculate_zscore_for_metric(mock_metric_broken)
            self.assertTrue(any("Failed to calculate Z-scores" in out for out in cm.output))
            # Verify that exc_info was captured on the LogRecord
            self.assertIsNotNone(cm.records[-1].exc_info)
            self.assertIs(cm.records[-1].exc_info[0], AttributeError)

    @patch("anthrocalc.anthrocalc.pygrowup.Calculator", create=True)
    def test_anthrocalc_loader_logging(self, mock_calculator_cls):
        import pandas as pd
        from anthrocalc.anthrocalc import AnthroLoader

        # Matching columns dataframe
        df_matching = pd.DataFrame(
            columns=["Col0", "Col1", "Col2", "Col3", "Col4", "Peso_2020-01", "Talla_2020-01", "Fecha_2020-01", "Lay_2020-01"]
        )
        loader_match = AnthroLoader(df_matching)
        with self.assertLogs("anthrocalc.anthrocalc", level="DEBUG") as cm:
            loader_match.load_segments()
            self.assertTrue(any("Sets of Measures of Weight and Height match." in out for out in cm.output))

        # Non-matching columns dataframe
        df_mismatch = pd.DataFrame(
            columns=["Col0", "Col1", "Col2", "Col3", "Col4", "Peso_2020-01", "Talla_2020-02", "Fecha_2020-01", "Lay_2020-01"]
        )
        loader_mismatch = AnthroLoader(df_mismatch)
        with self.assertLogs("anthrocalc.anthrocalc", level="ERROR") as cm:
            loader_mismatch.load_segments()
            self.assertTrue(any("No Match on Weight-Height Columns!" in out for out in cm.output))

    @patch("anthrocalc.anthrocalc.numpy.NaN", float("nan"), create=True)
    @patch("anthrocalc.anthrocalc.pygrowup.Calculator", create=True)
    def test_anthrocalc_loader_warning_exc_info(self, mock_calculator_cls):
        import pandas as pd
        from anthrocalc.anthrocalc import AnthroLoader

        df = pd.DataFrame(
            {
                "Col0": [1],
                "Col1": [2],
                "Col2": [3],
                "Col3": [4],
                "FechaNacimiento": ["2020-01-01"],
                "Peso_2020-01": [10.0],
                "Talla_2020-01": [80.0],
                "Fecha_2020-01": ["invalid_date_entry"],
                "Lay_2020-01": [0],
            }
        )
        loader = AnthroLoader(df)
        loader.load_segments()

        with self.assertLogs("anthrocalc.anthrocalc", level="WARNING") as cm:
            loader.calculate_indexes()
            self.assertTrue(any("invalid date" in out for out in cm.output))
            # Verify that exc_info=True was passed and captured on warning record
            self.assertIsNotNone(cm.records[-1].exc_info)

    def test_demo_missing_file_logs_error_and_raises(self):
        from anthrocalc.demo import run_demo

        non_existent = "/tmp/non_existent_demo_file_12345.xls"
        with self.assertLogs("anthrocalc.demo", level="ERROR") as cm:
            with self.assertRaises(FileNotFoundError):
                run_demo(non_existent)
            self.assertTrue(any("Demo spreadsheet not found" in out for out in cm.output))

    def test_demo_sweet_toast_melt_signatures(self):
        import pandas as pd
        from anthrocalc.demo import sweet_toast_melt

        # 1. Old positional form: sweet_toast_melt(df, "hfaz")
        df_with_code = pd.DataFrame({
            "Codigo": ["P1", "P2"],
            "2020-01-01": [0.5, -0.2],
        })
        melted_old_pos = sweet_toast_melt(df_with_code, "hfaz")
        self.assertIn("Codigo", melted_old_pos.columns)
        self.assertIn("hfaz", melted_old_pos.columns)
        self.assertEqual(len(melted_old_pos), 2)

        # 2. Form with tabla_source providing Codigo
        df_no_code = pd.DataFrame({
            "2020-01-01": [0.5, -0.2],
        })
        tabla_source = pd.DataFrame({"Codigo": ["S1", "S2"]})
        melted_with_source = sweet_toast_melt(df_no_code, "wfaz", tabla_source=tabla_source)
        self.assertIn("Codigo", melted_with_source.columns)
        self.assertIn("wfaz", melted_with_source.columns)
        self.assertEqual(list(melted_with_source["Codigo"]), ["S1", "S2"])

        # 3. Default vname="z-val"
        melted_default = sweet_toast_melt(df_with_code)
        self.assertIn("z-val", melted_default.columns)
