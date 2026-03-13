import logging
from typing import Dict, List

from contentbot.chatbot.async_socket import AsyncSocket

logger = logging.getLogger("contentbot")


class BaseProcessor:
    """
    Base class for all event processors.

    Provides shared socket reference, logging, and optional helpers.
    """

    def __init__(self, sio: AsyncSocket):
        self._sio = sio

    @staticmethod
    def _parse_chat_event(data: Dict) -> tuple[str, str, List[str]]:
        """
        Extracts the user, command, and args from a chat event.

        Example: '!add_channel foo bar' -> ('add_channel', ['foo', 'bar'])
        """
        username = data.get("username", "")
        msg = data.get("msg", "")

        parts = msg.split()
        if not parts:
            return username, "", []

        command = parts[0].casefold()[1:]
        args = parts[1:]
        return username, command, args
