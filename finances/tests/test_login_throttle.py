from django.test import TestCase
from django.urls import reverse

from . import factories as f


class LoginThrottleTests(TestCase):
    """Repeated wrong passwords lock that username (from that IP) for a while."""

    def setUp(self):
        self.alice = f.user("alice")
        f.user("bob")

    def attempt(self, username, password):
        return self.client.post(
            reverse("login"), {"username": username, "password": password}
        )

    def test_locks_after_five_failures_even_with_the_right_password(self):
        for _ in range(4):
            self.assertEqual(self.attempt("alice", "wrong").status_code, 200)
        # The 5th failure itself is answered with the lockout page...
        self.assertEqual(self.attempt("alice", "wrong").status_code, 429)
        # ...and from then on even the right password is refused.
        response = self.attempt("alice", "pass1234")
        self.assertEqual(response.status_code, 429)
        self.assertContains(
            response, "Too many failed sign-in attempts", status_code=429
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lock_is_per_username_not_for_everyone_behind_the_same_ip(self):
        for _ in range(5):
            self.attempt("alice", "wrong")
        response = self.attempt("bob", "pass1234")
        self.assertRedirects(response, reverse("finances:dashboard"))

    def test_success_resets_the_counter(self):
        for _ in range(4):
            self.attempt("alice", "wrong")
        self.assertRedirects(
            self.attempt("alice", "pass1234"), reverse("finances:dashboard")
        )
        self.client.post(reverse("logout"))
        for _ in range(4):
            self.attempt("alice", "wrong")
        self.assertRedirects(
            self.attempt("alice", "pass1234"), reverse("finances:dashboard")
        )


class ClientIpTests(TestCase):
    """Behind one reverse proxy the client is the address the proxy appended."""

    def ip(self, xff=None):
        from django.test import RequestFactory

        from finances.parsing import client_ip_behind_proxy

        extra = {"HTTP_X_FORWARDED_FOR": xff} if xff is not None else {}
        request = RequestFactory().get("/", REMOTE_ADDR="172.18.0.5", **extra)
        return client_ip_behind_proxy(request)

    def test_single_forwarded_address_is_the_client(self):
        self.assertEqual(self.ip("81.62.10.5"), "81.62.10.5")

    def test_forged_left_entries_are_ignored(self):
        # The client sent "X-Forwarded-For: 6.6.6.6"; the proxy appended the real IP.
        self.assertEqual(self.ip("6.6.6.6, 81.62.10.5"), "81.62.10.5")

    def test_without_header_falls_back_to_the_socket_address(self):
        self.assertEqual(self.ip(), "172.18.0.5")
        self.assertEqual(self.ip(" "), "172.18.0.5")
