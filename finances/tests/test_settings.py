import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
PROBE = (
    "import json, django; from django.conf import settings; django.setup(); "
    "print(json.dumps({k: getattr(settings, k) for k in "
    "['SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'SECURE_PROXY_SSL_HEADER', "
    "'SECURE_HSTS_SECONDS', 'SECURE_HSTS_INCLUDE_SUBDOMAINS', 'TIME_ZONE']}))"
)


def load_settings(**env):
    """Import settings in a fresh interpreter, as a server process would."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
    clean["DJANGO_SETTINGS_MODULE"] = "otter_finance_manager.settings"
    return subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=ROOT,
        env={**clean, **env},
        capture_output=True,
        text=True,
        check=False,
    )


class ProductionSettingsTests(SimpleTestCase):
    def test_refuses_to_start_without_secret_key_when_not_debug(self):
        result = load_settings()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_debug_mode_falls_back_to_dev_key(self):
        result = load_settings(DJANGO_DEBUG="1")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_https_settings_are_off_by_default(self):
        result = load_settings(DJANGO_SECRET_KEY="x" * 50)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "SESSION_COOKIE_SECURE": False,
                "CSRF_COOKIE_SECURE": False,
                "SECURE_PROXY_SSL_HEADER": None,
                "SECURE_HSTS_SECONDS": 0,
                "SECURE_HSTS_INCLUDE_SUBDOMAINS": False,
                "TIME_ZONE": "Europe/Zurich",
            },
        )

    def test_https_settings_opt_in(self):
        result = load_settings(
            DJANGO_SECRET_KEY="x" * 50,
            DJANGO_HTTPS="true",
            DJANGO_BEHIND_PROXY="yes",
            DJANGO_HSTS_SECONDS="31536000",
            DJANGO_TIME_ZONE="America/New_York",
        )
        self.assertEqual(
            json.loads(result.stdout),
            {
                "SESSION_COOKIE_SECURE": True,
                "CSRF_COOKIE_SECURE": True,
                "SECURE_PROXY_SSL_HEADER": ["HTTP_X_FORWARDED_PROTO", "https"],
                "SECURE_HSTS_SECONDS": 31536000,
                "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
                "TIME_ZONE": "America/New_York",
            },
        )
