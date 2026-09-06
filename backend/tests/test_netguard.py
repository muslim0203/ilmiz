"""SSRF himoyasi: jurnal sayti / OAI manzili ichki tarmoqqa ishora qilmasin."""
import socket
import unittest
from unittest import mock

from backend.app.services import netguard


def _addrinfo(*addresses: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80)) for address in addresses]


class PublicUrlTest(unittest.TestCase):
    def test_literal_private_addresses_are_rejected(self) -> None:
        for url in (
            "http://127.0.0.1:8000/api/admin/dashboard",
            "http://10.0.0.5/",
            "http://192.168.1.1/oai",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://0.0.0.0/",
        ):
            with self.assertRaises(netguard.UnsafeURL, msg=url):
                netguard.assert_public_url(url)

    def test_internal_names_and_schemes_are_rejected_without_dns(self) -> None:
        for url in (
            "http://localhost/",
            "http://metadata.google.internal/",
            "http://ojs.corp/",
            "ftp://example.uz/",
            "file:///etc/passwd",
            "http:///path",
            "http://user:pass@example.uz/",
        ):
            with self.assertRaises(netguard.UnsafeURL, msg=url):
                netguard.assert_public_url(url, resolve=False)

    def test_public_literal_passes(self) -> None:
        self.assertEqual(netguard.assert_public_url("https://8.8.8.8/oai"), "https://8.8.8.8/oai")

    def test_hostname_resolving_to_private_address_is_rejected(self) -> None:
        with mock.patch.object(socket, "getaddrinfo", return_value=_addrinfo("93.184.216.34", "127.0.0.1")):
            with self.assertRaises(netguard.UnsafeURL):
                netguard.assert_public_url("https://evil.example/oai")

    def test_hostname_resolving_to_public_address_passes(self) -> None:
        with mock.patch.object(socket, "getaddrinfo", return_value=_addrinfo("93.184.216.34")):
            self.assertEqual(netguard.assert_public_url(" https://journal.uz/oai "), "https://journal.uz/oai")

    def test_unresolvable_host_is_rejected(self) -> None:
        with mock.patch.object(socket, "getaddrinfo", side_effect=socket.gaierror("yo'q")):
            with self.assertRaises(netguard.UnsafeURL):
                netguard.assert_public_url("https://nomavjud.example/")

    def test_no_dns_mode_accepts_public_looking_hostname(self) -> None:
        with mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS chaqirilmasligi kerak")):
            netguard.assert_public_url("https://journal.uz/", resolve=False)


class HarvesterGuardTest(unittest.TestCase):
    """Harvester `URL_GUARD` hook'i orqali manzilni so'rovdan oldin tekshiradi."""

    def test_request_is_refused_before_network(self) -> None:
        from harvester import oai_harvester
        from backend.app.services import ingest  # noqa: F401  (hook'ni o'rnatadi)

        self.assertIs(oai_harvester.URL_GUARD, netguard.assert_public_url)
        with mock.patch("harvester.oai_harvester.urllib.request.OpenerDirector.open") as opened:
            with self.assertRaises(oai_harvester.OAIError) as caught:
                oai_harvester._request("http://127.0.0.1:8000/oai", {"verb": "Identify"}, timeout=1)
        self.assertIn("rad etildi", str(caught.exception))
        opened.assert_not_called()

    def test_redirect_to_private_address_is_refused(self) -> None:
        from harvester import oai_harvester

        handler = oai_harvester._GuardedRedirectHandler()
        with mock.patch.object(oai_harvester, "URL_GUARD", netguard.assert_public_url):
            with self.assertRaises(oai_harvester.OAIError):
                handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1:8000/api/")


class ProfileFetchTest(unittest.TestCase):
    def test_redirect_chain_is_checked_at_every_hop(self) -> None:
        import httpx

        from backend.app.services import profile_collector

        first = httpx.Response(302, headers={"location": "http://127.0.0.1:8000/api/admin"}, request=httpx.Request("GET", "https://journal.uz/"))
        with mock.patch.object(socket, "getaddrinfo", return_value=_addrinfo("93.184.216.34")):
            with mock.patch.object(httpx.Client, "get", return_value=first):
                with self.assertRaises(netguard.UnsafeURL):
                    profile_collector.fetch_public("https://journal.uz/")


class JournalEditWebsiteTest(unittest.TestCase):
    def test_private_website_is_rejected_on_save(self) -> None:
        from backend.app.services import journal_edit

        with self.assertRaises(journal_edit.ValidationError):
            journal_edit._clean_website("http://127.0.0.1:8000/")
        self.assertEqual(journal_edit._clean_website("https://journal.uz/"), "https://journal.uz/")


if __name__ == "__main__":
    unittest.main()
