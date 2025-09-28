import json
import logging
import random
import string
from typing import Tuple

from worker.utils import query_endpoint

logger = logging.getLogger(__name__)


class RandomFinder:
    def find_random(
        self, size: int = 3, use_dict=False
    ) -> Tuple[str | None, str | None]:
        if 0 > size > 10:
            size = 3

        if use_dict:
            # This file is downloaded by the Dockerfile
            with open("/app/cytubebot/randomvideo/eng_dict.txt") as file:
                lines = file.read().splitlines()
                rand_str = random.choice(lines)
        else:
            rand_str = self._rand_str(size)

        logger.info(f"Finding random with {rand_str}")
        url = f"https://www.youtube.com/results?search_query={rand_str}"
        resp = query_endpoint(url)

        # Thankfully the video data is stored as json in script tags
        # We just have to pull the json out...
        start = "ytInitialData = "
        end = ";</script>"
        vids = json.loads(resp.text.split(start)[1].split(end)[0])
        vids = vids["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"][
            "sectionListRenderer"
        ]["contents"][0]["itemSectionRenderer"]["contents"]
        vids = [x for x in vids if "videoRenderer" in x]

        try:
            rand_num = random.randrange(len(vids))
        except ValueError:
            return None, None

        return vids[rand_num]["videoRenderer"]["videoId"], rand_str

    def _rand_str(self, size: int) -> str:
        """
        Great func found here: https://stackoverflow.com/a/2257449 &
        https://stackoverflow.com/a/23728630
        """
        chars = string.ascii_lowercase + string.digits
        return "".join(random.SystemRandom().choice(chars) for _ in range(size))
