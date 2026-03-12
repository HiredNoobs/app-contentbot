import logging
import os
from textwrap import wrap
from typing import Dict, Optional

import socketio

from contentbot.chatbot.sio_data import SIOData
from contentbot.utils.api_query import query_endpoint

logger: logging.Logger = logging.getLogger("contentbot")


class AsyncSocket:
    def __init__(self, url: str, channel_name: str, username: str, password: str, siodata: SIOData):
        self._url = url
        self._channel_name = channel_name
        self._username = username
        self._password = password

        self._client = socketio.AsyncClient(engineio_logger=logger)
        self.data = siodata

        self._message_limit = int(os.getenv("CYTUBE_MSG_LIMIT", "80"))

    async def _init_socket(self) -> str:
        socket_conf = f"{self._url}/socketconfig/{self._channel_name}.json"
        resp = query_endpoint(socket_conf)
        servers = resp.json()

        for server in servers["servers"]:
            if server["secure"]:
                return server["url"]

        raise ConnectionError("Unable to find a secure socket to connect to")

    async def connect(self) -> None:
        socket_url = await self._init_socket()
        await self._client.connect(socket_url, retry=True)

    async def join_channel(self) -> None:
        await self._client.emit("joinChannel", {"name": self._channel_name})

    async def login(self) -> None:
        await self._client.emit("login", {"name": self._username, "pw": self._password})

    async def emit(self, event: str, data: Optional[Dict] = None) -> None:
        """
        Generic emit wrapper method.

        This should be used for one off emits, and ideally those
        events don't take any data (e.g. playerReader). Anything else
        should get it's own method to keep all the logic together.
        """
        if data:
            await self._client.emit(event, data)
        else:
            await self._client.emit(event)

    async def send_chat_msg(self, message: str) -> None:
        msgs = wrap(message, self._message_limit)
        for msg in msgs:
            await self._client.emit("chatMsg", {"msg": msg})

    async def add_video_to_queue(self, id: str) -> None:
        await self._client.emit(
            "queue",
            {"id": id, "type": "yt", "pos": "end", "temp": True},
        )

    async def become_leader(self) -> None:
        """
        Become leader and pause the current media.
        """
        logger.debug("Bot (%s) is attempting to become leader.", self._username)

        # Obviously this can just be the user not having admin but it can
        # also be the bot responding to events before the login is complete
        # (this only seems to be an issue on socket reconnect.)
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
