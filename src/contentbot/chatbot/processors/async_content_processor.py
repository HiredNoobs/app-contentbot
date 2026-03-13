import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aio_pika import IncomingMessage

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.db.async_redis_db import AsyncRedisDB
from contentbot.common.rabbitmq_consumer import AsyncRabbitMQConsumer
from contentbot.common.rabbitmq_producer import AsyncRabbitMQProducer
from contentbot.exceptions import QueueError
from contentbot.utils.api_query import get_data_from_pattern
from contentbot.utils.yt import get_channel_id_from_name

logger: logging.Logger = logging.getLogger("contentbot")

ACCEPTABLE_ERRORS = {
    "This item is already on the playlist",
    "Cannot add age restricted videos. See: https://github.com/calzoneman/sync/wiki/Frequently-Asked-Questions#why-dont-age-restricted-youtube-videos-work",  # noqa: E501
    "The uploader has made this video non-embeddable",
    "This video has not been processed yet.",
}


class AsyncContentProcessor:
    """Processor for content related events (mainly chat commands.)"""

    def __init__(
        self,
        sio: AsyncSocket,
        db: AsyncRedisDB,
        job_queue: AsyncRabbitMQProducer,
        result_queue: AsyncRabbitMQConsumer,
    ):
        self._sio = sio
        self._db = db
        self._job_queue = job_queue
        self._result_queue = result_queue

    # -----------------------------------------------------
    # Helper methods
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Event handlers
    # -----------------------------------------------------

    async def handle_chat_message(self, data: Dict):
        username = data.get("username", "")
        msg = data.get("msg", "")

        msg_parts = msg.split()
        command = msg_parts[0].casefold()[1:]
        args = msg_parts[1:] if len(msg_parts) > 1 else []

        await self._handle_command(username, command, args)

    async def handle_change_media(self, data: Dict) -> None:
        self._sio.data.current_media = data

    async def handle_media_update(self, data: Dict) -> None:
        self._sio.data.update_current_time(data["currentTime"])

    async def handle_new_content(self, msg: IncomingMessage) -> None:
        content = json.loads(msg.body)
        video_id = content["video_id"]

        # Random videos don't include channel details or a dt to update
        channel_id = content.get("channel_id")
        dt = content.get("datetime")

        try:
            self._sio.data.add_pending(video_id, msg)
        except QueueError:
            # This error would mean the bot is re-processing content
            # that has already been emitted but before we hear back
            # from Cytube. Not sure if this is possible outside of
            # duplicate values ending up in the queue?
            await msg.nack(requeue=False)
            return

        try:
            await self._sio.add_video_to_queue(video_id)
            if channel_id and dt:
                await self._db.update_datetime(channel_id, dt)
        except Exception:
            logger.exception("Failed to add video to queue")
            await msg.nack(requeue=True)

    async def handle_successful_queue(self, data: Dict) -> None:
        video_id = self._extract_id(data)

        msg = self._sio.data.get_pending(video_id)
        if not msg:
            return

        try:
            await msg.ack()
            logger.debug("Acked RabbitMQ message for video %s", video_id)
        except Exception:
            logger.exception("Failed to ack RabbitMQ message for %s", video_id)
        finally:
            self._sio.data.remove_pending(video_id)

    async def handle_failed_queue(self, data: Dict) -> None:
        video_id = self._extract_id(data)

        msg = self._sio.data.get_pending(video_id)
        if not msg:
            return

        try:
            logger.debug("Nacking RabbitMQ message for failed video %s", video_id)
            if msg.body in ACCEPTABLE_ERRORS:
                await msg.nack(requeue=False)
            else:
                await msg.nack(requeue=True)
        except Exception:
            logger.exception("Failed to nack RabbitMQ message for %s", video_id)
        finally:
            self._sio.data.remove_pending(video_id)

    # -----------------------------------------------------
    # Command handlers
    # -----------------------------------------------------

    async def _handle_command(self, username: str, command: str, args: List[str]) -> None:
        match command:
            case "add_channel":
                if not self._sio.data.is_user_admin(username):
                    await self._sio.send_chat_msg("You don't have permission to do that.")

                if not args:
                    await self._sio.send_chat_msg("No channel provided.")
                    return

                await self._cmd_add_channel(args[0], args[1:])
            case "add_channels":
                if not self._sio.data.is_user_admin(username):
                    await self._sio.send_chat_msg("You don't have permission to do that.")

                if not args:
                    await self._sio.send_chat_msg("No channels provided.")
                    return

                for channel in args:
                    await self._cmd_add_channel(channel)
            case "add_tags":
                if not self._sio.data.is_user_admin(username):
                    await self._sio.send_chat_msg("You don't have permission to do that.")

                if len(args) < 2:
                    await self._sio.send_chat_msg("Missing args for add_tags.")
                    return

                await self._cmd_add_tags(args[0], args[1:])
            case "content":
                if not self._sio.data.is_user_moderator(username):
                    await self._sio.send_chat_msg("You don't have permission to do that.")

                await self._cmd_content_search(args)
            case "current":
                await self._cmd_current()
            case "random" | "random_word":
                try:
                    size = int(args[0]) if args else 3
                except ValueError:
                    size = 3

                if command == "random_word":
                    word = True
                else:
                    word = False

                await self._cmd_random(size, word)
            case "remove_channel" | "remove_channels":
                if not self._sio.data.is_user_admin(username):
                    await self._sio.send_chat_msg("You don't have permission to do that.")

                if not args:
                    await self._sio.send_chat_msg("No channels provided.")
                    return

                deleted = await self._db.remove_channels(args)
                await self._sio.send_chat_msg(f"Deleted {deleted} channels from the DB.")
            case "remove_tags":
                if not self._sio.data.is_user_admin(username):
                    await self._sio.send_chat_msg("You don't have permission to do that.")

                if len(args) < 2:
                    await self._sio.send_chat_msg("Missing args for remove_tags.")
                    return

                channel = args[0]
                tags = args[1:]
                await self._db.remove_tags(channel, tags)

    async def _cmd_add_channel(self, channel_name: str, tags: Optional[List] = None) -> None:
        channel_id = get_channel_id_from_name(channel_name)

        if not channel_id:
            await self._sio.send_chat_msg(f"Couldn't find '{channel_name}'")
            return

        success = await self._db.add_channel(channel_id, channel_name, tags=tags)

        if success:
            await self._sio.send_chat_msg(f"Added '{channel_name}' to DB.")
        else:
            await self._sio.send_chat_msg(f"Failed to add '{channel_name}' to DB.")

    async def _cmd_add_tags(self, channel_name: str, tags: List[str]) -> None:
        channel_id = await self._db.get_channel_id(channel_name)
        if not channel_id:
            await self._sio.send_chat_msg(f"{channel_name} not in DB.")
            return
        await self._db.add_tags(channel_id, tags)
        await self._sio.send_chat_msg(f"{tags} added to {channel_name}")

    async def _cmd_content_search(self, tags: List) -> None:
        if not tags:
            tags = [None]

        for tag in tags:
            # Stops content jobs being added over and over again
            last_pull = self._sio.data.get_last_content_pull(tag)
            if last_pull:
                if last_pull < datetime.now() - timedelta(minutes=5):
                    continue

            channels = await self._db.get_channels(tag=tag)
            for channel in channels:
                await self._job_queue.send(channel)

    async def _cmd_current(self) -> None:
        current = self._sio.data.current_media
        if not current:
            return None

        video_id = current["id"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        desc = get_data_from_pattern(
            url, r'.*"description":{"simpleText":"(.*?)"', script_tag_name="ytInitialPlayerResponse"
        )
        if desc:
            desc = desc.replace("\\n", " ")
        else:
            desc = "Description not available."

        await self._sio.send_chat_msg(desc)

    async def _cmd_random(self, size: int, word: bool) -> None:
        d = {"random_size": size, "random_word": word}
        await self._job_queue.send(d)
