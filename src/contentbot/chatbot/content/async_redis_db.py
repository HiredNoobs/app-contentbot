import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import redis.asyncio as redis
from bs4 import BeautifulSoup as bs

from contentbot.utils.api_query import query_endpoint

logger: logging.Logger = logging.getLogger("contentbot")


class AsyncRedisDB:
    def __init__(
        self, host: str, port: int, index: int, username: str, password: str, ca_cert: str, cert: str, key: str
    ) -> None:
        self._redis = redis.Redis(
            host=host,
            port=port,
            db=index,
            username=username,
            password=password,
            decode_responses=True,
            ssl=True,
            ssl_ca_certs=ca_cert,
            ssl_certfile=cert,
            ssl_keyfile=key,
        )

    # -----------------------------------------------------
    # Static methods
    # -----------------------------------------------------

    @staticmethod
    def _make_channel_key(channel_id: str) -> str:
        return f"{channel_id}@youtube.channel.id"

    @staticmethod
    def _processed_key(channel_id: str) -> str:
        return f"{channel_id}@youtube.processed"

    # -----------------------------------------------------
    # General Redis methods
    # -----------------------------------------------------
    async def close(self) -> None:
        await self._redis.close()

    # -----------------------------------------------------
    # Content methods
    # -----------------------------------------------------

    async def _load_channel_data(self, channel_id: str) -> Dict:
        key = self._make_channel_key(channel_id)
        raw = await self._redis.get(key)
        if raw and isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.exception("Failed to load JSON from %s", key)
        return {}

    # Should this do something more useful if it fails..? Return a bool?
    async def _save_channel_data(self, channel_id: str, data: Dict) -> None:
        key = self._make_channel_key(channel_id)
        try:
            await self._redis.set(key, json.dumps(data))
        except Exception:
            logger.exception("Failed to save key %s.", key)

    async def update_datetime(self, channel_id: str, new_dt: str) -> None:
        data = await self._load_channel_data(channel_id)
        if not data:
            logger.error("No channel found for ID: %s", channel_id)
            return

        # Since the bot might not necessarily get data in order
        # records in Redis should only be updated with the most
        # recent timestamp.
        # This does open the possibility of losing some data...
        try:
            old_dt = data.get("last_update")
            if old_dt:
                old_dt_parsed = datetime.fromisoformat(old_dt)
                new_dt_parsed = datetime.fromisoformat(new_dt)

                if new_dt_parsed <= old_dt_parsed:
                    return
        except Exception:
            logger.exception("Failed comparing datetimes for %s", channel_id)
            return

        data["last_update"] = new_dt
        await self._save_channel_data(channel_id, data)

    async def get_channels(self, tag: Optional[str] = None) -> List[Dict]:
        channels: List[Dict] = []
        keys = [key async for key in self._redis.scan_iter("*@youtube.channel.id")]

        if not keys:
            return channels

        raw_values = await self._redis.mget(keys)

        for raw in raw_values:
            if not raw or not isinstance(raw, str):
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.exception("Failed to load JSON from mget result")
                continue

            if tag:
                if tag in data.get("tags", []):
                    channels.append(data)
            else:
                channels.append(data)

        return channels

    # TODO: Add optional tags & check if channel already in DB.
    async def add_channel(self, channel_id: str, channel_name: str) -> None:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        try:
            resp = query_endpoint(url)
            resp.raise_for_status()
        except Exception:
            logger.exception(f"Failed to fetch feed for {channel_id}")
            return

        soup = bs(resp.text, "lxml")
        try:
            entry = soup.find_all("entry")[0]
            published = entry.find_all("published")[0].text
        except Exception:
            logger.error(f"Failed to parse feed for {channel_id}")
            return

        data = {
            "channelId": channel_id,
            "name": channel_name,
            "last_update": published,
            "tags": [],
        }
        await self._save_channel_data(channel_id, data)

    # Would it be easier to do channel_name -> lookup ID -> DEL key?
    async def remove_channel(self, channel_name: str) -> None:
        async for key in self._redis.scan_iter("*@youtube.channel.id"):
            raw = await self._redis.get(key)
            if not raw or not isinstance(raw, str):
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("name") == channel_name:
                await self._redis.delete(key)
                return

    async def add_tags(self, channel_id: str, new_tags: List[str]) -> None:
        data = await self._load_channel_data(channel_id)
        tags = set(data.get("tags", []))
        tags.update(new_tags)
        data["tags"] = list(tags)
        await self._save_channel_data(channel_id, data)

    async def remove_tags(self, channel_id: str, tags_to_remove: List[str]) -> None:
        data = await self._load_channel_data(channel_id)
        tags = data.get("tags", [])
        data["tags"] = [t for t in tags if t not in tags_to_remove]
        await self._save_channel_data(channel_id, data)

    # -----------------------------------------------------
    # Queue handling methods
    # -----------------------------------------------------

    # These mappings are required because Cytube only returns the video ID
    # and we'll need the channel ID later for the pending/processed keys.
    async def map_video_to_channel(self, video_id: str, channel_id: str) -> None:
        key = f"{video_id}@youtube.channel.mapping"
        await self._redis.set(key, channel_id, ex=3600)

    async def get_channel_for_video(self, video_id: str) -> Optional[str]:
        key = f"{video_id}@youtube.channel.mapping"
        return await self._redis.get(key)

    async def clear_video_channel_map(self, video_id: str) -> None:
        key = f"{video_id}@youtube.channel.mapping"
        await self._redis.delete(key)

    #
    # Kafka
    #
    async def map_video_to_kafka_offset(self, video_id: str, topic: str, partition: int, offset: int):
        key = f"{video_id}@kafka.offset.mapping"
        value = json.dumps({"topic": topic, "partition": partition, "offset": offset})
        await self._redis.set(key, value, ex=3600)

    async def get_kafka_offset_for_video(self, video_id: str):
        key = f"{video_id}@kafka.offset.mapping"
        raw = await self._redis.get(key)
        return json.loads(raw) if raw else None

    async def clear_kafka_offset_map(self, video_id: str):
        key = f"{video_id}@kafka.offset.mapping"
        await self._redis.delete(key)

    #
    # Pending
    #
    async def mark_video_pending(self, channel_id: str, video_id: str) -> None:
        key = f"{channel_id}@youtube.pending"
        await self._redis.sadd(key, video_id)

    async def is_video_pending(self, channel_id: str, video_id: str) -> bool:
        key = f"{channel_id}@youtube.pending"
        return await self._redis.sismember(key, video_id)

    async def clear_video_pending(self, channel_id: str, video_id: str) -> None:
        key = f"{channel_id}@youtube.pending"
        await self._redis.srem(key, video_id)

    #
    # Processed
    #
    async def mark_video_processed(self, channel_id: str, video_id: str) -> None:
        """
        Mark a video as successfully processed.
        """
        key = self._processed_key(channel_id)
        try:
            await self._redis.sadd(key, video_id)
        except Exception:
            logger.exception("Failed to mark video %s as processed for channel %s", video_id, channel_id)

    async def is_video_processed(self, channel_id: str, video_id: str) -> bool:
        """
        Check if a video has already been processed.
        """
        key = self._processed_key(channel_id)
        try:
            return await self._redis.sismember(key, video_id)
        except Exception:
            logger.exception("Failed to check processed state for %s on channel %s", video_id, channel_id)
            return False
