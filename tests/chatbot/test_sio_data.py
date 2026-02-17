import datetime

from cytubebot.src.cytubebot.chatbot.sio_data import SIOData


class TestSIOData:
    def test_setters(self):
        sio = SIOData()

        sio.lock = True
        assert sio.lock is True

        test_media = {"url": "http://example.com"}
        sio.current_media = test_media
        assert sio.current_media == test_media

        sio.users = {"Alice": {"rank": 1}}
        assert sio.users == {"Alice": {"rank": 1}}

    def test_can_retry_no_last_retry(self):
        sio = SIOData()
        sio._last_retry = None
        assert sio.can_retry() is True

    def test_can_retry_insufficient_time(self):
        sio = SIOData()
        now = datetime.datetime.now()
        sio._last_retry = now - datetime.timedelta(seconds=sio.current_backoff - 1)
        assert sio.can_retry() is False

    def test_can_retry_sufficient_time(self):
        sio = SIOData()
        now = datetime.datetime.now()
        sio._last_retry = now - datetime.timedelta(seconds=sio.current_backoff + 1)
        assert sio.can_retry() is True

    def test_reset_backoff_with_recent_retry(self):
        sio = SIOData()
        sio._current_backoff = 10
        retry_cooloff_period = 10
        now = datetime.datetime.now()
        sio._last_retry = now - datetime.timedelta(seconds=retry_cooloff_period - 1)
        original_backoff = sio.current_backoff
        sio.reset_backoff()
        assert sio.current_backoff == original_backoff

    def test_reset_backoff_without_recent_retry(self):
        sio = SIOData()
        sio._current_backoff = 10
        base_backoff = 4
        backoff_factor = sio.backoff_factor
        retry_cooloff_period = 10
        sio._last_retry = datetime.datetime.now() - datetime.timedelta(
            seconds=retry_cooloff_period + 1
        )
        sio.reset_backoff()
        expected = max(10 - backoff_factor, base_backoff)
        assert sio.current_backoff == expected

    def test_reset_backoff_with_no_last_retry(self):
        sio = SIOData()
        sio._current_backoff = 10
        sio._last_retry = None
        base_backoff = 4
        backoff_factor = sio.backoff_factor
        sio.reset_backoff()
        expected = max(10 - backoff_factor, base_backoff)
        assert sio.current_backoff == expected

    def test_increase_backoff(self):
        sio = SIOData()
        sio._current_backoff = 10
        max_backoff = sio.max_backoff
        backoff_factor = sio.backoff_factor
        sio.increase_backoff()
        expected = min(10 + backoff_factor, max_backoff)
        assert sio.current_backoff == expected

        sio._current_backoff = max_backoff
        sio.increase_backoff()
        assert sio.current_backoff == max_backoff

    def test_add_or_update_user(self):
        sio = SIOData()
        sio.add_or_update_user("user1", {"rank": 1})
        assert sio.users.get("user1") == {"rank": 1}

        sio.add_or_update_user("user1", {"rank": 2})
        assert sio.users.get("user1") == {"rank": 2}

    def test_remove_user(self):
        sio = SIOData()
        sio.add_or_update_user("user1", {"rank": 1})
        sio.add_or_update_user("user2", {"rank": 1})
        sio.remove_user("user1")
        assert "user1" not in sio.users
        sio.remove_user("nonexistent")
        assert "user2" in sio.users
