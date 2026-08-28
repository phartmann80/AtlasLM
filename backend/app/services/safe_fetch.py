"""Fetch public HTTP(S) pages without following them into private networks."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import ParseResult, urljoin, urlparse, urlunparse

import httpx

MAX_HTML_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
ALLOWED_SCHEMES = {"http", "https"}
CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 15.0
USER_AGENT = "Mozilla/5.0 (compatible; AtlasLM/1.0; +https://atlaslm.app)"

_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
}

_BLOCKED_HOSTNAME_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".intranet",
    ".corp",
    ".home",
    ".lan",
)


class PublicFetchError(Exception):
    """Safe-to-show failure while validating or fetching a public URL."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def is_blocked_ip(value: str) -> bool:
    """True when an address is not a globally routable unicast IP."""
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return True

    if addr.version == 6:
        mapped = addr.ipv4_mapped
        if mapped is not None:
            return is_blocked_ip(str(mapped))
        sixtofour = addr.sixtofour
        if sixtofour is not None:
            return is_blocked_ip(str(sixtofour))
        teredo = addr.teredo
        if teredo is not None:
            server, client = teredo
            return is_blocked_ip(str(server)) or is_blocked_ip(str(client))

    return not addr.is_global


def _hostname_is_blocked(hostname: str) -> bool:
    host = hostname.rstrip(".").lower()
    if not host or host in _BLOCKED_HOSTNAMES:
        return True
    return any(host.endswith(suffix) for suffix in _BLOCKED_HOSTNAME_SUFFIXES)


def _as_ip(hostname: str):
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        return None


def _allowed_port(scheme: str, port: int | None) -> bool:
    if port is None:
        return True
    if scheme == "http":
        return port == 80
    if scheme == "https":
        return port == 443
    return False


def normalize_public_http_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        raise PublicFetchError("URL is required")
    if not urlparse(url).scheme:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise PublicFetchError("URL must start with http:// or https://")
    validate_public_url(url)
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            parsed.path or "",
            parsed.params,
            parsed.query,
            "",
        )
    )


def validate_public_url(url: str) -> ParseResult:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise PublicFetchError("URL must start with http:// or https://")
    if parsed.username is not None or parsed.password is not None:
        raise PublicFetchError("That URL is not a public web page AtlasLM can fetch.")
    hostname = parsed.hostname
    if not hostname:
        raise PublicFetchError("URL is required")
    if _hostname_is_blocked(hostname):
        raise PublicFetchError("That URL is not a public web page AtlasLM can fetch.")
    if not _allowed_port(scheme, parsed.port):
        raise PublicFetchError("That URL is not a public web page AtlasLM can fetch.")
    literal = _as_ip(hostname)
    if literal is not None and is_blocked_ip(str(literal)):
        raise PublicFetchError("That URL is not a public web page AtlasLM can fetch.")
    return parsed


def resolve_host_ips(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise PublicFetchError(
            "AtlasLM could not reach that URL. Check the address and try again."
        ) from exc

    ips: list[str] = []
    for info in infos:
        addr = info[4][0]
        if "%" in addr:
            addr = addr.split("%", 1)[0]
        if addr not in ips:
            ips.append(addr)
    if not ips:
        raise PublicFetchError(
            "AtlasLM could not reach that URL. Check the address and try again."
        )
    return ips


def require_public_resolved_ips(hostname: str) -> list[str]:
    literal = _as_ip(hostname)
    if literal is not None:
        if is_blocked_ip(str(literal)):
            raise PublicFetchError("That URL is not a public web page AtlasLM can fetch.")
        return [str(literal)]

    ips = resolve_host_ips(hostname)
    if any(is_blocked_ip(ip) for ip in ips):
        raise PublicFetchError("That URL is not a public web page AtlasLM can fetch.")
    return ips


def _host_header(parsed: ParseResult) -> str:
    hostname = parsed.hostname or ""
    addr = _as_ip(hostname)
    if addr is not None and addr.version == 6:
        host = f"[{hostname}]"
    else:
        host = hostname
    port = parsed.port
    default = 443 if parsed.scheme == "https" else 80
    if port and port != default:
        return f"{host}:{port}"
    return host


def _pin_url_to_ip(parsed: ParseResult, ip: str) -> str:
    addr = ipaddress.ip_address(ip)
    host = f"[{ip}]" if addr.version == 6 else ip
    port = parsed.port
    netloc = f"{host}:{port}" if port else host
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )


async def read_limited_body(response: httpx.Response, max_bytes: int | None = None) -> bytes:
    limit = MAX_HTML_BYTES if max_bytes is None else max_bytes
    content_length = response.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > limit:
        raise PublicFetchError("That page is too large for AtlasLM to import.")

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        if not chunk:
            continue
        if total + len(chunk) > limit:
            raise PublicFetchError("That page is too large for AtlasLM to import.")
        total += len(chunk)
        chunks.append(chunk)
    return b"".join(chunks)


async def download_public_html(
    url: str,
    *,
    transport=None,
) -> bytes:
    current = normalize_public_http_url(url)
    seen: set[str] = set()
    redirects = 0
    timeout = httpx.Timeout(READ_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS)
    client_kwargs = {
        "follow_redirects": False,
        "timeout": timeout,
        "trust_env": False,
        "headers": {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    }
    if transport is not None:
        client_kwargs["transport"] = transport

    async with httpx.AsyncClient(**client_kwargs) as client:
        while True:
            if current in seen:
                raise PublicFetchError(
                    "AtlasLM could not reach that URL. Check the address and try again."
                )
            seen.add(current)

            parsed = validate_public_url(current)
            hostname = parsed.hostname or ""
            ips = require_public_resolved_ips(hostname)
            pinned = _pin_url_to_ip(parsed, ips[0])
            headers = {"Host": _host_header(parsed)}
            extensions = {}
            if parsed.scheme == "https":
                extensions["sni_hostname"] = hostname

            request = client.build_request(
                "GET",
                pinned,
                headers=headers,
                extensions=extensions,
            )
            try:
                response = await client.send(request, stream=True)
            except PublicFetchError:
                raise
            except Exception as exc:
                raise PublicFetchError(
                    "AtlasLM could not reach that URL. Check the address and try again."
                ) from exc

            try:
                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not location:
                        raise PublicFetchError(
                            "AtlasLM could not reach that URL. Check the address and try again."
                        )
                    redirects += 1
                    if redirects > MAX_REDIRECTS:
                        raise PublicFetchError(
                            "AtlasLM could not reach that URL. Check the address and try again."
                        )
                    current = urljoin(current, location)
                    continue

                if response.status_code >= 400:
                    raise PublicFetchError(
                        "AtlasLM could not reach that URL. Check the address and try again."
                    )

                content_type = response.headers.get("content-type", "")
                if (
                    content_type
                    and "text/html" not in content_type
                    and "xml" not in content_type
                ):
                    raise PublicFetchError(
                        "The URL did not return a web page. Only HTML pages are supported for now.",
                        status_code=422,
                    )
                return await read_limited_body(response)
            finally:
                await response.aclose()
