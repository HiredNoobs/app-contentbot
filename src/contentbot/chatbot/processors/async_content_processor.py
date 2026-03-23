import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aio_pika import IncomingMessage

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.db.async_redis_db import AsyncRedisDB
from contentbot.chatbot.processors.base_processor import BaseProcessor
from contentbot.chatbot.utils.yt import get_channel_id_from_name, get_data_from_pattern
from contentbot.common.queue.rabbitmq_producer import AsyncRabbitMQProducer
from contentbot.exceptions import QueueError

logger: logging.Logger = logging.getLogger("contentbot")

ACCEPTABLE_ERRORS = {
    "This item is already on the playlist",
    "Cannot add age restricted videos. See: https://github.com/calzoneman/sync/wiki/Frequently-Asked-Questions#why-dont-age-restricted-youtube-videos-work",  # noqa: E501
    "The uploader has made this video non-embeddable",
    "This video has not been processed yet.",
}

# This should match both channel names and channel IDs
CHANNEL_PATTERN = re.compile(r"^(?=.{3,30}$)[A-Za-z0-9](?:[A-Za-z0-9_.\-·]*[A-Za-z0-9])$")


class AsyncContentProcessor(BaseProcessor):
    """Processor for content related events."""

    def __init__(self, sio: AsyncSocket, db: AsyncRedisDB, job_queue: AsyncRabbitMQProducer):
        """
        Initialise the content processor.

        Args:
            sio (AsyncSocket): Socket interface for sending chat messages.
            db (AsyncRedisDB): Redis database interface for channel metadata.
            job_queue (AsyncRabbitMQProducer): Queue for submitting content jobs.
        """
        super().__init__(sio)
        self._db = db
        self._job_queue = job_queue

    # -----------------------------------------------------
    # Helper methods
    # -----------------------------------------------------

    @staticmethod
    def _extract_id(data: Dict) -> str:
        """
        Extract a video ID from a event payload.

        Args:
            data (Dict): Response dictionary containing an ID or link.

        Returns:
            str: Extracted ID.

        Raises:
            KeyError: If no valid ID can be found.
        """
        if "id" in data and data["id"]:
            return data["id"]

        link = data.get("link")
        if isinstance(link, str) and link.strip():
            return link.rstrip("/").split("/")[-1]

        try:
            return data["item"]["media"]["id"]
        except Exception:
            raise KeyError(f"No valid ID found in response: {data}")

    @staticmethod
    def _check_valid_channel_name(channel_name: str) -> bool:
        """
        Validate a channel name or ID using a regex pattern that should allow
        both channel names and channel IDs.

        Args:
            channel_name (str): Channel name or ID to validate.

        Returns:
            bool: True if valid, otherwise False.
        """
        if CHANNEL_PATTERN.match(channel_name):
            return True
        return False

    # -----------------------------------------------------
    # Event handlers
    # -----------------------------------------------------

    async def handle_chat_message(self, data: Dict):
        """
        Handle an incoming chat message.

        Args:
            data (Dict): Raw chat event payload.
        """
        username, command, args = self._parse_chat_event(data)
        await self._handle_command(username, command, args)

    async def handle_change_media(self, data: Dict) -> None:
        """
        Set state in SIOData object based on the current media event.

        Args:
            data (Dict): Media metadata payload.
        """
        self._sio.data.current_media = data

    async def handle_media_update(self, data: Dict) -> None:
        """
        Handle updates to the current media playback time.

        Args:
            data (Dict): Contains the updated playback timestamp.
        """
        self._sio.data.update_current_time(data["currentTime"])

    async def handle_new_content(self, msg: IncomingMessage) -> None:
        """
        Handle new content arriving from RabbitMQ.

        This includes:
            - Extracting video metadata
            - Adding the video to the Cytube queue
            - Updating Redis timestamps
            - Managing pending message acknowledgements

        Args:
            msg (IncomingMessage): RabbitMQ message containing content data.
        """
        content = json.loads(msg.body)
        video_id = content["video_id"]

        channel_id = content.get("channel_id")
        dt = content.get("datetime")

        try:
            self._sio.data.add_pending(video_id, msg)
        except QueueError:
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
        """
        Handle a successful Cytube queue event by acknowledging the RabbitMQ message.

        Args:
            data (Dict): Payload containing the video ID.
        """
        video_id = self._extract_id(data)

        msg = self._sio.data.get_pending(video_id)
        if not msg:
            return

        try:
            await msg.ack()
            logger.debug("Acked RabbitMQ message for video %s", video_id)

            self._sio.data.decrease_backoff()
        except Exception:
            logger.exception("Failed to ack RabbitMQ message for %s", video_id)
        finally:
            self._sio.data.remove_pending(video_id)

    async def handle_failed_queue(self, data: Dict) -> None:
        """
        Handle a failed Cytube queue event by nacking the RabbitMQ message.

        Args:
            data (Dict): Payload containing the video ID.
        """
        video_id = self._extract_id(data)

        msg = self._sio.data.get_pending(video_id)
        if not msg:
            return

        try:
            logger.debug("Nacking RabbitMQ message for failed video %s", video_id)
            if data["msg"] in ACCEPTABLE_ERRORS:
                await msg.nack(requeue=False)
            elif data["msg"] == "You are adding videos too quickly":
                self._sio.data.increase_backoff()
                await msg.nack(requeue=True)
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
        """
        Route a parsed chat command to the appropriate handler.

        Args:
            username (str): User issuing the command.
            command (str): Command keyword.
            args (List[str]): Command arguments.
        """
        match command:
            case "add_channel":
                if not self._sio.data.is_user_admin(username):
                    await self._sio.send_chat_msg("You don't have permission to do that.")

                if not args:
                    await self._sio.send_chat_msg("No channel provided.")
                    return

                await self._cmd_add_channel(args[0], tags=args[1:])
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

                word = command == "random_word"
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

    async def _cmd_add_channel(self, channel_name: str, tags: Optional[List[str]] = None) -> None:
        """
        Add a new channel to the database.

        Args:
            channel_name (str): Channel name or ID.
            tags (Optional[List[str]]): Optional list of tags.
        """
        if not self._check_valid_channel_name(channel_name):
            await self._sio.send_chat_msg(f"{channel_name} isn't a valid channel name or ID.")
            return

        if tags:
            tags = [tag for tag in tags if tag.isalpha()]

        channel_id = await get_channel_id_from_name(channel_name)

        if not channel_id:
            await self._sio.send_chat_msg(f"Couldn't find '{channel_name}'")
            return

        success = await self._db.add_channel(channel_id, channel_name, tags=tags)

        if success:
            await self._sio.send_chat_msg(f"Added '{channel_name}' to DB.")
        else:
            await self._sio.send_chat_msg(f"Failed to add '{channel_name}' to DB.")

    async def _cmd_add_tags(self, channel_name: str, tags: List[str]) -> None:
        """
        Add tags to an existing channel.

        Args:
            channel_name (str): Channel name.
            tags (List[str]): Tags to add.
        """
        tags = [tag for tag in tags if tag.isalpha()]
        if not tags:
            await self._sio.send_chat_msg("No valid tags provided.")
            return

        channel_id = await self._db.get_channel_id(channel_name)
        if not channel_id:
            await self._sio.send_chat_msg(f"{channel_name} not in DB.")
            return

        await self._db.add_tags(channel_id, tags)
        await self._sio.send_chat_msg(f"{tags} added to {channel_name}")

    async def _cmd_content_search(self, tags: List[str]) -> None:
        """
        Trigger content searches for channels matching the given tags.

        Args:
            tags (List[str]): Tags to filter channels by.
        """
        if tags:
            tags = [tag for tag in tags if tag.isalpha()]
        else:
            tags = [""]

        for tag in tags:
            now = datetime.now()
            last_pull = self._sio.data.get_last_content_pull(tag)
            if last_pull:
                if last_pull < now - timedelta(minutes=5):
                    continue

            channels = await self._db.get_channels(tag=tag)
            for channel in channels:
                await self._job_queue.send(channel)

            self._sio.data.update_last_content_pull(now, tag=tag)

    async def _cmd_current(self) -> None:
        """Display the description of the currently playing media item."""
        current = self._sio.data.current_media
        if not current:
            return None

        video_id = current["id"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        desc = await get_data_from_pattern(
            url, r'.*"description":{"simpleText":"(.*?)"', script_tag_name="ytInitialPlayerResponse"
        )
        if desc:
            desc = desc.replace("\\n", " ")
        else:
            desc = "Description not available."

        await self._sio.send_chat_msg(desc)

    async def _cmd_random(self, size: int, word: bool) -> None:
        """
        Request a random video or random word based content job.

        Args:
            size (int): Size of the random string to generate.
            word (bool): Whether to use a random word rather than
            a random string.
        """
        d = {"random_size": size, "random_word": word}
        await self._job_queue.send(d)
