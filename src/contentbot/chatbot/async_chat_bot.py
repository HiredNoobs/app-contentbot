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
from contentbot.common.rabbitmq_consumer import AsyncRabbitMQConsumer

logger: logging.Logger = logging.getLogger("contentbot")


class AsyncChatBot:
    def __init__(
        self,
        sio: AsyncSocket,
        event_processor: AsyncEventProcessor,
        content_processor: AsyncContentProcessor,
        blackjack_processor: AsyncBlackjackProcessor,
        db: AsyncRedisDB,
        result_consumer: AsyncRabbitMQConsumer,
    ):
        self._sio = sio
        self._event_processor = event_processor
        self._content_processor = content_processor
        self._blackjack_processor = blackjack_processor
        self._db = db
        self._result_consumer = result_consumer

        self._register_handlers()

    def _should_process_chat(self, data: Dict) -> bool:
        username = data.get("username")
        msg = data.get("msg", None)
        chat_ts = datetime.fromtimestamp(data["time"] / 1000)

        if not username or not msg or not chat_ts:
            return False

        if chat_ts < datetime.now() - timedelta(seconds=10):
            return False

        if username == self._sio.data.user:
            return False

        return True

    def _register_handlers(self):
        """
        Attach event handlers to the Socket.IO client.
        """

        @self._sio._client.event
        async def connect() -> None:
            logger.info("Socket connected.")
            await self._event_processor.handle_connect()

        @self._sio._client.event
        async def channelOpts(data: Dict) -> None:
            logger.debug("channelOpts event captured: %s", data)
            await self._event_processor.handle_channel_opts()

        @self._sio._client.event
        async def disconnect() -> None:
            logger.info("Socket disconnected.")
            self._event_processor.handle_disconnect()

        # AsyncChatBot only has some extra code because
        # it needs to route to the correct handler...
        @self._sio._client.event
        async def chatMsg(data: Dict) -> None:
            logger.debug("chatMsg event captured: %s", data)
            if not self._should_process_chat(data):
                return

            msg = data.get("msg", "")
            msg_parts = msg.split()
            command = msg_parts[0].casefold()

            if not command.startswith(Commands.COMMAND_SYMBOL.value):
                return

            command = command[1:]

            if command in Commands.GENERAL_COMMANDS.value.keys():
                await self._event_processor.handle_chat_message(data)
            elif command in Commands.CONTENT_COMMANDS.value.keys():
                await self._content_processor.handle_chat_message(data)
            elif command in Commands.BLACKJACK_COMMANDS.value.keys():
                await self._blackjack_processor.handle_chat_message(data)
            else:
                await self._sio.send_chat_msg(f"'{command}' is not a valid command.")

        @self._sio._client.event
        async def mediaUpdate(data: Dict) -> None:
            logger.debug("mediaUpdate event captured: %s", data)
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
        """
        Connect to Socket.IO and wait forever.
        """
        await self._sio.connect()
        await self._sio._client.wait()

    async def read_content_queue(self):
        """
        Consume worker results from RabbitMQ and delegate to the processor.
        """
        async for msg in self._result_consumer.consume():
            await self._content_processor.handle_new_content(msg)
