import json
import logging
import ssl

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class AsyncKafkaProducer:
    def __init__(self, bootstrap_servers: str, topic: str, ssl_context: ssl.SSLContext):
        self._bootstrap = bootstrap_servers
        self._topic = topic
        self._ssl_context = ssl_context

    async def start(self):
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            linger_ms=5,
            ssl_context=self._ssl_context,
            security_protocol="SSL",
        )
        await self._producer.start()
        logger.info("Kafka producer started")

    async def send(self, data: dict) -> None:
        if not self._producer:
            return
        await self._producer.send_and_wait(self._topic, json.dumps(data).encode("utf-8"))

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped")
