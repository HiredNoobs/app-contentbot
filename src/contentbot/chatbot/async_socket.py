import logging
import os
from textwrap import wrap

import socketio

from contentbot.chatbot.sio_data import SIOData
from contentbot.utils.api_query import query_endpoint

MSG_LIMIT = int(os.environ.get("CYTUBE_MSG_LIMIT", "80"))
logger: logging.Logger = logging.getLogger("contentbot")


class AsyncSocket:
    def __init__(self, url: str, channel_name: str, username: str, password: str):
        self._url = url
        self._channel_name = channel_name
        self._username = username
        self._password = password
        self.client = socketio.AsyncClient()
        self.data = SIOData()

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
        await self.client.connect(socket_url)

    async def login(self) -> None:
        self.client.emit("login", {"name": self._username, "pw": self._password})

    async def send_chat_msg(self, message: str) -> None:
        msgs = wrap(message, MSG_LIMIT)
        for msg in msgs:
            await self.client.emit("chatMsg", {"msg": msg})

    async def add_video_to_queue(self, id: str) -> None:
        await self.client.emit(
            "queue",
            {"id": id, "type": "yt", "pos": "end", "temp": True},
        )
