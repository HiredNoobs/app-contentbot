import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aio_pika import IncomingMessage

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.db.async_redis_db import AsyncRedisDB
from contentbot.chatbot.processors.base_processor import BaseProcessor
from contentbot.chatbot.utils.yt import get_channel_id_from_name, get_video_publish_date
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
            if dt:
                self._sio.data.set_video_publish_time(video_id, datetime.fromisoformat(dt))
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
            case "sort_queue":
                if not self._sio.data.is_user_moderator(username):
                    await self._sio.send_chat_msg("You don't have permission to do that.")
                    return

                await self._cmd_sort_queue()

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
                if last_pull > now - timedelta(minutes=5):
                    if tag:
                        await self._sio.send_chat_msg(
                            f"'{tag}' content was pulled recently. Please wait before pulling again."
                        )
                    else:
                        await self._sio.send_chat_msg("Content was pulled recently. Please wait before pulling again.")
                    continue

            if tag:
                await self._sio.send_chat_msg(f"Pulling content for '{tag}'...")
            else:
                await self._sio.send_chat_msg("Pulling content...")

            channels = await self._db.get_channels(tag=tag)
            for channel in channels:
                await self._job_queue.send(channel)

            self._sio.data.update_last_content_pull(now, tag=tag)

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

    @staticmethod
    def _plan_queue_sort(
        current_order: List[Optional[int]],
        desired_order: List[Optional[int]],
        anchor: str | int,
    ) -> List[Dict[str, str | int]]:
        """
        Build the minimum set of move operations required to reach the desired temp order.

        Items already in the correct relative position are left alone, which avoids
        reordering the entire temp block when only a few entries are misplaced.

        Args:
            current_order (List[Optional[int]]): Current temp-item UIDs in queue order.
            desired_order (List[Optional[int]]): Desired temp-item UIDs in sorted order.
            anchor (str | int): Queue anchor to place the temp block after; "prepend"
                means it should be inserted before the permanent queue.

        Returns:
            List[Dict[str, str | int]]: Move operations containing the source UID and
            insertion anchor.
        """
        if current_order == desired_order:
            return []

        current: List[int] = [uid for uid in current_order if uid is not None]
        desired_ids: List[int] = [uid for uid in desired_order if uid is not None]
        if current == desired_ids:
            return []

        moves: List[Dict[str, str | int]] = []
        active_anchor: str | int = anchor

        for desired_uid in desired_ids:
            if desired_uid not in current:
                continue

            if active_anchor == "prepend":
                if current and current[0] == desired_uid:
                    active_anchor = desired_uid
                    continue
            elif isinstance(active_anchor, int) and active_anchor in current:
                anchor_index = current.index(active_anchor)
                if anchor_index + 1 < len(current) and current[anchor_index + 1] == desired_uid:
                    active_anchor = desired_uid
                    continue

            moves.append({"from": desired_uid, "after": active_anchor})
            current.remove(desired_uid)
            if active_anchor == "prepend":
                current.insert(0, desired_uid)
            elif isinstance(active_anchor, int) and active_anchor in current:
                anchor_index = current.index(active_anchor)
                current.insert(anchor_index + 1, desired_uid)
            elif isinstance(active_anchor, int):
                current.append(desired_uid)
            else:
                raise TypeError(f"Unsupported queue anchor type: {type(active_anchor)!r}")
            active_anchor = desired_uid

        return moves

    async def _cmd_sort_queue(self) -> None:
        """
        Reorder temporary queue items behind the permanent queue by upload time.
        """
        playlist = await self._sio.request_playlist()
        if playlist is None:
            await self._sio.send_chat_msg("Queue is empty or could not be retrieved.")
            return

        temp_items = [item for item in playlist if item.get("temp")]
        if not temp_items:
            await self._sio.send_chat_msg("No temporary videos found.")
            return

        async def publish_time_for(item: Dict) -> datetime:
            media = item.get("media") or {}
            video_id = media.get("id")
            if video_id is None:
                return datetime.min

            known_dt = self._sio.data.get_video_publish_time(video_id)
            if known_dt is not None:
                return known_dt

            fetched_dt = await get_video_publish_date(video_id)
            if fetched_dt is not None:
                self._sio.data.set_video_publish_time(video_id, fetched_dt)
                return fetched_dt

            return datetime.min

        ordered_temp_items = []
        for item in temp_items:
            ordered_temp_items.append((await publish_time_for(item), item))

        ordered_temp_items.sort(key=lambda pair: (pair[0], pair[1].get("uid", 0)))
        ordered_temp_items = [item for _, item in ordered_temp_items]

        current_temp_order = [item.get("uid") for item in temp_items]
        desired_temp_order = [item.get("uid") for item in ordered_temp_items]
        if current_temp_order == desired_temp_order:
            await self._sio.send_chat_msg("Queue already sorted.")
            return

        anchor_uid = None
        for queue_item in reversed(playlist):
            if not queue_item.get("temp"):
                anchor_uid = queue_item.get("uid")
                break

        current_anchor = "prepend" if anchor_uid is None else anchor_uid
        move_plan = self._plan_queue_sort(current_temp_order, desired_temp_order, current_anchor)

        for move in move_plan:
            await self._sio.emit("moveMedia", {"from": move["from"], "after": move["after"]})
            await asyncio.sleep(0.25)

        await self._sio.send_chat_msg("Queue sorted.")
