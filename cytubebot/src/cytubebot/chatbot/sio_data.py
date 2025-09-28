import datetime
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class SIOData:
    """
    Non socket specific data class to share between classes more easily.
    """

    _current_backoff: int = int(os.environ.get("BASE_RETRY_BACKOFF", 2))
    _backoff_factor: int = int(os.environ.get("RETRY_BACKOFF_FACTOR", 2))
    _max_backoff: int = int(os.environ.get("MAX_RETRY_BACKOFF", 20))
    _retry_cooloff_period: int = int(os.environ.get("RETRY_COOLOFF_PERIOD", 10))
    _last_retry: datetime.datetime | None = None
    _lock: bool = False
    _current_media: Dict | None = None
    _users: Dict = field(default_factory=dict)
    _pending: List = field(default_factory=list)

    @property
    def lock(self) -> bool:
        return self._lock

    @lock.setter
    def lock(self, value: bool) -> None:
        self._lock = value

    @property
    def current_media(self) -> dict | None:
        return self._current_media

    @current_media.setter
    def current_media(self, value: Dict) -> None:
        self._current_media = value

    @property
    def users(self) -> dict:
        return self._users

    @users.setter
    def users(self, value: Dict) -> None:
        self._users = value

    @property
    def current_backoff(self) -> int:
        """Return the current backoff delay in seconds."""
        return self._current_backoff

    @property
    def backoff_factor(self) -> int:
        """Return the multiplier used to increase the backoff delay."""
        return self._backoff_factor

    @property
    def max_backoff(self) -> int:
        """Return the maximum allowed backoff delay in seconds."""
        return self._max_backoff

    @property
    def last_retry(self) -> datetime.datetime | None:
        """Return the timestamp of the last retry attempt."""
        return self._last_retry

    @last_retry.setter
    def last_retry(self, value: datetime.datetime) -> None:
        self._last_retry = value

    @property
    def pending(self) -> List:
        return self._pending

    def add_pending(self, id: str) -> None:
        self._pending.append(id)

    def remove_pending(self, id: str) -> None:
        # It's possible that someone else updates the queue
        # while the bot is running so we could reasonably
        # get an ID that isn't in pending - this isn't a big deal.
        try:
            self._pending.remove(id)
        except ValueError:
            pass

    def can_retry(self) -> bool:
        """
        Check if sufficient time has passed since the last retry based on the current backoff delay.
        If no previous retry has been attempted (i.e., _last_retry is None), returns True.
        """
        if self._last_retry is None:
            return True
        elapsed = (datetime.datetime.now() - self._last_retry).total_seconds()
        return elapsed >= self._current_backoff

    def reset_backoff(self) -> None:
        """
        Reduce the current_backoff by the backoff_factor if the last_retry wasn't within
        the retry_cooloff_period.
        """
        logger.debug("Attempting to reset backoff...")
        if self._last_retry is not None:
            # If the latest retry was recent then we won't reset
            elapsed = (datetime.datetime.now() - self._last_retry).total_seconds()
            logger.debug(f"{elapsed} seconds since {self._last_retry=}")
            if elapsed < self._retry_cooloff_period:
                logger.debug(
                    f"Last retry was too soon ({elapsed} seconds ago), not resetting backoff."
                )
                return

        self._current_backoff = max(
            self._current_backoff - self._backoff_factor,
            int(os.environ.get("BASE_RETRY_BACKOFF", 2)),
        )
        logger.debug(f"Backoff reduced to {self._current_backoff}")

    def increase_backoff(self) -> None:
        """
        Increment the current_backoff.
        """
        self._current_backoff = min(
            self._current_backoff + self._backoff_factor, self._max_backoff
        )
        logger.debug(f"Current backoff increased to {self._current_backoff}")

    def add_or_update_user(self, user_id: str, user_info: Dict) -> None:
        """
        Add a new user or update an existing user's information in the users dictionary.

        Parameters:
            user_id (str): A unique identifier for the user.
            user_info (dict): A dictionary of user-related information.
        """
        self._users[user_id] = user_info

    def remove_user(self, user_id: str) -> None:
        """
        Remove a user from the users dictionary by their identifier.

        Parameters:
            user_id (str): The identifier of the user to be removed.
        """
        self._users.pop(user_id, None)
