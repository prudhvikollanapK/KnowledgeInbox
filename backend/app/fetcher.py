import asyncio
import ipaddress
import re
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import aiohttp
import certifi
from aiohttp.abc import AbstractResolver
from bs4 import BeautifulSoup

from .errors import AppError

MAX_PAGE_BYTES = 2_000_000
MAX_CONTENT_CHARS = 100_000


def is_public_ip(host: str) -> bool:
    address = ipaddress.ip_address(host.split("%")[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def validate_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Use a complete http:// or https:// URL.")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing credentials are not supported.")
        if parsed.port not in (None, 80, 443):
            raise ValueError("Only standard HTTP and HTTPS ports are supported.")
        host = parsed.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("Only publicly accessible websites can be saved.")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if re.fullmatch(r"[0-9.]+", host):
                raise ValueError("Use a complete public IP address or website hostname.") from None
            if "." not in host:
                raise ValueError("Use a public website hostname.") from None
        else:
            if not is_public_ip(host):
                raise ValueError("Private and reserved network addresses are blocked.")
    except ValueError as exc:
        raise AppError("invalid_url", str(exc), 422) from None


class PublicResolver(AbstractResolver):
    """Validate actual connection addresses, avoiding a check-then-resolve DNS race."""

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        addresses = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            family=family,
            type=socket.SOCK_STREAM,
        )
        if not addresses or any(not is_public_ip(row[4][0]) for row in addresses):
            raise AppError("blocked_address", "This URL resolves to a non-public network address.")
        return [
            {
                "hostname": host,
                "host": address[0],
                "port": port,
                "family": af,
                "proto": proto,
                "flags": socket.AI_NUMERICHOST,
            }
            for af, _, proto, _, address in addresses
        ]

    async def close(self) -> None:
        pass


@dataclass
class FetchedPage:
    title: str
    raw_content: str
    text: str
    resolved_url: str
    content_type: str


def extract_page(raw: str, content_type: str, url: str) -> FetchedPage:
    title = urlsplit(url).hostname or "Saved page"
    if content_type == "text/plain":
        text = raw.strip()
    else:
        soup = BeautifulSoup(raw, "html.parser")
        if soup.title:
            title = soup.title.get_text(" ", strip=True)[:180] or title
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            element.decompose()
        body = soup.find("article") or soup.find("main") or soup.body or soup
        lines = [line.strip() for line in body.get_text("\n").splitlines()]
        text = "\n".join(line for line in lines if line)
    if not text:
        raise AppError("empty_page", "No readable text was found. Try pasting a note instead.")
    if len(text) > MAX_CONTENT_CHARS:
        raise AppError("page_too_long", "Page exceeds 100,000 characters. Save a shorter excerpt.")
    return FetchedPage(title, raw, text, url, content_type)


async def fetch_page(url: str) -> FetchedPage:
    # Windows Python installations can have an incomplete system CA store. Add the
    # maintained public roots while retaining OS/SSL_CERT_FILE trust and TLS checks.
    tls_context = ssl.create_default_context()
    tls_context.load_verify_locations(certifi.where())
    connector = aiohttp.TCPConnector(
        resolver=PublicResolver(),
        use_dns_cache=False,
        ssl=tls_context,
    )
    timeout = aiohttp.ClientTimeout(total=20, connect=8)
    try:
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=False,
            cookie_jar=aiohttp.DummyCookieJar(),
            headers={"User-Agent": "CommonplaceKnowledgeInbox/1.0"},
        ) as session:
            for _ in range(5):
                validate_url(url)
                async with session.get(url, allow_redirects=False) as response:
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise AppError(
                                "invalid_redirect", "The page returned an empty redirect."
                            )
                        url = urljoin(url, location)
                        continue
                    if response.status >= 400:
                        raise AppError(
                            "fetch_failed", f"The website returned HTTP {response.status}."
                        )
                    content_type = response.content_type
                    if content_type not in ("text/html", "application/xhtml+xml", "text/plain"):
                        raise AppError(
                            "unsupported_page", "Only HTML and plain text pages are supported."
                        )
                    body = bytearray()
                    async for part in response.content.iter_chunked(16_384):
                        body.extend(part)
                        if len(body) > MAX_PAGE_BYTES:
                            raise AppError(
                                "page_too_large", "Page exceeds the 2 MB download limit."
                            )
                    try:
                        raw = body.decode(response.charset or "utf-8", errors="replace")
                    except LookupError:
                        raw = body.decode("utf-8", errors="replace")
                    return await asyncio.to_thread(extract_page, raw, content_type, url)
            raise AppError("too_many_redirects", "The website redirected too many times.")
    except aiohttp.ClientConnectorCertificateError as exc:
        raise AppError(
            "certificate_error",
            "Could not verify this website's TLS certificate. "
            "Check the system CA configuration or save a text excerpt instead.",
        ) from exc
    except (TimeoutError, aiohttp.ClientError, OSError) as exc:
        raise AppError(
            "fetch_unavailable", "Could not fetch this page. Check the URL and try again."
        ) from exc
