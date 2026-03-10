import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

from aio_pika import IncomingMessage

logger = logging.getLogger("contentbot")


@dataclass
class SIOData:
    _current_media: Dict | None = None
    _users: Dict[str, int] = field(default_factory=dict)
    _pending: Dict[str, IncomingMessage] = field(default_factory=dict)

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

    def get_pending(self, video_id: str) -> Optional[IncomingMessage]:
        """
        Returns the IncomingMessage object from RabbitMQ if
        the video is pending, else returns None.
        """
        if video_id in self._pending:
            return self._pending[video_id]
        else:
            return None

    def add_pending(self, video_id: str, msg: IncomingMessage) -> None:
        if video_id not in self._pending:
            self._pending[video_id] = msg
        else:
            # TODO: Add a custom exception for this
            raise ValueError(f"{video_id} already pending")

    def remove_pending(self, video_id: str) -> None:
        try:
            del self._pending[video_id]
        except ValueError:
            pass
