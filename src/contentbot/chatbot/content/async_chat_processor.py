import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from aio_pika import IncomingMessage

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.content.async_redis_db import AsyncRedisDB
from contentbot.chatbot.sio_data import SIOData
from contentbot.common.rabbitmq_consumer import AsyncRabbitMQConsumer
from contentbot.common.rabbitmq_producer import AsyncRabbitMQProducer
from contentbot.utils.api_query import get_data_from_pattern
from contentbot.utils.yt import clean_yt_string

logger: logging.Logger = logging.getLogger("contentbot")

ACCEPTABLE_ERRORS = {
    "This item is already on the playlist",
    "Cannot add age restricted videos. See: https://github.com/calzoneman/sync/wiki/Frequently-Asked-Questions#why-dont-age-restricted-youtube-videos-work",  # noqa: E501
    "The uploader has made this video non-embeddable",
    "This video has not been processed yet.",
}


# TODO: Split all of the non-chat handling into a generic AsyncBotProcessor class
# this class should focus on the chat commands.
class AsyncChatProcessor:
    def __init__(
        self,
        sio: AsyncSocket,
        siodata: SIOData,
        db: AsyncRedisDB,
        job_queue: AsyncRabbitMQProducer,
        result_queue: AsyncRabbitMQConsumer,
    ):
        self._sio = sio
        self._siodata = siodata
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

    async def handle_connect(self):
        await self._sio.join_channel()

    async def handle_channel_opts(self):
        await self._sio.login()

    def handle_disconnect(self):
        self._sio.data.reset_data()

    async def handle_chat_message(self, data: Dict):
        username = data.get("username", "")
        msg = data.get("msg", "")

        msg_parts = msg.split()
        command = msg_parts[0].casefold()[1:]
        args = msg_parts[1:] if len(msg_parts) > 1 else []

        await self._handle_command(username, command, args)

    async def handle_user_join(self, data: Dict) -> None:
        user = data["name"]
        rank = data["rank"]
        self._siodata.add_or_update_user(user, rank)

    async def handle_user_leave(self, data: Dict) -> None:
        user = data["name"]
        self._siodata.remove_user(user)
        if self._siodata.only_remaining_user():
            await self._sio.become_leader()

    async def handle_change_media(self, data: Dict) -> None:
        self._siodata.current_media = data

    async def handle_media_update(self, data: Dict) -> None:
        self._siodata.update_current_time(data["currentTime"])

    async def handle_new_content(self, msg: IncomingMessage) -> None:
        content = json.loads(msg.body)
        video_id = content["video_id"]

        # Random videos don't include channel details or a dt to update
        channel_id = content.get("channel_id")
        dt = content.get("datetime")

        self._siodata.add_pending(video_id, msg)

        try:
            await self._sio.add_video_to_queue(video_id)
            if channel_id and dt:
                await self._db.update_datetime(channel_id, dt)
        except Exception:
            logger.exception("Failed to add video to queue")
            await msg.nack(requeue=True)

    async def handle_successful_login(self, _: Dict) -> None:
        # playerReady tells the server to start sending changeMedia events.
        await self._sio.emit("playerReady")
        # This is sent by the client during the login, not sure what it does as it doesn't appear to be
        # handled on the server side. Mainly adding it to test if anything changes...
        # https://github.com/calzoneman/sync/blob/589f999a9c526bf773a8b21ecf29ba30faf14739/www/js/callbacks.js#L472
        await self._sio.emit("initUserPLCallbacks")

    def handle_set_permissions(self, data: Dict) -> None:
        self._sio.data.channel_permissions = data

    async def handle_successful_queue(self, data: Dict) -> None:
        video_id = self._extract_id(data)

        msg = self._siodata.get_pending(video_id)
        if not msg:
            return

        try:
            await msg.ack()
            logger.debug("Acked RabbitMQ message for video %s", video_id)
        except Exception:
            logger.exception("Failed to ack RabbitMQ message for %s", video_id)
        finally:
            self._siodata.remove_pending(video_id)

    async def handle_failed_queue(self, data: Dict) -> None:
        video_id = self._extract_id(data)

        msg = self._siodata.get_pending(video_id)
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
            self._siodata.remove_pending(video_id)

    async def handle_user_list(self, data: Dict) -> None:
        for userdata in data:
            user = userdata["name"]
            rank = userdata["rank"]
            self._siodata.add_or_update_user(user, rank)

        if self._siodata.only_remaining_user():
            await self._sio.become_leader()

    # -----------------------------------------------------
    # Command handlers
    # -----------------------------------------------------

    async def _handle_command(self, username: str, command: str, args: List[str]) -> None:
        match command:
            case "add":
                if self._sio.data.is_user_admin(username):
                    if not args:
                        await self._sio.send_chat_msg("No channels provided.")
                        return

                    for channel in args:
                        await self._cmd_add_channel(channel)
                else:
                    await self._sio.send_chat_msg("You don't have permission to do that.")
            case "add_tags":
                if self._sio.data.is_user_admin(username):
                    if len(args) < 2:
                        await self._sio.send_chat_msg("Missing args for add_tags.")
                        return

                    channel = args[0]
                    tags = args[1:]
                    await self._db.add_tags(channel, tags)
                else:
                    await self._sio.send_chat_msg("You don't have permission to do that.")
            case "content":
                if self._sio.data.is_user_moderator(username):
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
            case "remove_tags":
                if self._sio.data.is_user_admin(username):
                    if len(args) < 2:
                        await self._sio.send_chat_msg("Missing args for remove_tags.")
                        return

                    channel = args[0]
                    tags = args[1:]
                    await self._db.remove_tags(channel, tags)
                else:
                    await self._sio.send_chat_msg("You don't have permission to do that.")

    async def _cmd_add_channel(self, channel_name: str) -> None:
        channel_name = clean_yt_string(channel_name)

        cookies = {"CONSENT": "YES+1"}
        candidate_urls = {
            f"https://www.youtube.com/@{channel_name}": r'.*"browse_id","value":"(.*?)"',
            f"https://www.youtube.com/c/{channel_name}": r'.*"browse_id","value":"(.*?)"',
            f"https://www.youtube.com/channel/{channel_name}": r'.*"channelMetadataRenderer":{"title":"(.*?)"',
        }

        for url, pattern in candidate_urls.items():
            channel_id = get_data_from_pattern(url, pattern, cookies=cookies)
            if channel_id:
                break
        else:
            await self._sio.send_chat_msg(f"Couldn't find '{channel_name}'")
            return

        await self._sio.send_chat_msg(f"Adding '{channel_name}' to DB.")
        await self._db.add_channel(channel_id, channel_name)

    async def _cmd_content_search(self, tags: List) -> None:
        if not tags:
            tags = [None]

        for tag in tags:
            # Stops content jobs being added over and over again
            last_pull = self._siodata.get_last_content_pull(tag)
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
