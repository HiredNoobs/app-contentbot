import logging
import ssl
from typing import AsyncGenerator, Optional

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)

logger = logging.getLogger("contentbot")


class AsyncRabbitMQConsumer:
    """Asynchronous RabbitMQ consumer wrapper."""

    def __init__(
        self,
        amqp_url: str,
        queue_name: str,
        ssl_context: Optional[ssl.SSLContext] = None,
    ):
        """
        Initialise the consumer.

        Args:
            amqp_url (str): AMQP connection URL.
            queue_name (str): Name of the queue to consume from.
            ssl_context (Optional[ssl.SSLContext]): SSL context for secure connections.
        """
        self._amqp_url = amqp_url
        self._queue_name = queue_name
        self._ssl_context = ssl_context

        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._queue: Optional[AbstractQueue] = None

    async def start(self) -> None:
        """Establish a connection to RabbitMQ and declare the queue."""
        self._connection = await aio_pika.connect_robust(
            self._amqp_url,
            ssl=self._ssl_context is not None,
            ssl_context=self._ssl_context,
        )

        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=1)

        self._queue = await self._channel.declare_queue(
            self._queue_name,
            durable=True,
        )

        logger.info(f"RabbitMQ consumer started for queue {self._queue_name}")

    async def consume(self) -> AsyncGenerator[AbstractIncomingMessage, None]:
        """
        Yield messages from the queue as they arrive.

        This is an async generator that:
            - Iterates over the queue
            - Yields each message for manual processing
            - Expects the caller to ack/nack the message

        Returns:
            AsyncGenerator[AbstractIncomingMessage, None]: Stream of incoming messages.
        """
        if not self._queue:
            return

        async with self._queue.iterator() as queue_iter:
            async for msg in queue_iter:
                logger.debug("Received data from RabbitMQ: %s", msg.body)
                yield msg

    async def commit(self, msg: AbstractIncomingMessage) -> None:
        """
        Acknowledge a message as successfully processed.

        Args:
            msg (AbstractIncomingMessage): The message to acknowledge.
        """
        try:
            await msg.ack()
        except Exception as e:
            logger.error("Failed to ack message: %s", e)

    async def stop(self) -> None:
        """
        Close the channel and connection gracefully.

        This should be called during shutdown to ensure
        that the AMQP connection is properly closed.
        """
        if self._channel:
            await self._channel.close()

        if self._connection:
            await self._connection.close()

        logger.info("RabbitMQ consumer stopped")
