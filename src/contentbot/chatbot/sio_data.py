import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger("contentbot")


@dataclass
class SIOData:
    """
    Shared state container for the async ChatBot.
    """

    # Backoff settings
    _current_backoff: int = int(os.environ.get("BASE_RETRY_BACKOFF", 2))
    _backoff_factor: int = int(os.environ.get("RETRY_BACKOFF_FACTOR", 2))
    _max_backoff: int = int(os.environ.get("MAX_RETRY_BACKOFF", 20))
    _retry_cooloff_period: int = int(os.environ.get("RETRY_COOLOFF_PERIOD", 10))

    # Retry timestamp
    _last_retry: float | None = None

    # Shared state
    _current_media: Dict | None = None
    _users: Dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    @property
    def current_media(self) -> dict | None:
        return self._current_media

    @current_media.setter
    def current_media(self, value: Dict) -> None:
        self._current_media = value

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    @property
    def users(self) -> dict:
        return self._users

    def add_or_update_user(self, username: str, rank: int) -> None:
        self._users[username] = rank

    def remove_user(self, username: str) -> None:
        self._users.pop(username, None)

    # ------------------------------------------------------------------
    # Pending queue
    # ------------------------------------------------------------------

    @property
    def pending(self) -> List[str]:
        return self._pending

    def add_pending(self, video_id: str) -> None:
        self._pending.append(video_id)

    def remove_pending(self, video_id: str) -> None:
        try:
            self._pending.remove(video_id)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Backoff logic
    # ------------------------------------------------------------------

    def can_retry(self) -> bool:
        """
        Check if enough time has passed since last retry.
        Uses monotonic time for async safety.
        """
        now = asyncio.get_event_loop().time()

        if self._last_retry is None:
            return True

        elapsed = now - self._last_retry
        return elapsed >= self._current_backoff

    def reset_backoff(self) -> None:
        """
        Reduce backoff if enough time has passed.
        """
        now = asyncio.get_event_loop().time()

        if self._last_retry is not None:
            elapsed = now - self._last_retry
            if elapsed < self._retry_cooloff_period:
                return

        base = int(os.environ.get("BASE_RETRY_BACKOFF", 2))
        self._current_backoff = max(self._current_backoff - self._backoff_factor, base)

    def increase_backoff(self) -> None:
        """
        Increase backoff up to max.
        """
        self._current_backoff = min(
            self._current_backoff + self._backoff_factor,
            self._max_backoff,
        )

    def mark_retry(self) -> None:
        """
        Record the time of the last retry.
        """
        self._last_retry = asyncio.get_event_loop().time()
