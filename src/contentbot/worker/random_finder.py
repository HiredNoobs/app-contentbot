import json
import logging
import random
import string
from typing import Dict, Optional

from contentbot.common.utils.api_query import query_endpoint

logger: logging.Logger = logging.getLogger("contentbot")


class RandomFinder:
    """Class for discovering random content from YouTube."""

    def __init__(self, dictonary_file: Optional[str]):
        """
        Initialise the random finder.

        Args:
            dictonary_file (Optional[str]): Path to a dictionary file containing
                one word per line. If provided, random words may be selected
                from this file instead of generating random strings.
        """
        self._dictonary_file = dictonary_file

    def find_random(self, size: int, use_dict: bool) -> Dict[str, str]:
        """
        Generate a random YouTube search query and return a random video ID
        from the results.

        Args:
            size (int): Length of the random string if not using a dictionary.
            use_dict (bool): Whether to use the dictionary file for random words.

        Returns:
            Dict[str, str]: A dictionary containing:
                {
                    "video_id": "<YouTube video ID>"
                }
            Returns an empty dict if no videos are found.
        """
        if 0 > size > 10:
            size = 3

        if use_dict and self._dictonary_file:
            with open(self._dictonary_file) as file:
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
        vids = vids["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]["sectionListRenderer"]["contents"][
            0
        ]["itemSectionRenderer"]["contents"]
        vids = [x for x in vids if "videoRenderer" in x]

        try:
            rand_num = random.randrange(len(vids))
        except ValueError:
            return {}

        return {"video_id": vids[rand_num]["videoRenderer"]["videoId"]}

    def _rand_str(self, size: int) -> str:
        """
        Generate a random alphanumeric string.

        Based on:
            https://stackoverflow.com/a/2257449
            https://stackoverflow.com/a/23728630

        Args:
            size (int): Length of the string to generate.

        Returns:
            str: A random lowercase alphanumeric string.
        """
        chars = string.ascii_lowercase + string.digits
        return "".join(random.SystemRandom().choice(chars) for _ in range(size))
