import asyncio
import json
import logging
import os
from typing import Dict

import click

from contentbot.chatbot.async_chat_bot import AsyncChatBot
from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.content.async_chat_processor import AsyncChatProcessor
from contentbot.chatbot.content.async_redis_db import AsyncRedisDB
from contentbot.common.kafka_consumer import AsyncKafkaConsumer
from contentbot.common.kafka_producer import AsyncKafkaProducer
from contentbot.configuration import Configuration
from contentbot.utils.ssl import create_ssl_context
from contentbot.worker.content_finder import ContentFinder

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

    kafka_ssl = create_ssl_context(cfg["kafka_ca_cert"], cfg["kafka_cert"], cfg["kafka_key"])
    kafka_producer = AsyncKafkaProducer(cfg["kafka_bootstrap_servers"], cfg["kafka_job_topic"], kafka_ssl)
    kafka_consumer = AsyncKafkaConsumer(
        cfg["kafka_bootstrap_servers"], cfg["kafka_content_topic"], cfg["kafka_consumer_group"], kafka_ssl
    )

    await kafka_producer.start()
    await kafka_consumer.start(False)

    sio = AsyncSocket(cfg["cytube_url"], cfg["cytube_channel"], cfg["cytube_user"], cfg["cytube_pass"])
    processor = AsyncChatProcessor(sio, db, kafka_producer, kafka_consumer)
    bot = AsyncChatBot(sio, processor, db, kafka_consumer)

    try:
        await asyncio.gather(
            bot.run(),
            bot.consume_kafka_jobs(),
        )
    finally:
        await kafka_producer.stop()
        await kafka_consumer.stop()
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

    kafka_ssl = create_ssl_context(cfg["kafka_ca_cert"], cfg["kafka_cert"], cfg["kafka_key"])
    kafka_producer = AsyncKafkaProducer(cfg["kafka_bootstrap_servers"], cfg["kafka_content_topic"], kafka_ssl)
    kafka_consumer = AsyncKafkaConsumer(
        cfg["kafka_bootstrap_servers"], cfg["kafka_job_topic"], cfg["kafka_consumer_group"], kafka_ssl
    )

    await kafka_producer.start()
    await kafka_consumer.start(True)

    content_finder = ContentFinder()

    try:
        async for channel_record in kafka_consumer.consume():
            try:
                channel = json.loads(channel_record.msg)
                content = content_finder.find_content(channel)
                for c in content:
                    await kafka_producer.send(c)
            except Exception as err:
                logger.exception("Unhandled exception: %s", err)
    finally:
        await kafka_consumer.stop()
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
