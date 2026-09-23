from datetime import datetime, timezone

import pytest
import requests

from contentbot.worker import queue_sorter
from contentbot.worker.queue_sorter import QueueSorter


def apply_moves(order, moves):
    """Simulate Cytube's moveMedia handling on a list of UIDs."""
    order = list(order)
    for move in moves:
        order.remove(move["from"])
        index = 0 if move["after"] == "prepend" else order.index(move["after"]) + 1
        order.insert(index, move["from"])
    return order


class FakeResponse:
    def __init__(self, text: str = "", json_data=None):
        self.text = text
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON")
        return self._json_data


class FakeDB:
    def __init__(self, times=None, random_videos=None):
        self.times = dict(times or {})
        self.random_videos = set(random_videos or [])

    async def get_video_publish_time(self, video_id):
        return self.times.get(video_id)

    async def set_video_publish_time(self, video_id, published):
        self.times[video_id] = published

    async def is_random_video(self, video_id):
        return video_id in self.random_videos


def item(uid, temp=True, media_id=None, media_type="yt"):
    return {"uid": uid, "temp": temp, "media_id": media_id or f"vid{uid}", "media_type": media_type}


def no_fetch(monkeypatch):
    """Make every uncached lookup fail, so only cached times are known."""

    async def fake_fetch(self, video_id):
        return None

    monkeypatch.setattr(QueueSorter, "_fetch_publish_time", fake_fetch)


# ------------------------------------------------------------------
# _plan_moves
# ------------------------------------------------------------------


def test_plan_moves_already_sorted():
    assert QueueSorter._plan_moves([1, 2, 3], [1, 2, 3]) == []


def test_plan_moves_only_moves_misplaced_item():
    moves = QueueSorter._plan_moves([1, 5, 2, 3, 4], [1, 2, 3, 4, 5])
    assert moves == [{"from": 5, "after": 4}]


def test_plan_moves_prepend():
    moves = QueueSorter._plan_moves([2, 3, 1], [1, 2, 3])
    assert moves == [{"from": 1, "after": "prepend"}]


@pytest.mark.parametrize(
    "current, desired",
    [
        ([3, 2, 1], [1, 2, 3]),
        ([4, 1, 3, 2, 6, 5], [1, 2, 3, 4, 5, 6]),
        ([10, 20, 30, 40], [40, 30, 20, 10]),
        ([7, 1, 8, 2, 9, 3], [1, 2, 3, 7, 8, 9]),
    ],
)
def test_plan_moves_reaches_desired_order(current, desired):
    moves = QueueSorter._plan_moves(current, desired)
    assert apply_moves(current, moves) == desired


def test_plan_moves_minimum_count():
    # Longest run already in order is 1, 2, 3 so only 4 and 5 need to move.
    moves = QueueSorter._plan_moves([4, 1, 2, 5, 3], [1, 2, 3, 4, 5])
    assert len(moves) == 2


# ------------------------------------------------------------------
# sort_queue
# ------------------------------------------------------------------


async def test_sort_queue_orders_temp_after_permanent_by_publish_time():
    db = FakeDB(
        {
            "vid2": "2024-03-01T12:00:00+00:00",
            "vid3": "2024-01-01T12:00:00+00:00",
            "vid4": "2024-02-01T12:00:00+00:00",
        }
    )
    playlist = [item(2), item(1, temp=False), item(3), item(4)]

    result = await QueueSorter(db).sort_queue(playlist)

    assert result["type"] == "sort_queue"
    assert result["unknown"] == 0
    assert result["unknown_random"] == 0
    assert apply_moves([2, 1, 3, 4], result["moves"]) == [1, 3, 4, 2]


async def test_sort_queue_compares_naive_and_aware_times():
    db = FakeDB({"vid1": "2024-01-02T00:00:00+05:00", "vid2": "2024-01-01"})
    result = await QueueSorter(db).sort_queue([item(1), item(2)])

    # 2024-01-02T00:00+05:00 is 2024-01-01T19:00Z, after 2024-01-01T00:00Z.
    assert apply_moves([1, 2], result["moves"]) == [2, 1]


async def test_sort_queue_leaves_undated_in_place(monkeypatch):
    no_fetch(monkeypatch)
    db = FakeDB(
        {
            "vid1": "2024-03-01T00:00:00+00:00",
            "vid3": "2024-01-01T00:00:00+00:00",
            "vid5": "2024-02-01T00:00:00+00:00",
        }
    )
    # 2 is undated and 4 isn't a YouTube video; both keep their positions.
    playlist = [item(1), item(2), item(3), item(4, media_type="vi"), item(5)]

    result = await QueueSorter(db).sort_queue(playlist)

    assert result["unknown"] == 2
    assert result["unknown_random"] == 0
    assert apply_moves([1, 2, 3, 4, 5], result["moves"]) == [3, 2, 5, 4, 1]


async def test_sort_queue_moves_undated_random_to_end(monkeypatch):
    no_fetch(monkeypatch)
    db = FakeDB(
        {"vid2": "2024-02-01T00:00:00+00:00", "vid4": "2024-01-01T00:00:00+00:00"},
        random_videos={"vid1", "vid3"},
    )
    # 1 and 3 are undated random videos; 5 is undated but not random.
    playlist = [item(1), item(2), item(3), item(4), item(5)]

    result = await QueueSorter(db).sort_queue(playlist)

    assert result["unknown"] == 1
    assert result["unknown_random"] == 2
    assert apply_moves([1, 2, 3, 4, 5], result["moves"]) == [4, 2, 5, 1, 3]


async def test_sort_queue_sorts_dated_random(monkeypatch):
    no_fetch(monkeypatch)
    db = FakeDB(
        {"vid1": "2024-03-01T00:00:00+00:00", "vid2": "2024-01-01T00:00:00+00:00"},
        random_videos={"vid2"},
    )

    result = await QueueSorter(db).sort_queue([item(1), item(2)])

    assert result["unknown_random"] == 0
    assert apply_moves([1, 2], result["moves"]) == [2, 1]


async def test_sort_queue_only_fetches_uncached_times(monkeypatch):
    fetched = []

    async def fake_fetch(self, video_id):
        fetched.append(video_id)
        return datetime(2020, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(QueueSorter, "_fetch_publish_time", fake_fetch)
    db = FakeDB({"vid1": "2024-01-01T00:00:00+00:00"})

    result = await QueueSorter(db).sort_queue([item(1), item(2)])

    assert fetched == ["vid2"]
    assert apply_moves([1, 2], result["moves"]) == [2, 1]


# ------------------------------------------------------------------
# _fetch_publish_time (oEmbed -> channel page -> RSS feed)
# ------------------------------------------------------------------

CHANNEL_ID = "UCEikOr4uF0x7hbITxBw8cWw"

CHANNEL_PAGE = f'<html><link rel="canonical" href="https://www.youtube.com/channel/{CHANNEL_ID}"></html>'

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
 <published>2010-01-01T00:00:00+00:00</published>
 <entry>
  <yt:videoId>vidA</yt:videoId>
  <published>2026-09-18T15:00:00+00:00</published>
 </entry>
 <entry>
  <yt:videoId>vidB</yt:videoId>
  <published>2026-09-10T08:30:00+00:00</published>
 </entry>
</feed>"""


@pytest.fixture
def fake_youtube(monkeypatch):
    """Fake the oEmbed, channel page, and RSS endpoints, recording each requested URL."""
    requested = []
    pages = {"oembed": None, "channel": CHANNEL_PAGE, "feed": FEED}

    async def fake_query_endpoint(url, cookies=None, max_retries=5):
        requested.append(url)
        if url.startswith("https://www.youtube.com/oembed"):
            if pages["oembed"] is not None:
                return pages["oembed"]
            return FakeResponse(json_data={"author_url": "https://www.youtube.com/@buffcorrell"})
        if url.startswith("https://www.youtube.com/feeds/"):
            return FakeResponse(pages["feed"])
        return FakeResponse(pages["channel"])

    monkeypatch.setattr(queue_sorter, "query_endpoint", fake_query_endpoint)
    return requested, pages


async def test_fetch_publish_time_from_feed(fake_youtube):
    db = FakeDB()

    result = await QueueSorter(db)._fetch_publish_time("vidA")

    assert result == datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)
    # Every entry in the feed is cached, not just the requested video.
    assert db.times == {
        "vidA": "2026-09-18T15:00:00+00:00",
        "vidB": "2026-09-10T08:30:00+00:00",
    }


async def test_fetch_publish_time_shares_channel_requests(fake_youtube):
    requested, _ = fake_youtube
    sorter = QueueSorter(FakeDB())

    await sorter._fetch_publish_time("vidA")
    await sorter._fetch_publish_time("vidOld")

    # Two oEmbed lookups, but the channel page and feed are only fetched once.
    assert sum(url.startswith("https://www.youtube.com/oembed") for url in requested) == 2
    assert requested.count("https://www.youtube.com/@buffcorrell") == 1
    assert sum(url.startswith("https://www.youtube.com/feeds/") for url in requested) == 1


async def test_fetch_publish_time_not_in_feed(fake_youtube):
    assert await QueueSorter(FakeDB())._fetch_publish_time("vidOld") is None


async def test_fetch_publish_time_oembed_failure(fake_youtube):
    _, pages = fake_youtube
    pages["oembed"] = FakeResponse()

    assert await QueueSorter(FakeDB())._fetch_publish_time("vidA") is None


async def test_fetch_publish_time_request_failure(monkeypatch):
    async def fake_query_endpoint(url, cookies=None, max_retries=5):
        raise requests.exceptions.HTTPError("404 Not Found")

    monkeypatch.setattr(queue_sorter, "query_endpoint", fake_query_endpoint)

    assert await QueueSorter(FakeDB())._fetch_publish_time("vidA") is None


async def test_fetch_publish_time_no_channel_id(fake_youtube):
    _, pages = fake_youtube
    pages["channel"] = "<html></html>"

    assert await QueueSorter(FakeDB())._fetch_publish_time("vidA") is None


async def test_sort_queue_resets_lookups_between_sorts(fake_youtube):
    requested, _ = fake_youtube
    sorter = QueueSorter(FakeDB())

    await sorter.sort_queue([item(1, media_id="vidOld")])
    await sorter.sort_queue([item(1, media_id="vidOld")])

    # Feeds aren't reused across sorts, so a newly uploaded video can be found.
    assert sum(url.startswith("https://www.youtube.com/feeds/") for url in requested) == 2
