import pytest
import requests

from contentbot.common.utils import api_query


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")


@pytest.fixture
def fake_get(monkeypatch):
    calls = []
    statuses = []

    def get(url, cookies=None, timeout=None):
        calls.append(url)
        return FakeResponse(statuses.pop(0) if statuses else 200)

    async def no_sleep(_):
        pass

    monkeypatch.setattr(api_query.requests, "get", get)
    monkeypatch.setattr(api_query.asyncio, "sleep", no_sleep)
    return calls, statuses


async def test_query_endpoint_returns_on_first_success(fake_get):
    calls, _ = fake_get

    resp = await api_query.query_endpoint("https://example.com")

    assert resp.status_code == 200
    assert len(calls) == 1


async def test_query_endpoint_retries_until_success(fake_get):
    calls, statuses = fake_get
    statuses.extend([500, 500])

    resp = await api_query.query_endpoint("https://example.com")

    assert resp.status_code == 200
    assert len(calls) == 3


async def test_query_endpoint_raises_after_max_retries(fake_get):
    calls, statuses = fake_get
    statuses.extend([500] * 10)

    with pytest.raises(requests.exceptions.HTTPError):
        await api_query.query_endpoint("https://example.com", max_retries=2)

    assert len(calls) == 3
