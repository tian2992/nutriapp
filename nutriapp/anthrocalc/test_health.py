from unittest.mock import MagicMock, patch

from django.test import Client, TestCase


class HealthEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_ok_when_db_responds(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok\n")
        self.assertEqual(response["Content-Type"], "text/plain")

    def test_health_rejects_non_get(self):
        response = self.client.post("/health/")
        self.assertEqual(response.status_code, 405)

    @patch("nutriapp.health.connection.cursor")
    def test_health_unavailable_when_db_fails(self, mock_cursor):
        mock_cursor.return_value.__enter__.return_value = MagicMock(
            execute=MagicMock(side_effect=RuntimeError("boom")),
        )
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b"db unavailable\n")
