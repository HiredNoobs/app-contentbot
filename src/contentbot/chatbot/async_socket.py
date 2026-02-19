import logging
import os
from textwrap import wrap

import socketio

from contentbot.chatbot.sio_data import SIOData
from contentbot.utils.api_query import query_endpoint

MSG_LIMIT = int(os.environ.get("CYTUBE_MSG_LIMIT", "80"))
logger: logging.Logger = logging.getLogger("contentbot")


class AsyncSocket:
    def __init__(self, url: str, channel_name: str):
        self._url = url
        self._channel_name = channel_name
        self._socketio = socketio.AsyncClient()
        self.data = SIOData()

    async def init_socket(self) -> str:
        socket_conf = f"{self._url}/socketconfig/{self._channel_name}.json"
        resp = query_endpoint(socket_conf)
        servers = resp.json()

        for server in servers["servers"]:
            if server["secure"]:
                return server["url"]

        raise ConnectionError("Unable to find a secure socket to connect to")

    async def send_chat_msg(self, message: str) -> None:
        msgs = wrap(message, MSG_LIMIT)
        for msg in msgs:
            await self._socketio.emit("chatMsg", {"msg": msg})

    async def add_video_to_queue(self, id: str) -> None:
        await self._socketio.emit(
            "queue",
            {"id": id, "type": "yt", "pos": "end", "temp": True},
        )
