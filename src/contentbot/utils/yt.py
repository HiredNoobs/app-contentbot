import re


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
