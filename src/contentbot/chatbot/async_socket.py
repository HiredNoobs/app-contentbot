import logging
import os
from textwrap import wrap
from typing import Dict, Optional

import socketio

from contentbot.chatbot.sio_data import SIOData
from contentbot.common.utils.api_query import query_endpoint

logger: logging.Logger = logging.getLogger("contentbot")


class AsyncSocket:
    """
    Asynchronous wrapper around the Cytube Socket.IO client.

    Handles connection, authentication, chat messaging, queueing videos,
    and leader controls. This class provides the low-level communication
    layer used by all processors.
    """

    def __init__(self, url: str, channel_name: str, username: str, password: str, siodata: SIOData):
        """
        Initialise the socket wrapper.

        Args:
            url (str): Base Cytube instance URL.
            channel_name (str): Channel to join.
            username (str): Bot username.
            password (str): Bot password.
            siodata (SIOData): Shared state container.
        """
        self._url = url
        self._channel_name = channel_name
        self._username = username
        self._password = password

        self._client = socketio.AsyncClient(engineio_logger=logger)
        self.data = siodata

        self._message_limit = int(os.getenv("CYTUBE_MSG_LIMIT", "80"))

    async def _get_socket_url(self) -> str:
        """
        Retrieve the secure WebSocket URL for the configured channel.

        Returns:
            str: The secure socket URL.

        Raises:
            ConnectionError: If no secure server entry is found.
        """
        socket_conf = f"{self._url}/socketconfig/{self._channel_name}.json"
        resp = query_endpoint(socket_conf)
        servers = resp.json()

        for server in servers["servers"]:
            if server["secure"]:
                return server["url"]

        raise ConnectionError("Unable to find a secure socket to connect to")

    async def connect(self) -> None:
        """Connect to the Cytube socket using the resolved secure URL."""
        socket_url = await self._get_socket_url()
        await self._client.connect(socket_url, retry=True)

    async def join_channel(self) -> None:
        """Join the configured Cytube channel."""
        await self._client.emit("joinChannel", {"name": self._channel_name})

    async def login(self) -> None:
        """Log in to the Cytube channel if not already authenticated."""
        if not self.data.logged_in:
            await self._client.emit("login", {"name": self._username, "pw": self._password})

    async def emit(self, event: str, data: Optional[Dict] = None) -> None:
        """
        Emit a generic event to the Cytube server.

        Args:
            event (str): Event name.
            data (Optional[Dict]): Optional payload to send.
        """
        if data:
            await self._client.emit(event, data)
        else:
            await self._client.emit(event)

    async def send_chat_msg(self, message: str) -> None:
        """
        Send a chat message to the Cytube channel, automatically wrapping
        long messages to comply with server message length limits.

        Args:
            message (str): Message text to send.
        """
        msgs = wrap(message, self._message_limit)
        for msg in msgs:
            await self._client.emit("chatMsg", {"msg": msg})

    async def add_video_to_queue(self, id: str) -> None:
        """
        Queue a YouTube video at the end of the playlist as a temporary item.

        Args:
            id (str): YouTube video ID.
        """
        await self._client.emit(
            "queue",
            {"id": id, "type": "yt", "pos": "end", "temp": True},
        )

    async def become_leader(self) -> None:
        """
        Attempt to become the channel leader and pause the current media.

        This is only possible if the bot has `leaderctl` permissions.
        """
        logger.debug("Bot (%s) is attempting to become leader.", self._username)

        if not self.data.has_permission(self._username, "leaderctl"):
            logger.debug("%s does not have leaderctl permissions.", self._username)
            return

        await self._client.emit("assignLeader", {"name": self._username})

        current = self.data.current_media
        if not current:
            logger.debug("No current media set. Skipping pause.")
            return

        current_id = current["id"]
        current_time = current.get("currentTime", 0)
        current_type = current["type"]

        logger.debug(
            "Pushing mediaUpdate: %s",
            {"id": current_id, "currentTime": current_time, "type": current_type, "paused": True},
        )

        await self._client.emit(
            "mediaUpdate",
            {"id": current_id, "currentTime": current_time, "type": current_type, "paused": True},
        )
