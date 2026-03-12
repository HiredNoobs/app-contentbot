import re
import time
from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup as bs


def query_endpoint(
    url: str,
    cookies: Optional[Dict] = None,
    max_retries: int = 10,
    backoff_factor: int = 2,
    max_backoff: int = 30,
) -> requests.Response:
    retries = 0
    current_backoff = 0

    while retries <= max_retries:
        try:
            resp = requests.get(url, cookies=cookies, timeout=60)
            resp.raise_for_status()
        except requests.exceptions.HTTPError:
            current_backoff = min(current_backoff + backoff_factor, max_backoff)
            time.sleep(current_backoff)

        retries += 1

    resp.raise_for_status()
    return resp


def get_data_from_pattern(
    url: str, pattern: str, cookies: Optional[Dict] = None, script_tag_name: str = "ytInitialData"
) -> Optional[str]:
    """
    query_endpoint wrapper that also extracts from a YouTube page based on a regex pattern.
    """
    try:
        resp = query_endpoint(url, cookies=cookies)
        soup = bs(resp.text, "lxml")
        script_tag = soup.find("script", string=re.compile(script_tag_name))  # type: ignore
        if not script_tag:
            return None

        match = re.search(pattern, script_tag.text)
        return match.group(1) if match else None
    except Exception:
        return None  # Should this be an exception...?
