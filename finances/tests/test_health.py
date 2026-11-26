from django.test import TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["finance.example.com"])
class HealthCheckTests(TestCase):
    def test_healthz_answers_without_login_or_allowed_host(self):
        # Container health checks call http://localhost:8000/healthz.
        response = self.client.get("/healthz", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_other_paths_still_validate_the_host(self):
        response = self.client.get("/accounts/login/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 400)
