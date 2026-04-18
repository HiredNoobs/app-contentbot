import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.commands import Commands
from contentbot.chatbot.db.async_redis_db import AsyncRedisDB
from contentbot.chatbot.processors.async_blackjack_processor import (
    AsyncBlackjackProcessor,
)
from contentbot.chatbot.processors.async_content_processor import AsyncContentProcessor
from contentbot.chatbot.processors.async_event_processor import AsyncEventProcessor
from contentbot.common.queue.rabbitmq_consumer import AsyncRabbitMQConsumer
from contentbot.exceptions import RemovedFromChannelError

logger: logging.Logger = logging.getLogger("contentbot")


class AsyncChatBot:
    """
    Main orchestrator for the chatbot.

    This class wires together the socket connection, event processors,
    Redis database, and RabbitMQ consumers. It registers all event handlers
    and delegates incoming events to the correct processor.
    """

    def __init__(
        self,
        sio: AsyncSocket,
        event_processor: AsyncEventProcessor,
        content_processor: AsyncContentProcessor,
        blackjack_processor: AsyncBlackjackProcessor,
        db: AsyncRedisDB,
        result_consumer: AsyncRabbitMQConsumer,
    ):
        """
        Initialise the chatbot and register all event handlers.

        Args:
            sio (AsyncSocket): Socket interface for Cytube communication.
            event_processor (AsyncEventProcessor): Handles general events.
            content_processor (AsyncContentProcessor): Handles content commands and media events.
            blackjack_processor (AsyncBlackjackProcessor): Handles blackjack commands.
            db (AsyncRedisDB): Redis database interface.
            result_consumer (AsyncRabbitMQConsumer): RabbitMQ consumer for worker results.
        """
        self._sio = sio
        self._event_processor = event_processor
        self._content_processor = content_processor
        self._blackjack_processor = blackjack_processor
        self._db = db
        self._result_consumer = result_consumer

        self._register_handlers()

    def _should_process_chat(self, data: Dict) -> bool:
        """
        Determine whether an incoming chat message should be processed.

        Conditions checked:
            - Message must contain a username, message text, and timestamp.
            - Message must be recent (within 10 seconds).
            - Message must not be from the bot itself.

        Args:
            data (Dict): Raw chat event payload.

        Returns:
            bool: True if the message should be processed, otherwise False.
        """
        username = data.get("username")
        msg = data.get("msg", None)
        chat_ts = datetime.fromtimestamp(data["time"] / 1000)

        if not username or not msg or not chat_ts:
            logger.debug("Chat message (%s) missing required fields.", msg)
            return False

        if chat_ts < datetime.now() - timedelta(seconds=10):
            logger.debug("Chat message (%s) is too old.", msg)
            return False

        if username == self._sio.data.user:
            logger.debug("Chat message (%s) is from the bot.", msg)
            return False

        return True

    def _register_handlers(self):
        """Register all Socket.IO event handlers."""

        @self._sio._client.event
        async def connect() -> None:
            logger.info("Socket connected.")
            await self._event_processor.handle_connect()

        @self._sio._client.event
        async def channelOpts(data: Dict) -> None:
            logger.debug("channelOpts event captured: %s", data)
            await self._event_processor.handle_channel_opts()

        @self._sio._client.event
        async def kick(data: Dict) -> None:
            logger.info("Bot was kicked due to %s", data["reason"])
            raise RemovedFromChannelError(f"Bot was kicked due to {data['reason']}")

        @self._sio._client.event
        async def disconnect() -> None:
            logger.info("Socket disconnected.")
            self._event_processor.handle_disconnect()

        @self._sio._client.event
        async def chatMsg(data: Dict) -> None:
            logger.debug("chatMsg event captured: %s", data)
            if not self._should_process_chat(data):
                return

            msg = data.get("msg", "")
            msg_parts = msg.split()
            command = msg_parts[0].casefold()

            if not command.startswith(Commands.COMMAND_SYMBOL.value):
                logger.debug("Chat message (%s) does not start with command symbol.", msg)
                return

            command = command[1:]

            if command in Commands.GENERAL_COMMANDS.value:
                logger.debug("Delegating to event processor.")
                await self._event_processor.handle_chat_message(data)
            elif command in Commands.CONTENT_COMMANDS.value:
                logger.debug("Delegating to content processor.")
                await self._content_processor.handle_chat_message(data)
            elif command in Commands.BLACKJACK_COMMANDS.value:
                logger.debug("Delegating to blackjack processor.")
                await self._blackjack_processor.handle_chat_message(data)
            else:
                await self._sio.send_chat_msg(f"'{command}' is not a valid command.")

        @self._sio._client.event
        async def mediaUpdate(data: Dict) -> None:
            logger.debug("mediaUpdate event captured: %s", data)
            # It is possible to miss the channelOpts event and skip the login call.
            # mediaUpdate is the only consistent event (so long as content is playing
            # which it should be as the bot is technically connected - unless someone else
            # is in the channel and pauses the content.)
            if self._sio.data.last_login is not None:  # avoid connecting to early on initial connection
                await self._sio.login()
            await self._content_processor.handle_media_update(data)

        @self._sio._client.event
        async def addUser(data: Dict) -> None:
            logger.debug("addUser event captured: %s", data)
            await self._event_processor.handle_user_join(data)

        @self._sio._client.event
        async def userLeave(data: Dict) -> None:
            logger.debug("userLeave event captured: %s", data)
            await self._event_processor.handle_user_leave(data)

        @self._sio._client.event
        async def changeMedia(data: Dict) -> None:
            logger.debug("changeMedia event captured: %s", data)
            await self._content_processor.handle_change_media(data)

        @self._sio._client.event
        async def login(data: Dict) -> None:
            logger.debug("login event captured: %s", data)
            if data["success"]:
                await self._event_processor.handle_successful_login(data)
            else:
                await self._event_processor.handle_failed_login(data)

        @self._sio._client.event
        async def setPermissions(data: Dict) -> None:
            logger.debug("setPermissions event captured: %s", data)
            self._event_processor.handle_set_permissions(data)

        @self._sio._client.event
        async def queue(data: Dict) -> None:
            logger.debug("queue event captured: %s", data)
            await self._content_processor.handle_successful_queue(data)

        @self._sio._client.event
        async def queueWarn(data: Dict) -> None:
            logger.debug("queueWarn event captured: %s", data)
            await self._content_processor.handle_successful_queue(data)

        @self._sio._client.event
        async def queueFail(data: Dict) -> None:
            logger.debug("queueFail event captured: %s", data)
            await self._content_processor.handle_failed_queue(data)

        @self._sio._client.event
        async def userlist(data: Dict) -> None:
            logger.debug("userlist event captured: %s", data)
            await self._event_processor.handle_user_list(data)

    async def run(self):
        """Start the bot by connecting to Socket.IO and waiting indefinitely."""
        await self._sio.connect()
        await self._sio._client.wait()

    async def read_content_queue(self):
        """
        Continuously consume worker results from RabbitMQ and forward them
        to the content processor for handling.
        """
        async for msg in self._result_consumer.consume():
            while not self._sio.data.logged_in:
                logger.debug("Bot disconnected. Waiting before processing content...")
                await asyncio.sleep(2)

            await self._content_processor.handle_new_content(msg)
            await asyncio.sleep(self._sio.data.current_backoff)
