import logging
import os
from datetime import datetime, timedelta
from typing import Dict

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.commands import Commands
from contentbot.chatbot.content.async_redis_db import AsyncRedisDB
from contentbot.common.kafka_producer import AsyncKafkaProducer

logger: logging.Logger = logging.getLogger("contentbot")

REQUIRED_PERMISSION_LEVEL = 3
ACCEPTABLE_ERRORS = {
    "This item is already on the playlist",
    "Cannot add age restricted videos. See: https://github.com/calzoneman/sync/wiki/Frequently-Asked-Questions#why-dont-age-restricted-youtube-videos-work",
    "The uploader has made this video non-embeddable",
    "This video has not been processed yet.",
}


class AsyncChatProcessor:
    def __init__(self, sio: AsyncSocket, db: AsyncRedisDB, queue: AsyncKafkaProducer):
        self._sio = sio
        self._db = db
        self._queue = queue

    # -----------------------------------------------------
    # Static methods
    # -----------------------------------------------------

    def _has_permission(self, username: str) -> bool:
        return self._sio.data.users.get(username, 0) >= REQUIRED_PERMISSION_LEVEL

    @staticmethod
    def _extract_id(resp: Dict) -> str:
        if "id" in resp and resp["id"]:
            return resp["id"]

        link = resp.get("link")
        if isinstance(link, str) and link.strip():
            return link.rstrip("/").split("/")[-1]

        try:
            return resp["item"]["media"]["id"]
        except Exception:
            raise KeyError(f"No valid ID found in response: {resp}")

    @staticmethod
    def _should_process_chat(resp: Dict) -> bool:
        username = resp.get("username")
        msg = resp.get("msg", None)
        chat_ts = datetime.fromtimestamp(resp["time"] / 1000)

        if not username or not msg or not chat_ts:
            return False

        if chat_ts < datetime.now() - timedelta(seconds=10):
            return False

        if username == os.getenv("CYTUBE_USERNAME"):
            return False

        return True

    # -----------------------------------------------------
    # Event handlers
    # -----------------------------------------------------

    async def handle_channel_opts(self):
        self._sio.login()

    async def handle_chat_message(self, data: Dict):
        if not self._should_process_chat(data):
            return

        username = data.get("username")
        msg = data.get("msg", "")

        logger.debug("Chat message from %s: %s", username, msg)

        msg_parts = msg.split()
        command = msg_parts[0].casefold()
        args = msg_parts[1:] if len(msg_parts) > 1 else []

        if command.startswith(Commands.COMMAND_SYMBOL):
            command = command[1:]
            if command in Commands.STANDARD_COMMANDS.value:
                await self._handle_command(username, command, args)
            elif command in Commands.BLACKJACK_COMMANDS.value:
                pass
            else:
                pass

    async def _handle_command(self, username, command, args):
        match command:
            case "add":
                if self._has_permission(username):
                    await self._cmd_add_channel(args)
            case "add_tags":
                if self._has_permission(username):
                    await self._cmd_add_tags(args)
            case "content":
                await self._cmd_content_search(args)
            case "current":
                await self._cmd_current()
            case "random":
                await self._cmd_random()
            case "remove_tags":
                if self._has_permission(username):
                    await self._cmd_remove_tags(args)

    async def handle_user_join(self, username: str) -> None:
        pass

    async def handle_user_leave(self, username: str) -> None:
        pass

    async def handle_set_current(self, _) -> None:
        pass

    async def handle_kafka_job(self, id: str) -> None:
        await self._sio.add_video_to_queue(id)

    # -----------------------------------------------------
    # Command handlers
    # -----------------------------------------------------

    async def _cmd_add_channel(self, channel_name: str) -> None:
        pass

    async def _cmd_add_tags(self, channel_name: str, tags: str) -> None:
        pass

    # Add all channels to job queue topic
    # worker(s) consume and add content to
    # content queue
    async def _cmd_content_search(self) -> None:
        channels = await self._db.get_channels()
        for channel in channels:
            await self._queue.send(channel)

    async def _cmd_current(self) -> None:
        pass

    async def _cmd_random(self) -> None:
        pass
