import logging
import os
from datetime import datetime, timedelta
from typing import Dict

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.blackjack.async_blackjack_processor import (
    AsyncBlackjackProcessor,
)
from contentbot.chatbot.commands import Commands
from contentbot.chatbot.content.async_chat_processor import AsyncChatProcessor
from contentbot.chatbot.content.async_redis_db import AsyncRedisDB
from contentbot.common.rabbitmq_consumer import AsyncRabbitMQConsumer

logger: logging.Logger = logging.getLogger("contentbot")


class AsyncChatBot:
    def __init__(
        self,
        sio: AsyncSocket,
        processor: AsyncChatProcessor,
        blackjack_processor: AsyncBlackjackProcessor,
        db: AsyncRedisDB,
        result_consumer: AsyncRabbitMQConsumer,
    ):
        self._sio = sio
        self._processor = processor
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
            await self._processor.handle_connect()

        @self._sio._client.event
        async def channelOpts(data: Dict) -> None:
            logger.debug("channelOpts event captured: %s", data)
            await self._processor.handle_channel_opts()

        @self._sio._client.event
        async def disconnect() -> None:
            logger.info("Socket disconnected.")

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

            if command in Commands.STANDARD_COMMANDS.value.keys():
                await self._processor.handle_chat_message(data)
            elif command in Commands.BLACKJACK_COMMANDS.value.keys():
                await self._blackjack_processor.handle_chat_message(data)
            else:
                await self._sio.send_chat_msg(f"'{command}' is not a valid command.")

        @self._sio._client.event
        async def mediaUpdate(data: Dict) -> None:
            logger.debug("mediaUpdate event captured: %s", data)
            await self._processor.handle_media_update(data)

        @self._sio._client.event
        async def userJoin(data: Dict) -> None:
            logger.debug("userJoin event captured: %s", data)
            await self._processor.handle_user_join(data)

        @self._sio._client.event
        async def userLeave(data: Dict) -> None:
            logger.debug("userLeave event captured: %s", data)
            await self._processor.handle_user_leave(data)

        @self._sio._client.event
        async def changeMedia(data: Dict) -> None:
            logger.debug("changeMedia event captured: %s", data)
            await self._processor.handle_change_media(data)

        @self._sio._client.event
        async def queue(data: Dict) -> None:
            logger.debug("queue event captured: %s", data)
            await self._processor.handle_successful_queue(data)

        @self._sio._client.event
        async def queueWarn(data: Dict) -> None:
            logger.debug("queueWarn event captured: %s", data)
            await self._processor.handle_successful_queue(data)

        @self._sio._client.event
        async def queueFail(data: Dict) -> None:
            logger.debug("queueFail event captured: %s", data)
            await self._processor.handle_failed_queue(data)

        @self._sio._client.event
        async def userlist(data: Dict) -> None:
            logger.debug("userlist event captured: %s", data)
            await self._processor.handle_user_list(data)

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
            await self._processor.handle_new_content(msg)
