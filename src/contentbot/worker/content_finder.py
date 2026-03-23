import logging
from datetime import datetime
from typing import Dict, List

import requests
from bs4 import BeautifulSoup as bs
from bs4 import element

from contentbot.common.utils.api_query import query_endpoint

logger: logging.Logger = logging.getLogger("contentbot")


class ContentFinder:
    """Class for discovering new YouTube content."""

    async def find_content(self, channel: Dict) -> List[dict]:
        """
        Retrieve newly published videos for a channel.

        Args:
            channel (Dict): Channel metadata containing:
                - channel_id (str)
                - channel_name (str)
                - last_update (ISO8601 str)

        Returns:
            list[dict]: A list of dictionaries, each containing:
                {
                    "channel_id": str,
                    "datetime": str (ISO8601),
                    "video_id": str
                }
        """
        content: List[Dict] = []
        channel_id = channel["channel_id"]
        name = channel["channel_name"]
        dt = datetime.fromisoformat(channel["last_update"])
        logger.info(f"Getting content for: {name}")

        channel_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        try:
            resp = await query_endpoint(channel_url)
        except requests.exceptions.HTTPError:
            return content

        page = resp.text
        soup = bs(page, "lxml-xml")

        for entry in soup.find_all("entry"):
            published_str = self._get_text_from_tag(entry, "published")
            published = datetime.fromisoformat(published_str)

            if published < dt or published == dt:
                logger.info(f"No more new videos for {name}")
                break

            title = self._get_text_from_tag(entry, "title").lower()
            video_id = self._get_text_from_tag(entry, "yt:videoId")
            if not video_id:
                continue

            if not self._is_short(title, video_id):
                content.append(
                    {
                        "channel_id": channel_id,
                        "datetime": published_str,
                        "video_id": video_id,
                    }
                )

        return content

    def _get_text_from_tag(self, tag: element.Tag, target: str) -> str:
        """
        Extract the text content from a specific child tag.

        Args:
            tag (bs4.element.Tag): Parent tag to search within.
            target (str): Name of the child tag to extract.

        Returns:
            str: The text content of the child tag.

        Raises:
            ValueError: If the expected tag is not found.
        """
        child = tag.find(target)
        if child:
            return child.text

        raise ValueError(f"Expected tag <{target}> not found inside '{tag.name}'")

    def _is_short(self, title: str, id: str) -> bool:
        """
        Determine whether a video is a YouTube Shorts video.

        Args:
            title (str): Video title.
            id (str): YouTube video ID.

        Returns:
            bool: True if the video is a Short, otherwise False.
        """
        if "#shorts" in title:
            return True

        shorts_url = f"https://www.youtube.com/shorts/{id}"
        resp = requests.head(shorts_url, cookies={"CONSENT": "YES+1"}, timeout=60, allow_redirects=False)

        if resp.status_code == 303 or resp.status_code == 302:
            return False
        # Assume any 2XX successfully reached a shorts page
        elif 200 <= resp.status_code <= 299:
            return True
        else:
            logger.info(f"Received {resp.status_code=} from {shorts_url}")
            return True
