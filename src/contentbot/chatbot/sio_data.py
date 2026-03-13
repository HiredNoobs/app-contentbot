import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from aio_pika import IncomingMessage

from contentbot.exceptions import QueueError

logger = logging.getLogger("contentbot")


@dataclass
class SIOData:
    _user: Optional[str] = None
    _current_media: Optional[Dict] = None
    _users: Dict[str, int] = field(default_factory=dict)
    _pending: Dict[str, IncomingMessage] = field(default_factory=dict)
    _last_content_pull: Dict[str, datetime] = field(default_factory=dict)
    _logged_in: bool = False

    # Any checks for Cytube permissions should use the _channel_perms
    # but interally the bot reuses the admin/mod levels for some commands.
    _channel_permissions: Dict[str, int] = field(default_factory=dict)
    _admin_permission_level = 3
    _moderator_permission_level = 2

    # This is for handling disconnects.
    # Mainly we're concerned _users will contain the bot
    # before it's properly logged in... but we get a lot
    # of the data again on login so we may as well clear
    # anything that is collected from the server.
    def reset_data(self) -> None:
        self._users = {}
        self._channel_permissions = {}

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    @property
    def user(self) -> Optional[str]:
        return self._user

    @user.setter
    def user(self, value: str) -> None:
        self._user = value

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    @property
    def current_media(self) -> dict | None:
        return self._current_media

    @current_media.setter
    def current_media(self, value: Dict) -> None:
        self._current_media = value

    def update_current_time(self, value: float) -> None:
        if self._current_media:
            self._current_media["currentTime"] = value

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

    def has_permission(self, username: str, permission: str) -> bool:
        """
        Checks if the user has access to a certain permission.

        If the users rank is missing and/or the channel permissions are missing,
        this will always return False to avoid getting the bot kicked.
        """
        return self._users.get(username, 0) >= self._channel_permissions.get(permission, 100)

    def is_user_admin(self, username: str) -> bool:
        return self.users.get(username, 0) >= self._admin_permission_level

    def is_user_moderator(self, username: str) -> bool:
        return self.users.get(username, 0) >= self._moderator_permission_level

    def only_remaining_user(self) -> bool:
        """
        Checks if the bot is the only logged in user in the channel.
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
        Returns the IncomingMessage object from RabbitMQ if
        the video is pending, else returns None.
        """
        return self._pending.get(video_id)

    def add_pending(self, video_id: str, msg: IncomingMessage) -> None:
        if video_id not in self._pending:
            self._pending[video_id] = msg
        else:
            raise QueueError(f"{video_id} already pending")

    def remove_pending(self, video_id: str) -> None:
        try:
            del self._pending[video_id]
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def get_last_content_pull(self, tag: Optional[str]) -> Optional[datetime]:
        if tag is None:
            tag = "all"
        return self._last_content_pull.get(tag)

    def update_last_content_pull(self, tag: Optional[str], new_dt: datetime) -> None:
        if tag is None:
            tag = "all"
        self._last_content_pull[tag] = new_dt

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    @property
    def channel_permissions(self) -> Dict[str, int]:
        return self._channel_permissions

    @channel_permissions.setter
    def channel_permissions(self, permissions: Dict[str, int]) -> None:
        self._channel_permissions = permissions

    # ------------------------------------------------------------------
    # Logged in
    # ------------------------------------------------------------------

    @property
    def logged_in(self) -> bool:
        return self._logged_in

    @logged_in.setter
    def logged_in(self, value: bool) -> None:
        self._logged_in = value
