import re
from typing import Dict, Optional

from bs4 import BeautifulSoup as bs

from contentbot.common.utils.api_query import query_endpoint


def clean_yt_string(channel_name_or_url: str) -> str:
    """
    Takes a YouTube channel name or full URL and tries to clean
    the string to get just the channel name.
    """
    if "</a>" in channel_name_or_url:
        cleaned_name = re.search(r".*>(.*?)</a>", channel_name_or_url)
        if cleaned_name:
            channel_name_or_url = cleaned_name.group(1)

    channel_name_or_url = channel_name_or_url.strip()

    channel_name_or_url = channel_name_or_url.replace("/featured", "")
    channel_name_or_url = channel_name_or_url.replace("/videos", "")
    channel_name_or_url = channel_name_or_url.replace("/playlists", "")
    channel_name_or_url = channel_name_or_url.replace("/community", "")
    channel_name_or_url = channel_name_or_url.replace("/channels", "")
    channel_name_or_url = channel_name_or_url.replace("/about", "")

    if channel_name_or_url[-1:] == "/":
        channel_name_or_url = channel_name_or_url[:-1]

    if channel_name_or_url[0] == "@":
        channel_name_or_url = channel_name_or_url[1:]

    channel_name_or_url = channel_name_or_url.rsplit("/", 1)[-1]

    return channel_name_or_url


def get_channel_id_from_name(channel_name: str) -> Optional[str]:
    channel_name = clean_yt_string(channel_name)

    cookies = {"CONSENT": "YES+1"}
    candidate_urls = {
        f"https://www.youtube.com/@{channel_name}": r'.*"browse_id","value":"(.*?)"',
        f"https://www.youtube.com/c/{channel_name}": r'.*"browse_id","value":"(.*?)"',
        f"https://www.youtube.com/channel/{channel_name}": r'.*"channelMetadataRenderer":{"title":"(.*?)"',
    }

    for url, pattern in candidate_urls.items():
        channel_id = get_data_from_pattern(url, pattern, cookies=cookies)
        if channel_id:
            return channel_id
    return None


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
