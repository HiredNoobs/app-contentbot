import asyncio
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

logger: logging.Logger = logging.getLogger("contentbot")


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    config_path = os.getenv("CONFIG_PATH", "contentbot.conf")
    secrets_path = os.getenv("SECRETS_PATH", "contentbot_secrets.conf")
    config = Configuration(config_path, secrets_path)
    config.read()

    ctx.obj = config.to_dict()


# -----------------------------------------------------
# Commands
# -----------------------------------------------------


@cli.command
@click.pass_context
def chatbot(ctx: click.Context) -> None:
    asyncio.run(run_chatbot(ctx.obj))


@cli.command
@click.pass_context
def worker(ctx: click.Context) -> None:
    asyncio.run(run_worker(ctx.obj))


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
    await kafka_consumer.start()

    sio = AsyncSocket(cfg["cytube_url"], cfg["cytube_channel"], cfg["cytube_user"], cfg["cytube_pass"])
    processor = AsyncChatProcessor(sio, db, kafka_producer)
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
    await kafka_consumer.start()

    try:
        async for _ in kafka_consumer.consume():
            pass
    finally:
        await kafka_consumer.stop()
        await db.close()
