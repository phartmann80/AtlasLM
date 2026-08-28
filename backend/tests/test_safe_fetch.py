"""SSRF and stream-limit tests for public website fetching."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import httpx

from app.services.safe_fetch import (
    PublicFetchError,
    download_public_html,
    is_blocked_ip,
    normalize_public_http_url,
    read_limited_body,
    require_public_resolved_ips,
    validate_public_url,
)

PUBLIC_IP = "93.184.216.34"


class _HeaderStream:
    def __init__(self, chunks, headers=None, infinite=False):
        self._chunks = chunks
        self._infinite = infinite
        self.headers = headers or {}

    async def aiter_bytes(self):
        if self._infinite:
            while True:
                yield b"x" * 1024
        else:
            for chunk in self._chunks:
                yield chunk


class BlockedAddressTests(unittest.TestCase):
    def test_literal_private_and_metadata_addresses_are_blocked(self) -> None:
        blocked = [
            "127.0.0.1",
            "10.1.2.3",
            "10.0.0.0",
            "172.16.0.1",
            "172.31.255.1",
            "192.168.1.1",
            "169.254.169.254",
            "169.254.0.1",
            "::1",
            "0.0.0.0",
            "100.64.0.1",
            "::ffff:127.0.0.1",
            "::ffff:10.0.0.1",
            "fe80::1",
        ]
        for ip in blocked:
            with self.subTest(ip=ip):
                self.assertTrue(is_blocked_ip(ip), ip)

    def test_public_unicast_is_allowed(self) -> None:
        self.assertFalse(is_blocked_ip(PUBLIC_IP))
        self.assertFalse(is_blocked_ip("8.8.8.8"))


class UrlValidationTests(unittest.TestCase):
    def test_loopback_and_private_literals_are_rejected(self) -> None:
        urls = [
            "http://127.0.0.1/",
            "https://127.0.0.1/secret",
            "http://localhost/",
            "http://LOCALHOST/admin",
            "http://[::1]/",
            "https://[::1]:443/",
            "http://10.0.0.5/internal",
            "http://172.16.0.2/",
            "http://192.168.0.10/",
            "http://169.254.169.254/latest/meta-data/",
        ]
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(PublicFetchError):
                    validate_public_url(url)

    def test_non_http_schemes_and_ports_are_rejected(self) -> None:
        with self.assertRaises(PublicFetchError):
            normalize_public_http_url("file:///etc/passwd")
        with self.assertRaises(PublicFetchError):
            validate_public_url("http://example.com:8080/")
        with self.assertRaises(PublicFetchError):
            validate_public_url("https://example.com:444/")
        with self.assertRaises(PublicFetchError):
            validate_public_url("http://user@example.com/")

    def test_https_is_added_when_scheme_is_missing(self) -> None:
        self.assertEqual(
            normalize_public_http_url("example.com/article"),
            "https://example.com/article",
        )

    def test_hostname_resolving_to_private_ip_is_rejected(self) -> None:
        with patch("app.services.safe_fetch.resolve_host_ips", return_value=["10.0.0.8"]):
            with self.assertRaises(PublicFetchError):
                require_public_resolved_ips("intranet.example")

    def test_mixed_public_and_private_dns_results_are_rejected(self) -> None:
        with patch(
            "app.services.safe_fetch.resolve_host_ips",
            return_value=[PUBLIC_IP, "10.0.0.8"],
        ):
            with self.assertRaises(PublicFetchError):
                require_public_resolved_ips("mixed.example")


class FetchGuardTests(unittest.TestCase):
    def test_redirect_to_private_address_is_not_followed(self) -> None:
        hits: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            hits.append(str(request.url))
            return httpx.Response(
                302,
                headers={"Location": "http://127.0.0.1/secret"},
            )

        with patch(
            "app.services.safe_fetch.resolve_host_ips",
            return_value=[PUBLIC_IP],
        ):
            with self.assertRaises(PublicFetchError):
                asyncio.run(
                    download_public_html(
                        "https://public.example/page",
                        transport=httpx.MockTransport(handler),
                    )
                )
        self.assertEqual(len(hits), 1)
        self.assertIn(PUBLIC_IP, hits[0])
        self.assertNotIn("127.0.0.1", "".join(hits))

    def test_oversized_and_indefinite_streams_are_cut_off(self) -> None:
        oversized = _HeaderStream(
            [b"a" * 600, b"b" * 600],
            headers={"content-type": "text/html"},
        )
        with self.assertRaises(PublicFetchError):
            asyncio.run(read_limited_body(oversized, max_bytes=1024))

        infinite = _HeaderStream(
            [],
            headers={"content-type": "text/html"},
            infinite=True,
        )
        with self.assertRaises(PublicFetchError):
            asyncio.run(read_limited_body(infinite, max_bytes=2048))

    def test_public_html_is_streamed_up_to_the_limit(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=b"<html>ok</html>",
            )

        with patch(
            "app.services.safe_fetch.resolve_host_ips",
            return_value=[PUBLIC_IP],
        ):
            body = asyncio.run(
                download_public_html(
                    "https://example.com/article",
                    transport=httpx.MockTransport(handler),
                )
            )
        self.assertEqual(body, b"<html>ok</html>")


if __name__ == "__main__":
    unittest.main()
