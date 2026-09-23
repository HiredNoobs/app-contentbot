import re
from typing import Dict, Optional

from bs4 import BeautifulSoup as bs

from contentbot.common.utils.api_query import query_endpoint


def clean_yt_string(channel_name_or_url: str) -> str:
    """
    Clean a YouTube channel name or URL and extract the channel identifier.

    This function:
        - Removes HTML anchor tags
        - Strips common YouTube path suffixes (e.g., /videos, /about)
        - Removes trailing slashes
        - Removes leading '@' symbols
        - Extracts the final path component if a URL is provided

    Args:
        channel_name_or_url (str): Raw channel name or URL.

    Returns:
        str: A cleaned channel identifier suitable for lookup.
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


async def get_channel_id_from_name(channel_name: str) -> Optional[str]:
    """
    Resolve a YouTube channel name or URL to its channel ID.

    This function attempts multiple YouTube URL formats and extracts the
    channel ID using regex patterns applied to the page's script tags.

    Args:
        channel_name (str): Raw channel name or URL.

    Returns:
        Optional[str]: The resolved channel ID, or None if not found.
    """
    channel_name = clean_yt_string(channel_name)

    cookies = {"CONSENT": "YES+1"}
    candidate_urls = {
        f"https://www.youtube.com/@{channel_name}": r'.*"browse_id","value":"(.*?)"',
        f"https://www.youtube.com/c/{channel_name}": r'.*"browse_id","value":"(.*?)"',
        f"https://www.youtube.com/channel/{channel_name}": r'.*"channelMetadataRenderer":{"title":"(.*?)"',
    }

    for url, pattern in candidate_urls.items():
        channel_id = await get_data_from_pattern(url, pattern, cookies=cookies)
        if channel_id:
            return channel_id
    return None


async def get_data_from_pattern(
    url: str, pattern: str, cookies: Optional[Dict] = None, script_tag_name: str = "ytInitialData"
) -> Optional[str]:
    """
    Fetch a YouTube page and extract data using a regex pattern applied to a script tag.

    This is a convenience wrapper around `query_endpoint` that:
        - Retrieves the page HTML
        - Locates a <script> tag containing a specific identifier
        - Applies a regex pattern to extract a desired value

    Args:
        url (str): The URL to fetch.
        pattern (str): Regex pattern used to extract data.
        cookies (Optional[Dict]): Optional cookies to include in the request.
        script_tag_name (str): Name or identifier used to locate the correct script tag.

    Returns:
        Optional[str]: The extracted value, or None if not found or on error.
    """
    try:
        resp = await query_endpoint(url, cookies=cookies)
        soup = bs(resp.text, "lxml")
        script_tag = soup.find("script", string=re.compile(script_tag_name))  # type: ignore
        if not script_tag:
            return None

        match = re.search(pattern, script_tag.text)
        return match.group(1) if match else None
    except Exception:
        return None
