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


def ok_view(request):
    return HttpResponse("OK")


urlpatterns = [
    path("trigger-500/", error_view),
    path("ok-view/", ok_view),
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
        path, status code (500), and full traceback for both POST and GET requests.
        Normal 200 responses must not emit django.request ERROR logs.
        """
        client = Client(raise_request_exception=False)

        req_logger = logging.getLogger("django.request")
        self.assertTrue(len(req_logger.handlers) > 0)
        stderr_handler = req_logger.handlers[0]

        # Verify that handler is configured to write to sys.stderr and not propagate
        self.assertEqual(stderr_handler.stream, sys.stderr)
        self.assertFalse(req_logger.propagate)

        # 1. Test POST request 500 error
        captured_stderr_post = io.StringIO()
        with patch.object(stderr_handler, "stream", captured_stderr_post):
            response_post = client.post("/trigger-500/")

        self.assertEqual(response_post.status_code, 500)
        stderr_output_post = captured_stderr_post.getvalue()
        self.assertIn("[ERROR]", stderr_output_post)
        self.assertIn("django.request", stderr_output_post)
        self.assertIn("method=POST", stderr_output_post)
        self.assertIn("path=/trigger-500/", stderr_output_post)
        self.assertIn("status=500", stderr_output_post)
        self.assertIn("RuntimeError: Simulated server crash for logging test", stderr_output_post)
        self.assertIn("Traceback (most recent call last):", stderr_output_post)

        # 2. Test GET request 500 error
        captured_stderr_get = io.StringIO()
        with patch.object(stderr_handler, "stream", captured_stderr_get):
            response_get = client.get("/trigger-500/")

        self.assertEqual(response_get.status_code, 500)
        stderr_output_get = captured_stderr_get.getvalue()
        self.assertIn("[ERROR]", stderr_output_get)
        self.assertIn("django.request", stderr_output_get)
        self.assertIn("method=GET", stderr_output_get)
        self.assertIn("path=/trigger-500/", stderr_output_get)
        self.assertIn("status=500", stderr_output_get)
        self.assertIn("RuntimeError: Simulated server crash for logging test", stderr_output_get)
        self.assertIn("Traceback (most recent call last):", stderr_output_get)

        # 3. Test OK request (200) does NOT emit to django.request ERROR handler
        captured_stderr_ok = io.StringIO()
        with patch.object(stderr_handler, "stream", captured_stderr_ok):
            response_ok = client.get("/ok-view/")

        self.assertEqual(response_ok.status_code, 200)
        self.assertEqual(captured_stderr_ok.getvalue(), "")

    def test_log_level_overrides_actually_filter_messages(self):
        """
        Verify that dynamic log level configuration (via DJANGO_LOG_LEVEL env override
        and dictConfig) actually configures the anthrocalc logger to filter messages
        below the set threshold at runtime, streaming formatted records to the console handler.
        """
        import importlib
        import logging.config
        import nutriapp.settings as app_settings

        original_environ = os.environ.copy()
        try:
            # 1. Level = WARNING: DEBUG and INFO should be filtered out from anthrocalc logger
            with patch.dict(os.environ, {"DJANGO_LOG_LEVEL": "WARNING"}, clear=False):
                importlib.reload(app_settings)
                logging.config.dictConfig(app_settings.LOGGING)

                anthro_logger = logging.getLogger("anthrocalc")
                self.assertEqual(anthro_logger.level, logging.WARNING)
                self.assertTrue(len(anthro_logger.handlers) > 0)
                console_handler = anthro_logger.handlers[0]

                stream_warn = io.StringIO()
                with patch.object(console_handler, "stream", stream_warn):
                    child_logger = logging.getLogger("anthrocalc.person_utils")
                    child_logger.debug("Debug msg that should be dropped")
                    child_logger.info("Info msg that should be dropped")
                    child_logger.warning("Warning msg that must pass")
                    child_logger.error("Error msg that must pass")

                output_warn = stream_warn.getvalue()
                self.assertNotIn("Debug msg", output_warn)
                self.assertNotIn("Info msg", output_warn)
                self.assertIn("[WARNING]", output_warn)
                self.assertIn("[anthrocalc.person_utils:", output_warn)
                self.assertIn("Warning msg that must pass", output_warn)
                self.assertIn("[ERROR]", output_warn)
                self.assertIn("Error msg that must pass", output_warn)

            # 2. Level = DEBUG: all messages including DEBUG and INFO must pass
            with patch.dict(os.environ, {"DJANGO_LOG_LEVEL": "DEBUG"}, clear=False):
                importlib.reload(app_settings)
                logging.config.dictConfig(app_settings.LOGGING)

                anthro_logger = logging.getLogger("anthrocalc")
                self.assertEqual(anthro_logger.level, logging.DEBUG)
                console_handler = anthro_logger.handlers[0]

                stream_debug = io.StringIO()
                with patch.object(console_handler, "stream", stream_debug):
                    child_logger = logging.getLogger("anthrocalc.person_utils")
                    child_logger.debug("Debug msg that must now pass")
                    child_logger.info("Info msg that must now pass")
                    child_logger.warning("Warning msg in debug mode")

                output_debug = stream_debug.getvalue()
                self.assertIn("[DEBUG]", output_debug)
                self.assertIn("[anthrocalc.person_utils:", output_debug)
                self.assertIn("Debug msg that must now pass", output_debug)
                self.assertIn("[INFO]", output_debug)
                self.assertIn("Info msg that must now pass", output_debug)
                self.assertIn("[WARNING]", output_debug)
                self.assertIn("Warning msg in debug mode", output_debug)

        finally:
            os.environ.clear()
            os.environ.update(original_environ)
            importlib.reload(app_settings)
            logging.config.dictConfig(settings.LOGGING)

    def test_pygrowup_logger_filters_debug_and_info(self):
        """
        Verify pygrowup logger is configured at WARNING level and filters debug/info records.
        """
        pygrowup_logger = logging.getLogger("pygrowup")
        self.assertEqual(pygrowup_logger.level, logging.WARNING)
        self.assertFalse(pygrowup_logger.isEnabledFor(logging.DEBUG))
        self.assertFalse(pygrowup_logger.isEnabledFor(logging.INFO))
        self.assertTrue(pygrowup_logger.isEnabledFor(logging.WARNING))
        self.assertTrue(pygrowup_logger.isEnabledFor(logging.ERROR))

    def test_settings_module_reload_with_env_override(self):
        import importlib
        import nutriapp.settings as app_settings

        original_environ = os.environ.copy()
        try:
            with patch.dict(os.environ, {"DJANGO_LOG_LEVEL": "WARNING"}, clear=False):
                importlib.reload(app_settings)
                self.assertEqual(app_settings.LOG_LEVEL, "WARNING")
                self.assertEqual(app_settings.LOGGING["root"]["level"], "WARNING")
                self.assertEqual(app_settings.LOGGING["loggers"]["anthrocalc"]["level"], "WARNING")

            with patch.dict(os.environ, {"DJANGO_LOG_LEVEL": "", "LOG_LEVEL": "ERROR"}, clear=False):
                importlib.reload(app_settings)
                self.assertEqual(app_settings.LOG_LEVEL, "ERROR")
                self.assertEqual(app_settings.LOGGING["root"]["level"], "ERROR")
        finally:
            os.environ.clear()
            os.environ.update(original_environ)
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

        with self.assertLogs("anthrocalc", level="ERROR") as cm:
            calculate_zscore_for_metric(mock_metric)
            self.assertTrue(any("Unknown gender: UnknownGender" in out for out in cm.output))

    def test_person_utils_logging_waz_calculation_warning(self):
        """
        Verify that a failure in WAZ calculation logs a warning with error details,
        streams formatted output through the configured anthrocalc console handler,
        and sets metric.wfaz to None while allowing other metrics to calculate.
        """
        import datetime
        from unittest.mock import MagicMock
        from anthrocalc.person_utils import calculate_zscore_for_metric

        mock_patient = MagicMock()
        mock_patient.dob = datetime.date(2020, 1, 1)
        mock_patient.gender = "male"

        mock_visit = MagicMock()
        mock_visit.patient = mock_patient
        mock_visit.date.date.return_value = datetime.date(2022, 1, 1)

        mock_metric = MagicMock()
        mock_metric.visit = mock_visit
        mock_metric.weight = "invalid_weight_string"
        mock_metric.height = 80.0
        mock_metric.standing_or_upright = True

        anthro_logger = logging.getLogger("anthrocalc")
        self.assertTrue(len(anthro_logger.handlers) > 0)
        console_handler = anthro_logger.handlers[0]

        # Pin log level temporarily to ensure test independence from caller environment
        prev_level = anthro_logger.level
        anthro_logger.setLevel(logging.WARNING)
        self.addCleanup(anthro_logger.setLevel, prev_level)

        captured_stream = io.StringIO()
        with patch.object(console_handler, "stream", captured_stream):
            calculate_zscore_for_metric(mock_metric)

        formatted_output = captured_stream.getvalue()
        self.assertIn("[WARNING]", formatted_output)
        self.assertIn("[anthrocalc.person_utils:", formatted_output)
        self.assertIn("Error calculating WAZ:", formatted_output)

        self.assertIsNone(mock_metric.wfaz)
        self.assertIsInstance(mock_metric.hfaz, float)

    def test_person_utils_logging_haz_calculation_warning(self):
        """
        Verify that a failure in HAZ calculation logs a warning with error details
        and sets metric.hfaz to None while allowing WAZ to calculate.
        """
        import datetime
        from unittest.mock import MagicMock
        from anthrocalc.person_utils import calculate_zscore_for_metric

        mock_patient = MagicMock()
        mock_patient.dob = datetime.date(2020, 1, 1)
        mock_patient.gender = "female"

        mock_visit = MagicMock()
        mock_visit.patient = mock_patient
        mock_visit.date.date.return_value = datetime.date(2022, 1, 1)

        mock_metric = MagicMock()
        mock_metric.visit = mock_visit
        mock_metric.weight = 10.0
        mock_metric.height = "invalid_height_string"
        mock_metric.standing_or_upright = True

        with self.assertLogs("anthrocalc", level="WARNING") as cm:
            calculate_zscore_for_metric(mock_metric)
            self.assertTrue(any("Error calculating HAZ" in out for out in cm.output))

        self.assertIsNone(mock_metric.hfaz)
        self.assertIsInstance(mock_metric.wfaz, float)

    def test_person_utils_logging_whz_calculation_warning(self):
        """
        Verify that a failure in WHZ calculation logs a warning with error details
        and sets metric.wfhz to None.
        """
        import datetime
        import pygrowup
        from unittest.mock import MagicMock, patch
        from anthrocalc.person_utils import calculate_zscore_for_metric

        mock_patient = MagicMock()
        mock_patient.dob = datetime.date(2020, 1, 1)
        mock_patient.gender = "male"

        mock_visit = MagicMock()
        mock_visit.patient = mock_patient
        mock_visit.date.date.return_value = datetime.date(2022, 1, 1)

        mock_metric = MagicMock()
        mock_metric.visit = mock_visit
        mock_metric.weight = 10.0
        mock_metric.height = 80.0
        mock_metric.standing_or_upright = True

        with patch.object(pygrowup.Observation, "wfh", side_effect=ValueError("Measurement out of bounds")):
            with self.assertLogs("anthrocalc", level="WARNING") as cm:
                calculate_zscore_for_metric(mock_metric)
                self.assertTrue(any("Error calculating WHZ: Measurement out of bounds" in out for out in cm.output))

        self.assertIsNone(mock_metric.wfhz)
        self.assertIsInstance(mock_metric.wfaz, float)
        self.assertIsInstance(mock_metric.hfaz, float)

    def test_person_utils_logging_outer_exception_details(self):
        """
        Verify that an unhandled exception in calculate_zscore_for_metric logs an ERROR
        via logger.exception including formatted verbose output, exc_info, and exception traceback.
        """
        import datetime
        from unittest.mock import MagicMock
        from anthrocalc.person_utils import calculate_zscore_for_metric

        mock_patient = MagicMock()
        mock_patient.dob = "invalid_dob_type"
        mock_patient.gender = "female"

        mock_visit = MagicMock()
        mock_visit.patient = mock_patient
        mock_visit.date.date.return_value = datetime.date(2022, 1, 1)

        mock_metric = MagicMock()
        mock_metric.visit = mock_visit

        anthro_logger = logging.getLogger("anthrocalc")
        self.assertTrue(len(anthro_logger.handlers) > 0)
        console_handler = anthro_logger.handlers[0]

        # Pin log level temporarily to ensure test independence from caller environment
        prev_level = anthro_logger.level
        anthro_logger.setLevel(logging.ERROR)
        self.addCleanup(anthro_logger.setLevel, prev_level)

        captured_stream = io.StringIO()
        with patch.object(console_handler, "stream", captured_stream):
            calculate_zscore_for_metric(mock_metric)

        formatted_output = captured_stream.getvalue()
        self.assertIn("[ERROR]", formatted_output)
        self.assertIn("[anthrocalc.person_utils:", formatted_output)
        self.assertIn("Failed to calculate Z-scores", formatted_output)
        self.assertIn("Traceback (most recent call last):", formatted_output)
        self.assertIn("TypeError", formatted_output)

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

    def test_dockerfile_gunicorn_logging_flags(self):
        dockerfile_path = os.path.join(settings.BASE_DIR, "..", "Dockerfile")
        if not os.path.exists(dockerfile_path):
            self.skipTest("Dockerfile not present at repository root")
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        cmd_lines = [line.strip() for line in lines if line.strip().startswith("CMD ")]
        self.assertTrue(len(cmd_lines) > 0, "CMD instruction must exist in Dockerfile")
        cmd_raw = cmd_lines[-1][4:].strip()

        import json

        cmd = json.loads(cmd_raw)
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], "gunicorn")

        # Verify log streaming flags and values
        self.assertIn("--access-logfile", cmd)
        self.assertEqual(cmd[cmd.index("--access-logfile") + 1], "-")
        self.assertIn("--error-logfile", cmd)
        self.assertEqual(cmd[cmd.index("--error-logfile") + 1], "-")
        self.assertIn("--capture-output", cmd)
        self.assertIn("--enable-stdio-inheritance", cmd)

    def test_env_example_logging_configuration(self):
        env_example_path = os.path.join(settings.BASE_DIR, "..", ".env.example")
        if not os.path.exists(env_example_path):
            self.skipTest(".env.example not present at repository root")
        env_vars = {}
        with open(env_example_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, v = stripped.split("=", 1)
                    env_vars[k.strip()] = v.strip()

        self.assertIn("DJANGO_LOG_LEVEL", env_vars)
        level_val = env_vars["DJANGO_LOG_LEVEL"]
        self.assertEqual(
            resolve_log_level({"DJANGO_LOG_LEVEL": level_val}),
            level_val.upper(),
        )

    def test_docker_compose_env_file_configuration(self):
        compose_path = os.path.join(settings.BASE_DIR, "..", "docker-compose.yaml")
        if not os.path.exists(compose_path):
            self.skipTest("docker-compose.yaml not present at repository root")

        import yaml

        with open(compose_path, "r", encoding="utf-8") as f:
            compose_data = yaml.safe_load(f)

        self.assertIn("services", compose_data)
        self.assertIn("web", compose_data["services"])
        web_service = compose_data["services"]["web"]

        # Check env_file contains .env
        env_file = web_service.get("env_file", [])
        if isinstance(env_file, str):
            env_file = [env_file]
        self.assertIn(".env", env_file)

        # Check environment does not hardcode DJANGO_LOG_LEVEL over .env
        env_dict = web_service.get("environment")
        if env_dict:
            if isinstance(env_dict, list):
                env_keys = [item.split("=")[0].strip() for item in env_dict if "=" in item]
            elif isinstance(env_dict, dict):
                env_keys = list(env_dict.keys())
            else:
                env_keys = []
            self.assertNotIn("DJANGO_LOG_LEVEL", env_keys)
