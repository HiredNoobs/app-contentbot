from datetime import datetime

import pytest

from contentbot.chatbot.utils import yt


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


@pytest.mark.asyncio
async def test_get_video_publish_date_uses_publish_date(monkeypatch):
    async def fake_query_endpoint(url, cookies=None):
        return FakeResponse(
            '<script>var ytInitialPlayerResponse = {"microformat":{"playerMicroformatRenderer":{"publishDate":"2024-03-20"}}};</script>'
        )

    monkeypatch.setattr(yt, "query_endpoint", fake_query_endpoint)

    result = await yt.get_video_publish_date("abc123")

    assert result == datetime(2024, 3, 20)
