import time
from typing import Dict, Optional

import requests


def query_endpoint(
    url: str,
    cookies: Optional[Dict] = None,
    max_retries: int = 10,
    backoff_factor: int = 2,
    max_backoff: int = 30,
) -> requests.Response:
    """
    Perform a GET request with retry and exponential backoff.

    Args:
        url (str): The URL to request.
        cookies (Optional[Dict]): Optional cookies to include in the request.
        max_retries (int): Maximum number of retry attempts.
        backoff_factor (int): Amount to increase the backoff delay per retry.
        max_backoff (int): Maximum allowed backoff delay in seconds.

    Returns:
        requests.Response: The successful HTTP response.

    Raises:
        requests.exceptions.HTTPError: If all retries fail or the final
            response still contains an HTTP error status.
    """
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
