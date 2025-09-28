import json
import logging
import threading
from typing import Dict

import redis

logger = logging.getLogger(__name__)


class DatabaseWrapper:
    _instance = None
    _lock = threading.Lock()

    # Instance variable annotations for Mypy
    _host: str
    _port: int
    _redis: redis.Redis

    def __new__(cls, host: str, port: int):
        if cls._instance is None:
            with cls._lock:
                instance = super().__new__(cls)
                instance._host = host
                instance._port = port
                instance._redis = redis.Redis(
                    host=host, port=port, db=0, decode_responses=True
                )
                instance._create_consumer_group()
                cls._instance = instance
        return cls._instance

    def _close_connection(self) -> None:
        logger.info("Closing Redis connection.")
        self._redis.close()

    def _make_key(self, channel_id: str) -> str:
        return f"{channel_id}@youtube.channel.id"

    def _load_channel_data(self, channel_id: str) -> dict:
        key = self._make_key(channel_id)
        data_str = self._redis.get(key)
        if data_str and isinstance(data_str, str):
            try:
                logger.debug(f"Found {key}={data_str}")
                return json.loads(data_str)
            except json.JSONDecodeError:
                logger.exception(f"Failed to decode JSON data for key: {key}")
        return {}

    def _save_channel_data(self, channel_id: str, data: Dict) -> None:
        key = self._make_key(channel_id)
        logger.debug(f"Updating {key} with {data=}")
        try:
            self._redis.set(key, json.dumps(data))
        except Exception:
            logger.exception(f"Failed to save data for key: {key}")

    def _create_consumer_group(self) -> None:
        try:
            self._redis.xgroup_create(
                "stream:jobs:pending", "workers", id="0", mkstream=True
            )
        except redis.ResponseError:
            pass

    def add_to_stream(self, stream: str, data: Dict) -> None:
        self._redis.xadd(stream, data)

    def read_stream(self, stream: str) -> Dict:
        pend = self._redis.xpending(stream, "socketio")["pending"]
        pending_msgs = []
        if pend:
            pending_msgs = self._redis.xreadgroup(
                "socketio", "contentbot", {stream: "0"}, count=pend, block=0
            )

        new_messages = self._redis.xreadgroup(
            groupname="workers",
            consumername="worker",
            streams={stream: "0"},
            count=1,
            block=0,
        )

        return pending_msgs + new_messages

    def ack_stream_message(self, stream: str, id: str) -> None:
        self._redis.xack(stream, "workers", id)
        self._redis.xdel(stream, id)

    def update_datetime(self, channel_id: str, new_dt: str) -> None:
        data = self._load_channel_data(channel_id)
        if not data:
            logger.error(f"No channel found for ID: {channel_id}")
            return
        data["last_update"] = new_dt
        self._save_channel_data(channel_id, data)
        logger.info(f"Updated datetime for channel {channel_id}")

    def get_channels(self, tag: str | None = None) -> list:
        channels = []
        pattern = "*@youtube.channel.id"
        # scan_iter instead of keys to be more production friendly
        for key in self._redis.scan_iter(pattern):
            data_str = self._redis.get(key)
            if data_str and isinstance(data_str, str):
                try:
                    data = json.loads(data_str)
                    if tag:
                        if (
                            "tags" in data
                            and isinstance(data["tags"], list)
                            and tag in data["tags"]
                        ):
                            channels.append(data)
                    else:
                        channels.append(data)
                except json.JSONDecodeError:
                    logger.exception(f"JSON decoding failed for key: {key}")
        return channels

    def shutdown(self) -> None:
        logger.info("Shutting down DB remotely...")
        self._redis.shutdown(save=True)

    @property
    def connection(self) -> redis.Redis:
        return self._redis
