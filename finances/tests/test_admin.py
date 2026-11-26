from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from finances.models import SiteSettings


# Admin pages reference static files; skip the collectstatic manifest in tests.
@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class SiteSettingsAdminTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser("admin", password="x")
        self.client.force_login(admin)

    def test_changelist_redirects_to_the_single_settings_object(self):
        response = self.client.get(reverse("admin:finances_sitesettings_changelist"))
        settings = SiteSettings.objects.get()
        self.assertRedirects(
            response, reverse("admin:finances_sitesettings_change", args=[settings.pk])
        )

    def test_add_only_allowed_until_settings_exist(self):
        add_url = reverse("admin:finances_sitesettings_add")
        self.assertEqual(self.client.get(add_url).status_code, 200)
        SiteSettings.get()
        self.assertEqual(self.client.get(add_url).status_code, 403)

    def test_settings_cannot_be_deleted(self):
        settings = SiteSettings.get()
        url = reverse("admin:finances_sitesettings_delete", args=[settings.pk])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        self.assertTrue(SiteSettings.objects.exists())
