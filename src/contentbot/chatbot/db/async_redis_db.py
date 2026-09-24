import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import redis.asyncio as redis
from bs4 import BeautifulSoup as bs

from contentbot.common.utils.api_query import query_endpoint

logger: logging.Logger = logging.getLogger("contentbot")

VIDEO_PUBLISH_TIME_TTL = int(timedelta(days=30).total_seconds())
CONTENT_BATCH_TTL = int(timedelta(days=1).total_seconds())


class AsyncRedisDB:
    """
    Asynchronous Redis interface for storing and retrieving YouTube channel metadata.
    """

    def __init__(
        self,
        host: str,
        port: int,
        index: int,
        username: str,
        password: str,
        ca_cert: Optional[str],
        cert: Optional[str],
        key: Optional[str],
    ) -> None:
        """
        Initialise the Redis connection with SSL authentication.

        Args:
            host (str): Redis host address.
            port (int): Redis port number.
            index (int): Redis database index.
            username (str): Redis username.
            password (str): Redis password.
            ca_cert (Optional[str]): Path to CA certificate.
            cert (Optiona[str]): Path to client certificate.
            key (Optional[str]): Path to client key file.
        """
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
        """
        Construct the Redis key used to store channel metadata.

        Args:
            channel_id (str): YouTube channel ID.

        Returns:
            str: Redis key for the channel.
        """
        return f"{channel_id}@youtube.channel.id"

    @staticmethod
    def _make_video_publish_time_key(video_id: str) -> str:
        """
        Construct the Redis key used to store a video's publish time.

        Args:
            video_id (str): YouTube video ID.

        Returns:
            str: Redis key for the video's publish time.
        """
        return f"{video_id}@youtube.video.published"

    @staticmethod
    def _make_random_video_key(video_id: str) -> str:
        """
        Construct the Redis key used to flag a video as found by the random commands.

        Args:
            video_id (str): YouTube video ID.

        Returns:
            str: Redis key for the random video flag.
        """
        return f"{video_id}@youtube.video.random"

    @staticmethod
    def _make_content_batch_key(batch_id: str) -> str:
        """
        Construct the Redis key used to track the finished jobs of a content batch.

        Args:
            batch_id (str): Content batch ID.

        Returns:
            str: Redis key for the batch.
        """
        return f"{batch_id}@contentbot.batch"

    # -----------------------------------------------------
    # General Redis methods
    # -----------------------------------------------------

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()

    # -----------------------------------------------------
    # Content methods
    # -----------------------------------------------------

    async def _load_channel_data(self, channel_id: str) -> Dict:
        """
        Load channel metadata from Redis.

        Args:
            channel_id (str): YouTube channel ID.

        Returns:
            Dict: Parsed channel data, or an empty dict if missing or invalid.
        """
        key = self._make_channel_key(channel_id)
        raw = await self._redis.get(key)
        if raw and isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.exception("Failed to load JSON from %s", key)
        return {}

    async def _save_channel_data(self, channel_id: str, data: Dict) -> None:
        """
        Save channel data to Redis.

        Args:
            channel_id (str): YouTube channel ID.
            data (Dict): Channel data to store.
        """
        key = self._make_channel_key(channel_id)
        try:
            await self._redis.set(key, json.dumps(data))
        except Exception:
            logger.exception("Failed to save key %s.", key)

    async def update_datetime(self, channel_id: str, new_dt: str) -> None:
        """
        Update the stored last_update timestamp for a channel,
        but only if the new timestamp is more recent.

        Args:
            channel_id (str): YouTube channel ID.
            new_dt (str): ISO8601 timestamp string.
        """
        data = await self._load_channel_data(channel_id)
        if not data:
            logger.error("No channel found for ID: %s", channel_id)
            return

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
        """
        Retrieve all stored channels, optionally filtered by tag.

        Args:
            tag (Optional[str]): Tag to filter by. If None (or false-y),
            all channels are returned.

        Returns:
            List[Dict]: List of channel metadata dictionaries.
        """
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

    async def get_channel_id(self, channel_name: str) -> Optional[str]:
        """
        Look up a channel ID by its name.

        Args:
            channel_name (str): Channel name.

        Returns:
            Optional[str]: Channel ID if found, otherwise None.
        """
        async for key in self._redis.scan_iter("*@youtube.channel.id"):
            raw = await self._redis.get(key)
            if not raw or not isinstance(raw, str):
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("channel_name") == channel_name:
                return data.get("channel_id")

        return None

    async def _channel_exists(self, channel_id: str) -> bool:
        """
        Check whether a channel ID already exists in Redis.

        Args:
            channel_id (str): YouTube channel ID.

        Returns:
            bool: True if the channel exists, otherwise False.
        """
        return await self._redis.exists(f"{channel_id}@youtube.channel.id") > 0

    async def add_channel(self, channel_id: str, channel_name: str, tags: Optional[List] = None) -> bool:
        """
        Add a new YouTube channel to Redis.

        Args:
            channel_id (str): YouTube channel ID.
            channel_name (str): Human-readable channel name.
            tags (Optional[List]): Optional list of tags.

        Returns:
            bool: True if added successfully, False if the channel already exists or if the
            XML feed can't be loaded for the channel.
        """
        if await self._channel_exists(channel_id):
            return False

        if not tags:
            tags = []

        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        try:
            resp = await query_endpoint(url)
            resp.raise_for_status()
        except Exception:
            logger.exception(f"Failed to fetch feed for {channel_id}")
            return False

        soup = bs(resp.text, "lxml")
        try:
            entry = soup.find_all("entry")[0]
            published = entry.find_all("published")[0].text
        except Exception:
            logger.error(f"Failed to parse feed for {channel_id}")
            return False

        data = {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "last_update": published,
            "tags": tags,
        }
        await self._save_channel_data(channel_id, data)
        return True

    async def remove_channels(self, channel_names: List[str]) -> int:
        """
        Remove channels from Redis by their stored names.

        Args:
            channel_names (List[str]): List of channel names to delete.

        Returns:
            int: Number of channels successfully removed.
        """
        deleted_count = 0
        async for key in self._redis.scan_iter("*@youtube.channel.id"):
            raw = await self._redis.get(key)
            if not raw or not isinstance(raw, str):
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("channel_name") in channel_names:
                await self._redis.delete(key)
                deleted_count += 1

        return deleted_count

    async def add_tags(self, channel_id: str, new_tags: List[str]) -> None:
        """
        Add tags to a channel.

        Args:
            channel_id (str): YouTube channel ID.
            new_tags (List[str]): Tags to add.
        """
        data = await self._load_channel_data(channel_id)
        if not data:
            logger.error("No channel found for ID: %s", channel_id)
            return

        tags = set(data.get("tags", []))
        tags.update(new_tags)
        data["tags"] = list(tags)
        await self._save_channel_data(channel_id, data)

    async def remove_tags(self, channel_id: str, tags_to_remove: List[str]) -> None:
        """
        Remove tags from a channel.

        Args:
            channel_id (str): YouTube channel ID.
            tags_to_remove (List[str]): Tags to remove.
        """
        data = await self._load_channel_data(channel_id)
        if not data:
            logger.error("No channel found for ID: %s", channel_id)
            return

        tags = data.get("tags", [])
        data["tags"] = [t for t in tags if t not in tags_to_remove]
        await self._save_channel_data(channel_id, data)

    # -----------------------------------------------------
    # Video methods
    # -----------------------------------------------------

    async def get_video_publish_time(self, video_id: str) -> Optional[str]:
        """
        Get the cached publish time for a video.

        Args:
            video_id (str): YouTube video ID.

        Returns:
            Optional[str]: ISO8601 publish time if cached, otherwise None.
        """
        raw = await self._redis.get(self._make_video_publish_time_key(video_id))
        return raw if isinstance(raw, str) else None

    async def set_video_publish_time(self, video_id: str, published: str) -> None:
        """
        Cache the publish time for a video.

        The key expires so the cache doesn't grow indefinitely with videos
        that have long since left the queue.

        Args:
            video_id (str): YouTube video ID.
            published (str): ISO8601 publish time.
        """
        key = self._make_video_publish_time_key(video_id)
        try:
            await self._redis.set(key, published, ex=VIDEO_PUBLISH_TIME_TTL)
        except Exception:
            logger.exception("Failed to save key %s.", key)

    async def mark_random_video(self, video_id: str) -> None:
        """
        Flag a video as found by the random commands.

        The key expires so the flag doesn't outlive the video's time in the queue.

        Args:
            video_id (str): YouTube video ID.
        """
        key = self._make_random_video_key(video_id)
        try:
            await self._redis.set(key, 1, ex=VIDEO_PUBLISH_TIME_TTL)
        except Exception:
            logger.exception("Failed to save key %s.", key)

    async def is_random_video(self, video_id: str) -> bool:
        """
        Check whether a video was found by the random commands.

        Args:
            video_id (str): YouTube video ID.

        Returns:
            bool: True if the video is flagged as random, otherwise False.
        """
        return await self._redis.exists(self._make_random_video_key(video_id)) > 0

    # -----------------------------------------------------
    # Content batch methods
    # -----------------------------------------------------

    async def complete_batch_job(self, batch_id: str, job_index: int, batch_size: int) -> bool:
        """
        Record a finished job of a content batch.

        Jobs are recorded by index in a set, so a redelivered job isn't counted twice,
        and in a transaction, so only one worker sees the batch finish.

        Args:
            batch_id (str): Content batch ID.
            job_index (int): Index of the job within the batch.
            batch_size (int): Number of jobs in the batch.

        Returns:
            bool: True if this job finished the batch.
        """
        key = self._make_content_batch_key(batch_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.sadd(key, job_index)
            pipe.scard(key)
            pipe.expire(key, CONTENT_BATCH_TTL)
            added, finished, _ = await pipe.execute()

        return bool(added) and finished >= batch_size
