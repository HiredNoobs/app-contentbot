import logging

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.content.async_chat_processor import AsyncChatProcessor
from contentbot.chatbot.content.async_redis_db import AsyncRedisDB
from contentbot.common.kafka_consumer import AsyncKafkaConsumer

logger: logging.Logger = logging.getLogger("contentbot")


class AsyncChatBot:
    def __init__(
        self,
        sio: AsyncSocket,
        processor: AsyncChatProcessor,
        db: AsyncRedisDB,
        kafka_consumer: AsyncKafkaConsumer,
    ):
        self._sio = sio
        self._processor = processor
        self._db = db
        self._kafka_consumer = kafka_consumer

        self._register_handlers()

    def _register_handlers(self):
        """
        Attach event handlers to the Socket.IO client.
        """

        @self._sio.client.event
        async def connect():
            logger.info("Socket connected.")
            await self._processor.handle_connect()

        @self._sio.client.event
        async def channelOpts(data):
            logger.debug("channelOpts event captured: %s", data)
            await self._processor.handle_channel_opts()

        @self._sio.client.event
        async def disconnect():
            logger.info("Socket disconnected.")

        @self._sio.client.event
        async def chatMsg(data):
            logger.debug("chatMsg event captured: %s", data)
            await self._processor.handle_chat_message(data)

        @self._sio.client.event
        async def userJoin(data):
            logger.debug("userJoin event captured: %s", data)
            await self._processor.handle_user_join(data)

        @self._sio.client.event
        async def userLeave(data):
            logger.debug("userLeave event captured: %s", data)
            await self._processor.handle_user_leave(data)

        @self._sio.client.event
        async def setCurrent(data):
            logger.debug("setCurrent event captured: %s", data)
            await self._processor.handle_set_current(data)

    async def run(self):
        """
        Connect to Socket.IO and wait forever.
        """
        await self._sio.connect()
        await self._sio.client.wait()

    async def consume_kafka_jobs(self):
        """
        Consume Kafka jobs and delegate to the processor.
        """
        async for msg in self._kafka_consumer.consume():
            await self._processor.handle_kafka_job(msg)
