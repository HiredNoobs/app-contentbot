import logging
from datetime import datetime
from typing import Dict

import requests
from bs4 import BeautifulSoup as bs
from bs4 import element

from contentbot.utils.api_query import query_endpoint

logger = logging.getLogger(__name__)


class ContentFinder:
    def find_content(self, channel: Dict) -> list[dict]:
        """
        returns:
            A list of dicts, each video comes in a dict.
            Comes in the form:
            [
                {
                    "channel_id": "abc123",
                    "datetime": datetime.datetime(2025, 1, 1, 0, 5, 23),
                    "video_id": "afghtbx36"
                }
            ]
        """
        content = []
        channel_id = channel["channel_id"]
        name = channel["channel_name"]
        dt = datetime.fromisoformat(channel["last_update"])
        logger.info(f"Getting content for: {name}")

        channel_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        resp = query_endpoint(channel_url)
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
                        "datetime": published,
                        "video_id": video_id,
                    }
                )

        return content

    def _get_text_from_tag(self, tag: element.Tag, target: str) -> str:
        child = tag.find(target)
        if child:
            return child.text

        raise ValueError(f"Expected tag <{target}> not found inside '{tag.name}'")

    def _is_short(self, title: str, id: str) -> bool:
        """
        Returns True if video id is a YT Shorts video.
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
