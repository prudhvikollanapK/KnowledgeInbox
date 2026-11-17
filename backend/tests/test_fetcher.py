import socket
from unittest.mock import AsyncMock

import pytest

from backend.app.errors import AppError
from backend.app.fetcher import PublicResolver, extract_page, fetch_page, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.1",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]",
        "http://[::ffff:127.0.0.1]",
        "http://192.168.1.1",
        "http://127.1",
        "http://localhost.",
        "http://service.internal",
        "ftp://example.com/file",
        "https://user:pass@example.com",
        "http://224.0.0.1",
    ],
)
def test_blocks_non_public_urls(url):
    with pytest.raises(AppError):
        validate_url(url)


async def test_resolver_checks_actual_connection_addresses(monkeypatch):
    import asyncio

    loop = asyncio.get_running_loop()
    resolver = AsyncMock(
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    )
    monkeypatch.setattr(loop, "getaddrinfo", resolver)
    with pytest.raises(AppError, match="non-public"):
        await PublicResolver().resolve("innocent.example.com", 443)
    resolver.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))]
    result = await PublicResolver().resolve("example.com", 443)
    assert result[0]["host"] == "93.184.215.14"
    assert result[0]["hostname"] == "example.com"


def test_extracts_article_and_removes_page_chrome():
    raw = (
        "<html><title>Good title</title><nav>Navigation</nav><main><h1>Useful</h1>"
        "<p>Readable text.</p><script>bad()</script></main><footer>Noise</footer></html>"
    )
    page = extract_page(raw, "text/html", "https://example.com")
    assert page.title == "Good title"
    assert page.raw_content == raw
    assert "Readable text." in page.text
    assert all(word not in page.text for word in ["Navigation", "bad()", "Noise"])
    with pytest.raises(AppError, match="No readable"):
        extract_page("<html><script>foo</script></html>", "text/html", "https://example.com")


async def test_redirect_to_private_address_is_blocked(monkeypatch):
    class Redirect:
        status = 302
        headers = {"Location": "http://169.254.169.254/latest/meta-data"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Session:
        def __init__(self, **kwargs):
            self.connector = kwargs["connector"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.connector.close()

        def get(self, url, **kwargs):
            assert url == "https://example.com"
            assert kwargs["allow_redirects"] is False
            return Redirect()

    monkeypatch.setattr("backend.app.fetcher.aiohttp.ClientSession", Session)
    with pytest.raises(AppError, match="blocked"):
        await fetch_page("https://example.com")
