import logging
import ssl
from typing import AsyncGenerator

from aiokafka import AIOKafkaConsumer, ConsumerRecord, OffsetAndMetadata, TopicPartition

logger = logging.getLogger("contentbot")


class AsyncKafkaConsumer:
    def __init__(self, bootstrap_servers: str, topic: str, group_id: str, ssl_context: ssl.SSLContext):
        self._topic = topic
        self._bootstrap = bootstrap_servers
        self._group_id = group_id
        self._ssl_context = ssl_context
        self._consumer = None

    async def start(self, auto_commit: bool = True) -> None:
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            enable_auto_commit=auto_commit,
            auto_offset_reset="latest",
            ssl_context=self._ssl_context,
            security_protocol="SSL",
        )

        # Yes this is really necessary according to mypy...
        if not self._consumer:
            return

        await self._consumer.start()
        logger.info(f"Kafka consumer started for topic {self._topic}")

    async def consume(self) -> AsyncGenerator[ConsumerRecord]:
        if not self._consumer:
            return

        async for msg in self._consumer:
            logger.debug("Receieved data from Kafka: %s", msg.value)
            yield msg

    async def commit(self, topic: str, partition: int, offset: int) -> None:
        if not self._consumer:
            return

        tp = TopicPartition(topic, partition)
        om = OffsetAndMetadata(offset + 1, None)
        await self._consumer.commit({tp: om})

    async def stop(self):
        if not self._consumer:
            return

        await self._consumer.stop()
        logger.info("Kafka consumer stopped")
