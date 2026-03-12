from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.sio_data import SIOData


class TestAsyncSocket:

    @pytest.fixture
    def sio_data(self):
        return SIOData()

    @pytest.fixture
    def socket(self, sio_data):
        return AsyncSocket(
            url="https://example.com",
            channel_name="testchan",
            username="bot",
            password="pw",
            siodata=sio_data,
        )

    # ------------------------------------------------------------------
    # _init_socket
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_init_socket_returns_secure_url(self, socket):
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "servers": [
                {"secure": False, "url": "ws://insecure"},
                {"secure": True, "url": "wss://secure.example"},
            ]
        }

        with patch("contentbot.chatbot.async_socket.query_endpoint", return_value=fake_response):
            url = await socket._init_socket()
            assert url == "wss://secure.example"

    @pytest.mark.asyncio
    async def test_init_socket_raises_if_no_secure(self, socket):
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "servers": [
                {"secure": False, "url": "ws://insecure1"},
                {"secure": False, "url": "ws://insecure2"},
            ]
        }

        with patch("contentbot.chatbot.async_socket.query_endpoint", return_value=fake_response):
            with pytest.raises(ConnectionError):
                await socket._init_socket()

    # ------------------------------------------------------------------
    # connect
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_calls_socketio_connect(self, socket):
        socket._client.connect = AsyncMock()

        fake_response = MagicMock()
        fake_response.json.return_value = {"servers": [{"secure": True, "url": "wss://secure.example"}]}

        with patch("contentbot.chatbot.async_socket.query_endpoint", return_value=fake_response):
            await socket.connect()

        socket._client.connect.assert_called_once_with("wss://secure.example", retry=True)

    # ------------------------------------------------------------------
    # join_channel
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_join_channel_emits_joinChannel(self, socket):
        socket._client.emit = AsyncMock()

        await socket.join_channel()

        socket._client.emit.assert_called_once_with("joinChannel", {"name": "testchan"})

    # ------------------------------------------------------------------
    # login
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_login_emits_login(self, socket):
        socket._client.emit = AsyncMock()

        await socket.login()

        socket._client.emit.assert_called_once_with("login", {"name": "bot", "pw": "pw"})

    # ------------------------------------------------------------------
    # emit wrapper
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_emit_with_data(self, socket):
        socket._client.emit = AsyncMock()

        await socket.emit("customEvent", {"x": 1})

        socket._client.emit.assert_called_once_with("customEvent", {"x": 1})

    @pytest.mark.asyncio
    async def test_emit_without_data(self, socket):
        socket._client.emit = AsyncMock()

        await socket.emit("ping")

        socket._client.emit.assert_called_once_with("ping")

    # ------------------------------------------------------------------
    # send_chat_msg
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_send_chat_msg_wraps(self, monkeypatch):
        monkeypatch.setenv("CYTUBE_MSG_LIMIT", "10")

        data = SIOData()
        socket = AsyncSocket(
            url="https://example.com",
            channel_name="testchan",
            username="bot",
            password="pw",
            siodata=data,
        )

        socket._client.emit = AsyncMock()

        await socket.send_chat_msg("This is a long message")

        actual_calls = socket._client.emit.call_args_list

        expected = ["This is a", "long", "message"]

        assert len(actual_calls) == len(expected)

        for call, chunk in zip(actual_calls, expected):
            assert call.args == ("chatMsg", {"msg": chunk})

    # ------------------------------------------------------------------
    # add_video_to_queue
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_add_video_to_queue(self, socket):
        socket._client.emit = AsyncMock()

        await socket.add_video_to_queue("abc123")

        socket._client.emit.assert_called_once_with(
            "queue",
            {"id": "abc123", "type": "yt", "pos": "end", "temp": True},
        )

    # ------------------------------------------------------------------
    # become_leader
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_become_leader_no_permission(self, socket):
        socket._client.emit = AsyncMock()

        # No permissions set → should return early
        socket.data.add_or_update_user("bot", 0)
        socket.data.channel_permissions = {"leaderctl": 2}

        await socket.become_leader()

        # Should NOT emit anything
        socket._client.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_become_leader_with_permission_no_media(self, socket):
        socket._client.emit = AsyncMock()

        socket.data.add_or_update_user("bot", 3)
        socket.data.channel_permissions = {"leaderctl": 2}

        await socket.become_leader()

        socket._client.emit.assert_called_once_with("assignLeader", {"name": "bot"})

    @pytest.mark.asyncio
    async def test_become_leader_with_media(self, socket):
        socket._client.emit = AsyncMock()

        socket.data.add_or_update_user("bot", 3)
        socket.data.channel_permissions = {"leaderctl": 2}

        socket.data.current_media = {
            "id": "xyz",
            "currentTime": 12.5,
            "type": "yt",
        }

        await socket.become_leader()

        # First emit: assignLeader
        # Second emit: mediaUpdate
        assert socket._client.emit.call_count == 2

        socket._client.emit.assert_any_call("assignLeader", {"name": "bot"})

        socket._client.emit.assert_any_call(
            "mediaUpdate",
            {"id": "xyz", "currentTime": 12.5, "type": "yt", "paused": True},
        )
