"""Base class for browser-driven E2E tests.

Runs headless Chromium via Playwright against the real app (routing,
templates, static files, DB) through Django's StaticLiveServerTestCase --
one test runner (`python manage.py test`), not a separate pytest setup.
The existing suite in `anthrocalc/tests.py` uses Django's TestCase; this
package is additive, not a replacement.

Setup (not part of the default install, see requirements-dev.txt):
    pip install -r requirements-dev.txt
    playwright install chromium

Run just these tests:
    python manage.py test anthrocalc.tests_e2e

If Playwright isn't installed, every test in this package skips instead of
erroring, so `python manage.py test` (no args) stays green in environments
that haven't opted into E2E testing.
"""

import os
import unittest

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

# Playwright's sync API drives an asyncio loop; Django ORM calls from setUp
# would otherwise raise SynchronousOnlyOperation under recent Playwright.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "playwright not installed - see requirements-dev.txt")
class PlaywrightTestCase(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()
        super().tearDown()

    def login_as_field_agent(self):
        """Create a user and attach a logged-in session cookie to Playwright.

        LOGIN_URL is /admin/login/. Filling that form through Playwright has
        been flaky against recent Chromium builds; establishing the session
        with Django's test client and copying ``sessionid`` is stable and
        still exercises the real authenticated views afterward.
        """
        from django.test import Client

        User = get_user_model()
        username, password = "e2e_agent", "e2e-test-pass-123"
        User.objects.create_user(username=username, password=password)

        client = Client()
        assert client.login(username=username, password=password)
        session_cookie = client.cookies["sessionid"]
        self.page.context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": session_cookie.value,
                    "url": self.live_server_url,
                }
            ]
        )
