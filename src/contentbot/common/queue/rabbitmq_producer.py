import json
import logging
import ssl
from typing import Optional

import aio_pika
from aio_pika import Message, RobustChannel, RobustConnection

logger = logging.getLogger("contentbot")


class AsyncRabbitMQProducer:
    """Asynchronous RabbitMQ producer wrapper."""

    def __init__(self, amqp_url: str, queue_name: str, ssl_context: Optional[ssl.SSLContext] = None):
        """
        Initialise the producer.

        Args:
            amqp_url (str): AMQP connection URL.
            queue_name (str): Name of the queue to publish messages to.
            ssl_context (Optional[ssl.SSLContext]): SSL context for secure connections.
        """
        self._amqp_url = amqp_url
        self._queue_name = queue_name
        self._ssl_context = ssl_context

        self._connection: Optional[RobustConnection] = None
        self._channel: Optional[RobustChannel] = None
        self._queue = None

    async def start(self):
        """Establish a connection to RabbitMQ and declare the queue."""
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
        Publish a JSON encoded message to the queue.

        Args:
            data (dict): The message payload to send. It will be JSON encoded
                and published to the configured queue.
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
        """Close the AMQP channel and connection gracefully."""
        if self._channel:
            await self._channel.close()

        if self._connection:
            await self._connection.close()

        logger.info("RabbitMQ producer stopped")
