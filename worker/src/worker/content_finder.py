import logging
from datetime import datetime
from operator import itemgetter

import requests
from bs4 import BeautifulSoup as bs

from worker.database_wrapper import DatabaseWrapper
from worker.utils import query_endpoint

logger = logging.getLogger(__name__)


class ContentFinder:
    def __init__(self) -> None:
        self._db = DatabaseWrapper("", 0)

    def find_content(self, tag: str | None = None) -> list[dict]:
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
        channels = self._db.get_channels(tag)

        for row in channels:
            logger.debug(f"{row=}")
            channel_id = row["channel_id"]
            name = row["channel_name"]
            dt = datetime.fromisoformat(row["last_update"])
            logger.info(f"Getting content for: {name}")

            channel = (
                f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            )
            resp = query_endpoint(channel)
            page = resp.text
            soup = bs(page, "lxml")

            for item in soup.find_all("entry"):
                published = item.find_all("published")[0].text
                published = datetime.fromisoformat(published)

                if published < dt or published == dt:
                    logger.info(f"No more new videos for {name}")
                    break

                title = item.find_all("title")[0].text.casefold()
                video_id = item.find_all("yt:videoid")[0].text

                if not self._is_short(title, video_id):
                    c = {
                        "channel_id": channel_id,
                        "datetime": published,
                        "video_id": video_id,
                    }
                    content.append(c)

        content = sorted(content, key=itemgetter("datetime"))

        return content

    def _is_short(self, title: str, id: str) -> bool:
        """
        Returns True if video id is a YT Shorts video.
        """
        if "#shorts" in title:
            return True

        shorts_url = f"https://www.youtube.com/shorts/{id}"
        resp = requests.head(
            shorts_url, cookies={"CONSENT": "YES+1"}, timeout=60, allow_redirects=False
        )
        if resp.status_code == 303 or resp.status_code == 302:
            return False
        # Assume any 2XX successfully reached a shorts page
        elif 200 <= resp.status_code <= 299:
            return True
        else:
            logger.info(f"Received {resp.status_code=} from {shorts_url}")
            return True
