import logging
import re
from bisect import bisect_left
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import requests

from contentbot.chatbot.db.async_redis_db import AsyncRedisDB
from contentbot.common.utils.api_query import query_endpoint

logger: logging.Logger = logging.getLogger("contentbot")

# Ordered by preference; YouTube usually includes a full ISO8601 timestamp in
# publishDate, but older pages may only include the date.
PUBLISH_TIME_PATTERNS = (
    re.compile(r'"publishDate":"([^"]+)"'),
    re.compile(r'"uploadDate":"([^"]+)"'),
    re.compile(r'itemprop="datePublished" content="([^"]+)"'),
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

    async def sort_queue(self, playlist: List[Dict]) -> Dict:
        """
        Plan the moves needed to sort temporary items after the permanent items by publish time.

        Permanent items keep their current relative order. Temporary items with an unknown
        publish time are placed at the end, keeping their current relative order.

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
                    "unknown": int count of temporary items with no known publish time
                }
        """
        playlist = [item for item in playlist if item.get("uid") is not None]
        permanent_items = [item for item in playlist if not item.get("temp")]
        temp_items = [item for item in playlist if item.get("temp")]

        keyed_temp_items = []
        for position, item in enumerate(temp_items):
            published = await self._get_publish_time(item)
            keyed_temp_items.append(
                ((published is None, published or datetime.min.replace(tzinfo=timezone.utc), position), item)
            )
        keyed_temp_items.sort(key=lambda pair: pair[0])

        current_order = [item["uid"] for item in playlist]
        desired_order = [item["uid"] for item in permanent_items] + [item["uid"] for _, item in keyed_temp_items]

        return {
            "type": "sort_queue",
            "moves": self._plan_moves(current_order, desired_order),
            "unknown": sum(1 for key, _ in keyed_temp_items if key[0]),
        }

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

        published = await self._fetch_publish_time(video_id)
        if published:
            await self._db.set_video_publish_time(video_id, published.isoformat())

        return published

    async def _fetch_publish_time(self, video_id: str) -> Optional[datetime]:
        """
        Fetch the publish time for a YouTube video from its watch page.

        A full timestamp is preferred; a date-only value is used as a fallback.

        Args:
            video_id (str): YouTube video ID.

        Returns:
            Optional[datetime]: UTC publish time, or None if it could not be resolved.
        """
        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            resp = await query_endpoint(url, cookies={"CONSENT": "YES+1"})
        except requests.exceptions.RequestException:
            logger.warning("Failed to fetch watch page for %s", video_id)
            return None

        fallback: Optional[datetime] = None
        for pattern in PUBLISH_TIME_PATTERNS:
            match = pattern.search(resp.text)
            if not match:
                continue

            raw = match.group(1)
            try:
                published = self._as_utc(datetime.fromisoformat(raw))
            except ValueError:
                continue

            if "T" in raw:
                return published
            fallback = fallback or published

        return fallback

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
