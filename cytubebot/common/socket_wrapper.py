import datetime
import logging
import os
import threading
from textwrap import wrap

import socketio  # type: ignore

from cytubebot.chatbot.sio_data import SIOData
from cytubebot.utils import query_endpoint

MSG_LIMIT = int(os.environ.get("CYTUBE_MSG_LIMIT", "80"))
logger = logging.getLogger(__name__)


class SocketWrapper:
    _instance = None
    _lock = threading.Lock()

    # Instance variable annotations for Mypy
    _url: str
    _channel_name: str
    _logger: logging.Logger
    _socketio: socketio.Client
    data: SIOData

    def __new__(cls, url: str, channel_name: str):
        if cls._instance is None:
            with cls._lock:
                instance = super().__new__(cls)
                instance._url = url
                instance._channel_name = channel_name

                # For debugging: engineio_logger=True
                instance._socketio = socketio.Client()
                instance.data = SIOData()
                cls._instance = instance
        return cls._instance

    def init_socket(self) -> str:
        """
        Returns:
            A str containing the URL of the socket server.
        """
        socket_conf = f"{self._url}/socketconfig/{self._channel_name}.json"
        resp = query_endpoint(socket_conf)
        logger.info(f"resp: {resp.status_code} - {resp.reason}")
        servers = resp.json()
        socket_url = ""

        for server in servers["servers"]:
            if server["secure"]:
                socket_url = server["url"]
                break

        if not socket_url:
            raise socketio.exceptions.ConnectionError(
                "Unable to find a secure socket to connect to"
            )

        return socket_url

    def send_chat_msg(self, message: str) -> None:
        """
        Sends a chat message through the socket.
        The message is split into chunks of size MSG_LIMIT using textwrap.wrap,
        and each chunk is emitted as a "chatMsg" event.
        """
        msgs = wrap(message, MSG_LIMIT)
        for msg in msgs:
            self._socketio.emit("chatMsg", {"msg": msg})

    def add_video_to_queue(self, id: str, wait: bool = True) -> None:
        """
        Add YouTube video to queue by video ID and wait until
        it's successfully added.
        """
        logger.debug(f"Adding {id} to queue, and {wait=}.")
        self._socketio.emit(
            "queue",
            {"id": id, "type": "yt", "pos": "end", "temp": True},
        )

        if not wait:
            return

        logger.debug(
            f"Starting to wait for content be successfully added. Starting values: {self.data.queue_resp=} and {self.data.queue_err=}."
            f"Starting time: {datetime.datetime.now()}"
        )

        while self.data.queue_resp is None or self.data.queue_err:
            self._socketio.sleep(0.3)

        logger.debug(
            f"Finished waiting for content to be added. Final values: {self.data.queue_resp=} and {self.data.queue_err=}."
            f"Finish time: {datetime.datetime.now()}"
        )

        self.data.queue_resp = None

    def __getattr__(self, name):
        """
        Forward attribute access to the underlying SocketIO instance.
        """
        try:
            return object.__getattribute__(self, name)
        except AttributeError:
            return getattr(self._socketio, name)
