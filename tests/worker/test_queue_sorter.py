from datetime import datetime, timezone

import pytest

from contentbot.worker import queue_sorter
from contentbot.worker.queue_sorter import QueueSorter, plan_moves


def apply_moves(order, moves):
    """Simulate Cytube's moveMedia handling on a list of UIDs."""
    order = list(order)
    for move in moves:
        order.remove(move["from"])
        index = 0 if move["after"] == "prepend" else order.index(move["after"]) + 1
        order.insert(index, move["from"])
    return order


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class FakeDB:
    def __init__(self, times=None):
        self.times = dict(times or {})

    async def get_video_publish_time(self, video_id):
        return self.times.get(video_id)

    async def set_video_publish_time(self, video_id, published):
        self.times[video_id] = published


def item(uid, temp=True, media_id=None, media_type="yt"):
    return {"uid": uid, "temp": temp, "media_id": media_id or f"vid{uid}", "media_type": media_type}


# ------------------------------------------------------------------
# plan_moves
# ------------------------------------------------------------------


def test_plan_moves_already_sorted():
    assert plan_moves([1, 2, 3], [1, 2, 3]) == []


def test_plan_moves_only_moves_misplaced_item():
    moves = plan_moves([1, 5, 2, 3, 4], [1, 2, 3, 4, 5])
    assert moves == [{"from": 5, "after": 4}]


def test_plan_moves_prepend():
    moves = plan_moves([2, 3, 1], [1, 2, 3])
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
    moves = plan_moves(current, desired)
    assert apply_moves(current, moves) == desired


def test_plan_moves_minimum_count():
    # Longest run already in order is 1, 2, 3 so only 4 and 5 need to move.
    moves = plan_moves([4, 1, 2, 5, 3], [1, 2, 3, 4, 5])
    assert len(moves) == 2


# ------------------------------------------------------------------
# QueueSorter
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
    assert apply_moves([2, 1, 3, 4], result["moves"]) == [1, 3, 4, 2]


async def test_sort_queue_compares_naive_and_aware_times():
    db = FakeDB({"vid1": "2024-01-02T00:00:00+05:00", "vid2": "2024-01-01"})
    result = await QueueSorter(db).sort_queue([item(1), item(2)])

    # 2024-01-02T00:00+05:00 is 2024-01-01T19:00Z, after 2024-01-01T00:00Z.
    assert apply_moves([1, 2], result["moves"]) == [2, 1]


async def test_sort_queue_places_unknown_last(monkeypatch):
    async def fake_fetch(video_id):
        return None

    monkeypatch.setattr(queue_sorter, "fetch_publish_time", fake_fetch)
    db = FakeDB({"vid2": "2024-01-01T00:00:00+00:00", "vid4": "2023-01-01T00:00:00+00:00"})
    playlist = [item(1), item(2), item(3, media_type="vi"), item(4)]

    result = await QueueSorter(db).sort_queue(playlist)

    assert result["unknown"] == 2
    assert apply_moves([1, 2, 3, 4], result["moves"]) == [4, 2, 1, 3]


async def test_sort_queue_fetches_and_caches_missing_times(monkeypatch):
    fetched = []

    async def fake_fetch(video_id):
        fetched.append(video_id)
        return datetime(2020, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(queue_sorter, "fetch_publish_time", fake_fetch)
    db = FakeDB({"vid1": "2024-01-01T00:00:00+00:00"})

    result = await QueueSorter(db).sort_queue([item(1), item(2)])

    assert fetched == ["vid2"]
    assert db.times["vid2"] == "2020-01-01T00:00:00+00:00"
    assert apply_moves([1, 2], result["moves"]) == [2, 1]


# ------------------------------------------------------------------
# fetch_publish_time
# ------------------------------------------------------------------


async def test_fetch_publish_time_prefers_full_timestamp(monkeypatch):
    async def fake_query_endpoint(url, cookies=None):
        return FakeResponse('{"publishDate":"2024-03-20","uploadDate":"2024-03-20T05:30:00-07:00"}')

    monkeypatch.setattr(queue_sorter, "query_endpoint", fake_query_endpoint)

    result = await queue_sorter.fetch_publish_time("abc123")

    assert result == datetime(2024, 3, 20, 12, 30, tzinfo=timezone.utc)


async def test_fetch_publish_time_falls_back_to_date(monkeypatch):
    async def fake_query_endpoint(url, cookies=None):
        return FakeResponse('{"publishDate":"2024-03-20"}')

    monkeypatch.setattr(queue_sorter, "query_endpoint", fake_query_endpoint)

    result = await queue_sorter.fetch_publish_time("abc123")

    assert result == datetime(2024, 3, 20, tzinfo=timezone.utc)


async def test_fetch_publish_time_missing(monkeypatch):
    async def fake_query_endpoint(url, cookies=None):
        return FakeResponse("<html></html>")

    monkeypatch.setattr(queue_sorter, "query_endpoint", fake_query_endpoint)

    assert await queue_sorter.fetch_publish_time("abc123") is None
