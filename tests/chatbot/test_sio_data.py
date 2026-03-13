from datetime import datetime

import pytest

from contentbot.chatbot.sio_data import SIOData
from contentbot.exceptions import QueueError


class FakeIncomingMessage:
    def __init__(self, body="test"):
        self.body = body


# https://github.com/calzoneman/sync/blob/589f999a9c526bf773a8b21ecf29ba30faf14739/src/channel/permissions.js#L4
DEFAULT_PERMISSIONS = {
    "seeplaylist": -1,
    "playlistadd": 1.5,
    "playlistdelete": 2,
    "playlistaddcustom": 3,
    "chat": 0,
    "pollvote": -1,
    "kick": 1.5,
    "ban": 2,
    "motdedit": 3,
}


class TestSIOData:

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    def test_user_setter_getter(self):
        data = SIOData()
        data.user = "alice"
        assert data.user == "alice"

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    def test_current_media_setter_getter(self):
        data = SIOData()
        media = {"id": "abc123", "currentTime": 0}
        data.current_media = media
        assert data.current_media == media

    def test_update_current_time(self):
        data = SIOData()
        data.current_media = {"id": "abc123", "currentTime": 0}

        data.update_current_time(42.5)
        assert data.current_media["currentTime"] == 42.5

    def test_update_current_time_no_media(self):
        data = SIOData()
        data.update_current_time(10.0)
        assert data.current_media is None

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def test_add_or_update_user(self):
        data = SIOData()
        data.add_or_update_user("alice", 2)
        assert data.users["alice"] == 2

        data.add_or_update_user("alice", 3)
        assert data.users["alice"] == 3

    def test_remove_user(self):
        data = SIOData()
        data.add_or_update_user("alice", 2)
        data.remove_user("alice")
        assert "alice" not in data.users

    # ------------------------------------------------------------------
    # Permission Logic
    # ------------------------------------------------------------------

    @pytest.fixture
    def perm_data(self):
        d = SIOData()
        d.channel_permissions = DEFAULT_PERMISSIONS
        return d

    def test_permission_negative_rank(self, perm_data):
        perm_data.add_or_update_user("alice", 0)
        assert perm_data.has_permission("alice", "seeplaylist") is True
        assert perm_data.has_permission("alice", "pollvote") is True

    def test_permission_zero_rank(self, perm_data):
        perm_data.add_or_update_user("alice", 0)
        assert perm_data.has_permission("alice", "chat") is True

    def test_permission_fractional_rank(self, perm_data):
        perm_data.add_or_update_user("alice", 1)
        perm_data.add_or_update_user("bob", 2)

        assert perm_data.has_permission("alice", "kick") is False
        assert perm_data.has_permission("bob", "kick") is True

    def test_permission_moderator_level(self, perm_data):
        perm_data.add_or_update_user("mod", 2)
        perm_data.add_or_update_user("admin", 3)

        assert perm_data.has_permission("mod", "ban") is True
        assert perm_data.has_permission("admin", "ban") is True

    def test_permission_admin_level(self, perm_data):
        perm_data.add_or_update_user("mod", 2)
        perm_data.add_or_update_user("admin", 3)

        assert perm_data.has_permission("mod", "motdedit") is False
        assert perm_data.has_permission("admin", "motdedit") is True

    def test_missing_permission(self, perm_data):
        perm_data.add_or_update_user("alice", 3)
        assert perm_data.has_permission("alice", "nonexistent_perm") is False

    def test_missing_user(self, perm_data):
        assert perm_data.has_permission("ghost", "chat") is True
        assert perm_data.has_permission("ghost", "playlistdelete") is False

    # ------------------------------------------------------------------
    # Admin / Moderator helpers
    # ------------------------------------------------------------------

    def test_is_user_admin(self):
        data = SIOData()
        data.add_or_update_user("alice", 3)
        assert data.is_user_admin("alice") is True
        assert data.is_user_admin("bob") is False

    def test_is_user_moderator(self):
        data = SIOData()
        data.add_or_update_user("alice", 2)
        assert data.is_user_moderator("alice") is True
        assert data.is_user_moderator("bob") is False

    # ------------------------------------------------------------------
    # Only remaining user
    # ------------------------------------------------------------------

    def test_only_remaining_user(self):
        data = SIOData()
        data.logged_in = True
        data.user = "bot"

        data.add_or_update_user("bot", 3)
        assert data.only_remaining_user() is True

        data.add_or_update_user("alice", 1)
        assert data.only_remaining_user() is False

    # ------------------------------------------------------------------
    # Pending queue
    # ------------------------------------------------------------------

    def test_add_pending(self):
        data = SIOData()
        msg = FakeIncomingMessage()

        data.add_pending("vid123", msg)
        assert data.get_pending("vid123") is msg

    def test_add_pending_duplicate_raises(self):
        data = SIOData()
        msg = FakeIncomingMessage()

        data.add_pending("vid123", msg)
        with pytest.raises(QueueError):
            data.add_pending("vid123", msg)

    def test_remove_pending(self):
        data = SIOData()
        msg = FakeIncomingMessage()

        data.add_pending("vid123", msg)
        data.remove_pending("vid123")

        assert data.get_pending("vid123") is None

    # ------------------------------------------------------------------
    # Content pull timestamps
    # ------------------------------------------------------------------

    def test_update_and_get_last_content_pull(self):
        data = SIOData()
        now = datetime.now()

        data.update_last_content_pull("music", now)
        assert data.get_last_content_pull("music") == now

    def test_last_content_pull_default_tag(self):
        data = SIOData()
        now = datetime.now()

        data.update_last_content_pull(None, now)
        assert data.get_last_content_pull(None) == now
        assert data.get_last_content_pull("all") == now

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def test_reset_data(self):
        data = SIOData()
        data.add_or_update_user("alice", 2)
        data.channel_permissions = {"delete_video": 2}

        data.reset_data()

        assert data.users == {}
        assert data.channel_permissions == {}
