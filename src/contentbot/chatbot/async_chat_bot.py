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

        @self.sio.event
        async def connect():
            logger.info("Socket connected.")

        @self.sio.event
        async def disconnect():
            logger.info("Socket disconnected.")

        @self.sio.event
        async def chatMsg(data):
            await self._processor.handle_chat_message(data)

        @self.sio.event
        async def userJoin(data):
            await self._processor.handle_user_join(data)

        @self.sio.event
        async def userLeave(data):
            await self._processor.handle_user_leave(data)

        @self.sio.event
        async def setCurrent(data):
            await self._processor.handle_set_current(data)

    async def run(self):
        """
        Connect to Socket.IO and wait forever.
        """
        await self.sio.connect()
        await self.sio.wait()

    async def consume_kafka_jobs(self):
        """
        Consume Kafka jobs and delegate to the processor.
        """
        async for msg in self.kafka_consumer.consume():
            await self._processor.handle_kafka_job(msg)
