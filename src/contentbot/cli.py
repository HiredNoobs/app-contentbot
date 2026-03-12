import asyncio
import json
import logging
import os
from typing import Dict

import click

from contentbot.chatbot.async_chat_bot import AsyncChatBot
from contentbot.chatbot.async_event_processor import AsyncEventProcessor
from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.blackjack.async_blackjack_processor import (
    AsyncBlackjackProcessor,
)
from contentbot.chatbot.content.async_content_processor import AsyncContentProcessor
from contentbot.chatbot.content.async_redis_db import AsyncRedisDB
from contentbot.chatbot.sio_data import SIOData
from contentbot.common.rabbitmq_consumer import AsyncRabbitMQConsumer
from contentbot.common.rabbitmq_producer import AsyncRabbitMQProducer
from contentbot.configuration import Configuration
from contentbot.utils.ssl import create_ssl_context
from contentbot.worker.content_finder import ContentFinder
from contentbot.worker.random_finder import RandomFinder

logger: logging.Logger = logging.getLogger("contentbot")

# -----------------------------------------------------
# Helper functions
# -----------------------------------------------------


def load_config() -> Dict:
    config_path = os.getenv("CONFIG_PATH", "contentbot.conf")
    secrets_path = os.getenv("SECRETS_PATH", "contentbot_secrets.conf")
    config = Configuration(config_path, secrets_path)
    config.read()

    return config.to_dict()


# -----------------------------------------------------
# Functions
# -----------------------------------------------------


async def run_chatbot(cfg: Dict) -> None:
    siodata = SIOData()
    siodata.user = cfg["cytube_user"]

    db = AsyncRedisDB(
        cfg["db_host"],
        cfg["db_port"],
        cfg["db_index"],
        cfg["db_user"],
        cfg["db_pass"],
        cfg["db_ca_cert"],
        cfg["db_cert"],
        cfg["db_key"],
    )

    rabbit_ssl = create_ssl_context(cfg["rabbitmq_ca_cert"], cfg["rabbitmq_cert"], cfg["rabbitmq_key"])
    job_producer = AsyncRabbitMQProducer(cfg["rabbitmq_url"], cfg["rabbitmq_job_queue"], rabbit_ssl)
    result_consumer = AsyncRabbitMQConsumer(cfg["rabbitmq_url"], cfg["rabbitmq_result_queue"], rabbit_ssl)

    await job_producer.start()
    await result_consumer.start()

    sio = AsyncSocket(cfg["cytube_url"], cfg["cytube_channel"], cfg["cytube_user"], cfg["cytube_pass"], siodata)
    event_processor = AsyncEventProcessor(sio)
    content_processor = AsyncContentProcessor(sio, db, job_producer, result_consumer)
    blackjack_processor = AsyncBlackjackProcessor(sio)
    bot = AsyncChatBot(sio, event_processor, content_processor, blackjack_processor, db, result_consumer)

    try:
        await asyncio.gather(
            bot.run(),
            bot.read_content_queue(),
        )
    finally:
        await job_producer.stop()
        await result_consumer.stop()
        await db.close()


async def run_worker(cfg: Dict) -> None:
    db = AsyncRedisDB(
        cfg["db_host"],
        cfg["db_port"],
        cfg["db_index"],
        cfg["db_user"],
        cfg["db_pass"],
        cfg["db_ca_cert"],
        cfg["db_cert"],
        cfg["db_key"],
    )

    rabbit_ssl = create_ssl_context(
        cfg["rabbitmq_ca_cert"],
        cfg["rabbitmq_cert"],
        cfg["rabbitmq_key"],
    )

    job_consumer = AsyncRabbitMQConsumer(
        cfg["rabbitmq_url"],
        cfg["rabbitmq_job_queue"],
        rabbit_ssl,
    )

    result_producer = AsyncRabbitMQProducer(
        cfg["rabbitmq_url"],
        cfg["rabbitmq_result_queue"],
        rabbit_ssl,
    )

    await job_consumer.start()
    await result_producer.start()

    content_finder = ContentFinder()
    random_finder = RandomFinder()

    try:
        async for msg in job_consumer.consume():
            try:
                job = json.loads(msg.body)

                content = None
                if "channel_id" in job.keys():
                    content = content_finder.find_content(job)
                elif "random_size" in job.keys():
                    content = [random_finder.find_random(job["random_size"], job["random_word"])]

                if not content:
                    await job_consumer.commit(msg)
                    continue

                for c in content:
                    await result_producer.send(c)

                await job_consumer.commit(msg)
            except Exception as err:
                logger.exception("Unhandled exception: %s", err)
                await msg.nack(requeue=False)

    finally:
        await job_consumer.stop()
        await result_producer.stop()
        await db.close()


# -----------------------------------------------------
# Commands
# -----------------------------------------------------


@click.group(invoke_without_command=False)
def cli() -> None:
    pass


@cli.command()
def chatbot() -> None:
    cfg = load_config()
    asyncio.run(run_chatbot(cfg))


@cli.command()
def worker() -> None:
    cfg = load_config()
    asyncio.run(run_worker(cfg))
