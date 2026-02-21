import json
import logging
import ssl

from aiokafka import AIOKafkaConsumer, OffsetAndMetadata, TopicPartition

logger = logging.getLogger("contentbot")


class AsyncKafkaConsumer:
    def __init__(self, bootstrap_servers: str, topic: str, group_id: str, ssl_context: ssl.SSLContext):
        self._topic = topic
        self._bootstrap = bootstrap_servers
        self._group_id = group_id
        self._ssl_context = ssl_context
        self._consumer = None

    async def start(self, auto_commit: bool) -> None:
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            enable_auto_commit=auto_commit,
            auto_offset_reset="latest",
            ssl_context=self._ssl_context,
            security_protocol="SSL",
        )
        await self._consumer.start()
        logger.info(f"Kafka consumer started for topic {self._topic}")

    async def consume(self):
        async for msg in self._consumer:
            logger.debug("Receieved data from Kafka: %s", msg.value)
            yield json.loads(msg)

    async def commit(self, topic: str, partition: int, offset: int) -> None:
        if self._consumer:
            tp = TopicPartition(topic, partition)
            om = OffsetAndMetadata(offset + 1, None)
            await self._consumer.commit({tp: om})

    async def stop(self):
        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka consumer stopped")
