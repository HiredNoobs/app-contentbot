import json
import logging
import ssl
from typing import Optional

import aio_pika
from aio_pika import Message, RobustChannel, RobustConnection

logger = logging.getLogger("contentbot")


class AsyncRabbitMQProducer:
    def __init__(self, amqp_url: str, queue_name: str, ssl_context: Optional[ssl.SSLContext] = None):
        self._amqp_url = amqp_url
        self._queue_name = queue_name
        self._ssl_context = ssl_context

        self._connection: Optional[RobustConnection] = None
        self._channel: Optional[RobustChannel] = None
        self._queue = None

    async def start(self):
        """
        Establish connection and declare the queue.
        """
        self._connection = await aio_pika.connect_robust(
            self._amqp_url,
            ssl=self._ssl_context is not None,
            ssl_context=self._ssl_context,
        )

        self._channel = await self._connection.channel()
        self._queue = await self._channel.declare_queue(
            self._queue_name,
            durable=True,
        )

        logger.info("RabbitMQ producer started")

    async def send(self, data: dict) -> None:
        """
        Publish a JSON message to the queue.
        """
        if not self._channel:
            return

        body = json.dumps(data).encode("utf-8")
        logger.debug("Publishing %s to RabbitMQ queue %s", body, self._queue_name)

        await self._channel.default_exchange.publish(
            Message(body=body),
            routing_key=self._queue_name,
        )

    async def stop(self):
        """
        Close channel and connection.
        """
        if self._channel:
            await self._channel.close()

        if self._connection:
            await self._connection.close()

        logger.info("RabbitMQ producer stopped")
