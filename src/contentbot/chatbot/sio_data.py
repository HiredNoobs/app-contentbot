import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from aio_pika import IncomingMessage

from contentbot.exceptions import QueueError

logger = logging.getLogger("contentbot")


@dataclass
class SIOData:
    """
    Container for all stateful data used by the AsyncSocket and event processors.

    It acts as a shared state object across all processors.
    """

    _user: Optional[str] = None
    _current_media: Optional[Dict] = None
    _users: Dict[str, int] = field(default_factory=dict)
    _pending: Dict[str, IncomingMessage] = field(default_factory=dict)
    _last_content_pull: Dict[str, datetime] = field(default_factory=dict)

    _logged_in: bool = False
    _last_login: Optional[datetime] = None

    _channel_permissions: Dict[str, int] = field(default_factory=dict)
    _admin_permission_level = 3
    _moderator_permission_level = 2

    # These should probably come from the config file
    _base_retry_backoff: int = int(os.environ.get("BASE_RETRY_BACKOFF", 0))
    _current_backoff: int = int(os.environ.get("BASE_RETRY_BACKOFF", 0))
    _backoff_factor: int = int(os.environ.get("RETRY_BACKOFF_FACTOR", 2))
    _max_backoff: int = int(os.environ.get("MAX_RETRY_BACKOFF", 20))
    _retry_cooloff_period: int = int(os.environ.get("RETRY_COOLOFF_PERIOD", 10))
    _last_retry: datetime = datetime.now()

    def reset_data(self) -> None:
        """
        Reset user and permission state.

        This is typically called on disconnect to ensure that stale
        server-provided state does not persist across reconnections.
        """
        self._users = {}
        self._logged_in = False
        self._channel_permissions = {}

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    @property
    def user(self) -> Optional[str]:
        """Return the bot's username."""
        return self._user

    @user.setter
    def user(self, value: str) -> None:
        """
        Set the bot's username.

        Args:
            value (str): The bot's username.
        """
        self._user = value

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    @property
    def current_media(self) -> Optional[dict]:
        """Return the currently playing media metadata."""
        return self._current_media

    @current_media.setter
    def current_media(self, value: Dict) -> None:
        """
        Set the currently playing media metadata.

        Args:
            value (Dict): Media metadata dictionary.
        """
        self._current_media = value

    def update_current_time(self, value: float) -> None:
        """
        Update the playback timestamp of the current media.

        Args:
            value (float): New playback time in seconds.
        """
        if self._current_media:
            self._current_media["currentTime"] = value

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    @property
    def users(self) -> dict:
        """Return the mapping of usernames to their Cytube ranks."""
        return self._users

    def add_or_update_user(self, username: str, rank: int) -> None:
        """
        Add a new user or update an existing user's rank.

        Args:
            username (str): Username.
            rank (int): Cytube rank value.
        """
        self._users[username] = rank

    def remove_user(self, username: str) -> None:
        """
        Remove a user from the local user list.

        Args:
            username (str): Username to remove.
        """
        self._users.pop(username, None)

    def has_permission(self, username: str, permission: str) -> bool:
        """
        Check whether a user has a specific permission.

        Args:
            username (str): Username to check.
            permission (str): Permission key from channel permissions.

        Returns:
            bool: True if the user has the required permission level.
        """
        return self._users.get(username, 0) >= self._channel_permissions.get(permission, 100)

    def is_user_admin(self, username: str) -> bool:
        """Return True if the user has admin-level permissions."""
        return self.users.get(username, 0) >= self._admin_permission_level

    def is_user_moderator(self, username: str) -> bool:
        """Return True if the user has moderator-level permissions."""
        return self.users.get(username, 0) >= self._moderator_permission_level

    def only_remaining_user(self) -> bool:
        """
        Check whether the bot is the only user currently in the channel.

        Returns:
            bool: True if only the bot remains, otherwise False.
        """
        if not self._logged_in:
            return False
        users = list(self._users.keys())
        return len(users) == 1 and users[0] == self._user

    # ------------------------------------------------------------------
    # Pending queue
    # ------------------------------------------------------------------

    def get_pending(self, video_id: str) -> Optional[IncomingMessage]:
        """
        Retrieve a pending RabbitMQ message for a given video ID.

        Args:
            video_id (str): Video ID associated with the pending message.

        Returns:
            Optional[IncomingMessage]: The message if pending, else None.
        """
        return self._pending.get(video_id)

    def add_pending(self, video_id: str, msg: IncomingMessage) -> None:
        """
        Add a pending RabbitMQ message for a video.

        Args:
            video_id (str): Video ID.
            msg (IncomingMessage): RabbitMQ message.

        Raises:
            QueueError: If the video already has a pending message.
        """
        if video_id not in self._pending:
            self._pending[video_id] = msg
        else:
            raise QueueError(f"{video_id} already pending")

    def remove_pending(self, video_id: str) -> None:
        """
        Remove a pending RabbitMQ message for a video.

        Args:
            video_id (str): Video ID.
        """
        try:
            del self._pending[video_id]
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def get_last_content_pull(self, tag: Optional[str] = None) -> Optional[datetime]:
        """
        Get the timestamp of the last content pull for a given tag.

        Args:
            tag (Optional[str]): Content tag, or None for global pulls.

        Returns:
            Optional[datetime]: Timestamp of last pull, or None.
        """
        if tag is None:
            tag = "all"
        return self._last_content_pull.get(tag)

    def update_last_content_pull(self, new_dt: datetime, tag: Optional[str] = None) -> None:
        """
        Update the timestamp of the last content pull for a tag.

        Args:
            new_dt (datetime): Timestamp to record.
            tag (Optional[str]): Content tag, or None for global pulls.
        """
        if tag is None:
            tag = "all"
        self._last_content_pull[tag] = new_dt

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    @property
    def channel_permissions(self) -> Dict[str, int]:
        """Return the channel permission mapping."""
        return self._channel_permissions

    @channel_permissions.setter
    def channel_permissions(self, permissions: Dict[str, int]) -> None:
        """
        Set the channel permission mapping.

        Args:
            permissions (Dict[str, int]): Mapping of permission keys to rank levels.
        """
        self._channel_permissions = permissions

    # ------------------------------------------------------------------
    # Logged in
    # ------------------------------------------------------------------

    @property
    def logged_in(self) -> bool:
        """Return True if the bot is logged in."""
        return self._logged_in

    @logged_in.setter
    def logged_in(self, value: bool) -> None:
        """
        Set the bot's login state.

        Args:
            value (bool): Login state.
        """
        self._logged_in = value

    @property
    def last_login(self) -> Optional[datetime]:
        """Return the timestamp of the most recent successful login."""
        return self._last_login

    @last_login.setter
    def last_login(self, value: datetime) -> None:
        """
        Set the timestamp of the most recent successful login.

        Args:
            value (datetime): Login timestamp.
        """
        self._last_login = value

    # ------------------------------------------------------------------
    # Backoff
    # ------------------------------------------------------------------

    @property
    def current_backoff(self) -> int:
        """Return the current backoff delay in seconds."""
        return self._current_backoff

    def increase_backoff(self) -> None:
        """Increment the current_backoff value."""
        self._last_retry = datetime.now()
        self._current_backoff = min(self._current_backoff + self._backoff_factor, self._max_backoff)
        logger.debug("Current backoff increased to %s.", self._current_backoff)

    def decrease_backoff(self) -> None:
        """
        Decrease the current_backoff value.

        The backoff value is reduced by the configured backoff factor,
        but only if enough time has passed since the last backoff adjustment.
        The backoff will not drop below the base retry backoff value.
        """
        logger.debug("Attempting to decrease backoff...")

        elapsed = (datetime.now() - self._last_retry).total_seconds()
        logger.debug("%s seconds since last retry (%s)", elapsed, self._last_retry)
        if elapsed < self._retry_cooloff_period:
            logger.debug("Last retry was too soon (%s seconds ago), not resetting backoff.", elapsed)
            return

        self._current_backoff = max(self._current_backoff - self._backoff_factor, self._base_retry_backoff)
        self._last_retry = datetime.now()
        logger.debug("Backoff reduced to %s", self._current_backoff)
