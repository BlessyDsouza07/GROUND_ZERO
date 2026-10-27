import httpx
import pytest

from layer0.infrastructure.http_client import ResilientHttpClient, RetryConfig, SourceUnavailable


class FakeResponse:
    def __init__(self, status_code: int, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        raise RuntimeError("should not be called for handled status codes")


class FakeAsyncClient:
    def __init__(self, response: FakeResponse):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, params=None, json=None, headers=None):
        return self.response


@pytest.mark.asyncio
async def test_request_raises_source_unavailable_for_overpass_406(monkeypatch):
    client = ResilientHttpClient(retry_config=RetryConfig(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0))
    monkeypatch.setattr("layer0.infrastructure.http_client.httpx.AsyncClient", lambda *args, **kwargs: FakeAsyncClient(FakeResponse(406, {})))

    with pytest.raises(SourceUnavailable) as exc_info:
        await client.request("openstreetmap", "POST", "https://example.test")

    assert exc_info.value.source == "openstreetmap"
    assert exc_info.value.status_code == 406


@pytest.mark.asyncio
async def test_request_raises_source_unavailable_for_transport_error(monkeypatch):
    client = ResilientHttpClient(retry_config=RetryConfig(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0))

    class ExplodingAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, params=None, json=None, headers=None):
            raise httpx.RemoteProtocolError("server disconnected")

    monkeypatch.setattr("layer0.infrastructure.http_client.httpx.AsyncClient", lambda *args, **kwargs: ExplodingAsyncClient())

    with pytest.raises(SourceUnavailable) as exc_info:
        await client.request("openstreetmap", "POST", "https://example.test")

    assert exc_info.value.source == "openstreetmap"
    assert exc_info.value.status_code is None
