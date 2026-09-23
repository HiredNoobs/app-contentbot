import logging
import re
from bisect import bisect_left
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup as bs

from contentbot.chatbot.db.async_redis_db import AsyncRedisDB
from contentbot.common.utils.api_query import query_endpoint

logger: logging.Logger = logging.getLogger("contentbot")

# Matches the channel ID on a channel page, e.g. from https://www.youtube.com/@handle.
CHANNEL_ID_PATTERNS = (
    re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"'),
    re.compile(r'"externalId":"(UC[\w-]{22})"'),
)


class QueueSorter:
    """Class for planning a Cytube queue sort by video publish time."""

    def __init__(self, db: AsyncRedisDB):
        """
        Initialise the queue sorter.

        Args:
            db (AsyncRedisDB): Redis database interface used to cache publish times.
        """
        self._db = db

        # Per-sort lookups, so videos from the same channel share requests.
        self._channel_ids: Dict[str, Optional[str]] = {}
        self._feeds: Dict[str, Dict[str, datetime]] = {}

    async def sort_queue(self, playlist: List[Dict]) -> Dict:
        """
        Plan the moves needed to sort temporary items after the permanent items by publish time.

        Permanent items keep their current relative order. Temporary items without a known
        publish time stay in their current position and the dated items are sorted around
        them, except for undated random videos which are moved to the end.

        Args:
            playlist (List[Dict]): Playlist snapshot, each item containing:
                - uid (int)
                - temp (bool)
                - media_id (str)
                - media_type (str)

        Returns:
            Dict: A result dictionary containing:
                {
                    "type": "sort_queue",
                    "moves": List[Dict] of moveMedia payloads,
                    "unknown": int count of undated items left in place,
                    "unknown_random": int count of undated random items moved to the end
                }
        """
        self._channel_ids = {}
        self._feeds = {}

        playlist = [item for item in playlist if item.get("uid") is not None]
        permanent_items = [item for item in playlist if not item.get("temp")]
        temp_items = [item for item in playlist if item.get("temp")]

        # Undated items keep their slot; dated items are sorted into the remaining slots.
        slots: List[Tuple[Optional[datetime], Dict]] = []
        unknown_random: List[Dict] = []
        for item in temp_items:
            published = await self._get_publish_time(item)
            if published is None and await self._is_random(item):
                unknown_random.append(item)
            else:
                slots.append((published, item))

        dated_items = iter(
            item
            for _, _, item in sorted(
                (published, position, item) for position, (published, item) in enumerate(slots) if published is not None
            )
        )
        ordered_temp_items = [item if published is None else next(dated_items) for published, item in slots]

        current_order = [item["uid"] for item in playlist]
        desired_order = [item["uid"] for item in permanent_items + ordered_temp_items + unknown_random]

        return {
            "type": "sort_queue",
            "moves": self._plan_moves(current_order, desired_order),
            "unknown": sum(1 for published, _ in slots if published is None),
            "unknown_random": len(unknown_random),
        }

    async def _is_random(self, item: Dict) -> bool:
        """
        Check whether a playlist item was found by the random commands.

        Args:
            item (Dict): Playlist snapshot item.

        Returns:
            bool: True if the item is flagged as random, otherwise False.
        """
        video_id = item.get("media_id")
        if not video_id or item.get("media_type") != "yt":
            return False
        return await self._db.is_random_video(video_id)

    async def _get_publish_time(self, item: Dict) -> Optional[datetime]:
        """
        Get the publish time for a playlist item, using the Redis cache where possible.

        Args:
            item (Dict): Playlist snapshot item.

        Returns:
            Optional[datetime]: UTC publish time, or None if it could not be resolved.
        """
        video_id = item.get("media_id")
        if not video_id or item.get("media_type") != "yt":
            return None

        cached = await self._db.get_video_publish_time(video_id)
        if cached:
            try:
                return self._as_utc(datetime.fromisoformat(cached))
            except ValueError:
                logger.warning("Ignoring invalid cached publish time for %s: %s", video_id, cached)

        return await self._fetch_publish_time(video_id)

    async def _fetch_publish_time(self, video_id: str) -> Optional[datetime]:
        """
        Fetch the publish time for a YouTube video from its channel's RSS feed.

        The feed only contains the channel's most recent uploads, so older videos
        won't be found. Every entry in the feed is cached, not just the requested video.

        Args:
            video_id (str): YouTube video ID.

        Returns:
            Optional[datetime]: UTC publish time, or None if it could not be resolved.
        """
        channel_id = await self._get_channel_id(video_id)
        if not channel_id:
            return None

        if channel_id not in self._feeds:
            self._feeds[channel_id] = await self._fetch_feed(channel_id)

        published = self._feeds[channel_id].get(video_id)
        if not published:
            logger.debug("%s not in the RSS feed for %s", video_id, channel_id)
        return published

    async def _get_channel_id(self, video_id: str) -> Optional[str]:
        """
        Resolve the channel ID for a video via oEmbed and the channel page.

        Args:
            video_id (str): YouTube video ID.

        Returns:
            Optional[str]: The channel ID, or None if it could not be resolved.
        """
        video_url = quote(f"https://www.youtube.com/watch?v={video_id}", safe="")
        oembed_url = f"https://www.youtube.com/oembed?url={video_url}&format=json"

        try:
            resp = await query_endpoint(oembed_url, max_retries=1)
            author_url = resp.json().get("author_url")
        except (requests.exceptions.RequestException, ValueError) as err:
            # Private, deleted, and non-embeddable videos return an error here.
            logger.warning("Failed to get oEmbed data for %s: %s", video_id, err)
            return None

        if not author_url:
            logger.warning("No channel URL in oEmbed data for %s", video_id)
            return None

        if author_url not in self._channel_ids:
            self._channel_ids[author_url] = await self._fetch_channel_id(author_url)

        return self._channel_ids[author_url]

    async def _fetch_channel_id(self, channel_url: str) -> Optional[str]:
        """
        Fetch a channel page and extract its channel ID.

        Args:
            channel_url (str): Channel URL, e.g. https://www.youtube.com/@handle.

        Returns:
            Optional[str]: The channel ID, or None if it could not be found.
        """
        try:
            resp = await query_endpoint(channel_url, max_retries=1)
        except requests.exceptions.RequestException as err:
            logger.warning("Failed to fetch channel page %s: %s", channel_url, err)
            return None

        for pattern in CHANNEL_ID_PATTERNS:
            match = pattern.search(resp.text)
            if match:
                return match.group(1)

        logger.warning("No channel ID found on channel page %s", channel_url)
        return None

    async def _fetch_feed(self, channel_id: str) -> Dict[str, datetime]:
        """
        Fetch a channel's RSS feed and cache the publish time of every entry.

        Args:
            channel_id (str): YouTube channel ID.

        Returns:
            Dict[str, datetime]: UTC publish times keyed by video ID.
        """
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        try:
            resp = await query_endpoint(url)
        except requests.exceptions.RequestException as err:
            logger.warning("Failed to fetch RSS feed for %s: %s", channel_id, err)
            return {}

        published_times: Dict[str, datetime] = {}
        for entry in bs(resp.text, "lxml-xml").find_all("entry"):
            video_id_tag = entry.find("yt:videoId")
            published_tag = entry.find("published")
            if not video_id_tag or not published_tag:
                continue

            try:
                published = self._as_utc(datetime.fromisoformat(published_tag.text))
            except ValueError:
                continue

            published_times[video_id_tag.text] = published
            await self._db.set_video_publish_time(video_id_tag.text, published.isoformat())

        return published_times

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        """
        Normalise a datetime to timezone-aware UTC so naive and aware values can be compared.

        Naive datetimes are assumed to already be in UTC.

        Args:
            dt (datetime): Datetime to normalise.

        Returns:
            datetime: Timezone-aware UTC datetime.
        """
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _plan_moves(current_order: List[int], desired_order: List[int]) -> List[Dict[str, str | int]]:
        """
        Build the minimum set of move operations required to turn current_order into desired_order.

        The longest subsequence of items already in the correct relative order is left in place
        and every other item is moved directly after its predecessor in the desired order.

        Args:
            current_order (List[int]): Playlist UIDs in their current order.
            desired_order (List[int]): The same UIDs in the desired order.

        Returns:
            List[Dict[str, str | int]]: Cytube moveMedia payloads, in the order they must be applied.
        """
        desired_positions = {uid: i for i, uid in enumerate(desired_order)}
        stable = QueueSorter._longest_increasing_subsequence([desired_positions[uid] for uid in current_order])

        moves: List[Dict[str, str | int]] = []
        for i, uid in enumerate(desired_order):
            if i in stable:
                continue
            moves.append({"from": uid, "after": desired_order[i - 1] if i else "prepend"})

        return moves

    @staticmethod
    def _longest_increasing_subsequence(values: List[int]) -> Set[int]:
        """
        Find a longest strictly increasing subsequence of distinct values.

        Args:
            values (List[int]): Distinct integers.

        Returns:
            Set[int]: The values making up the subsequence.
        """
        tail_values: List[int] = []
        tail_indexes: List[int] = []
        parents: List[int] = [-1] * len(values)

        for i, value in enumerate(values):
            pos = bisect_left(tail_values, value)
            if pos:
                parents[i] = tail_indexes[pos - 1]

            if pos == len(tail_values):
                tail_values.append(value)
                tail_indexes.append(i)
            else:
                tail_values[pos] = value
                tail_indexes[pos] = i

        subsequence: Set[int] = set()
        i = tail_indexes[-1] if tail_indexes else -1
        while i != -1:
            subsequence.add(values[i])
            i = parents[i]

        return subsequence
