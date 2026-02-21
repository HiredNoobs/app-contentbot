import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List

from aiokafka import ConsumerRecord

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.commands import Commands
from contentbot.chatbot.content.async_redis_db import AsyncRedisDB
from contentbot.common.kafka_consumer import AsyncKafkaConsumer
from contentbot.common.kafka_producer import AsyncKafkaProducer

logger: logging.Logger = logging.getLogger("contentbot")

REQUIRED_PERMISSION_LEVEL = 3
ACCEPTABLE_ERRORS = {
    "This item is already on the playlist",
    "Cannot add age restricted videos. See: https://github.com/calzoneman/sync/wiki/Frequently-Asked-Questions#why-dont-age-restricted-youtube-videos-work",  # noqa: E501
    "The uploader has made this video non-embeddable",
    "This video has not been processed yet.",
}


class AsyncChatProcessor:
    def __init__(
        self, sio: AsyncSocket, db: AsyncRedisDB, job_queue: AsyncKafkaProducer, content_queue: AsyncKafkaConsumer
    ):
        self._sio = sio
        self._db = db
        self._job_queue = job_queue
        self._content_queue = content_queue

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

    async def handle_connect(self):
        await self._sio.join_channel()

    async def handle_channel_opts(self):
        await self._sio.login()

    async def handle_chat_message(self, data: Dict):
        if not self._should_process_chat(data):
            return

        username = data.get("username")
        msg = data.get("msg", "")

        logger.debug("Chat message from %s: %s", username, msg)

        msg_parts = msg.split()
        command = msg_parts[0].casefold()
        args = msg_parts[1:] if len(msg_parts) > 1 else []

        if command.startswith(Commands.COMMAND_SYMBOL.value):
            command = command[1:]
            if command in Commands.STANDARD_COMMANDS.value.keys():
                await self._handle_command(username, command, args)
            elif command in Commands.BLACKJACK_COMMANDS.value.keys():
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

    async def handle_kafka_job(self, msg: ConsumerRecord) -> None:
        content = json.loads(msg.value)
        channel_id = content["channel_id"]
        video_id = content["video_id"]
        dt = content["datetime"]

        if await self._db.is_video_processed(channel_id, video_id):
            return

        if await self._db.is_video_pending(channel_id, video_id):
            return

        await self._db.map_video_to_kafka_offset(video_id, msg.topic, msg.partition, msg.offset)

        await self._db.mark_video_pending(channel_id, video_id)
        await self._sio.add_video_to_queue(video_id)
        await self._db.update_datetime(channel_id, dt)

    async def handle_successful_queue(self, data: Dict) -> None:
        video_id = self._extract_id(data)
        channel_id = await self._db.get_channel_for_video(video_id)
        kafka_meta = await self._db.get_kafka_offset_for_video(video_id)

        if not channel_id:
            return

        await self._content_queue.commit(kafka_meta["topic"], kafka_meta["partition"], kafka_meta["offset"])

        await self._db.mark_video_processed(channel_id, video_id)
        await self._db.clear_video_pending(channel_id, video_id)
        await self._db.clear_video_channel_map(video_id)
        await self._db.clear_kafka_offset_map(video_id)

    async def handle_failed_queue(self, data: Dict) -> None:
        video_id = self._extract_id(data)
        channel_id = await self._db.get_channel_for_video(video_id)
        kafka_meta = await self._db.get_kafka_offset_for_video(video_id)

        if not channel_id:
            return

        if data["msg"] in ACCEPTABLE_ERRORS:
            await self._content_queue.commit(kafka_meta["topic"], kafka_meta["partition"], kafka_meta["offset"])

            await self._db.mark_video_processed(channel_id, video_id)
            await self._db.clear_video_pending(channel_id, video_id)
            await self._db.clear_video_channel_map(video_id)
            await self._db.clear_kafka_offset_map(video_id)
        else:
            await self._db.clear_video_pending(channel_id, video_id)

    # -----------------------------------------------------
    # Command handlers
    # -----------------------------------------------------

    async def _cmd_add_channel(self, channel_name: str) -> None:
        pass

    async def _cmd_add_tags(self, channel_name: str, tags: str) -> None:
        pass

    async def _cmd_content_search(self, tags: List) -> None:
        if not tags:
            tags = [None]

        for tag in tags:
            channels = await self._db.get_channels(tag)
            for channel in channels:
                await self._job_queue.send(channel)

    async def _cmd_current(self) -> None:
        pass

    async def _cmd_random(self) -> None:
        pass
