import logging
from typing import Dict, List, Tuple

from contentbot.chatbot.async_socket import AsyncSocket

logger = logging.getLogger("contentbot")


class BaseProcessor:
    """Base class for all event processors."""

    def __init__(self, sio: AsyncSocket):
        """
        Initialise the processor with a socket interface.

        Args:
            sio (AsyncSocket): The socket used for sending events.
        """
        self._sio = sio

    @staticmethod
    def _parse_chat_event(data: Dict) -> Tuple[str, str, List[str]]:
        """
        Parse a chat event into its components: username, command, and arguments.

        The expected message format is a command beginning with the command
        symbol (e.g., '!add_channel foo bar').

        Args:
            data (Dict): Raw chat event payload containing at least 'username' and 'msg' fields.

        Returns:
            Tuple[str, str, List[str]]:
                - username: The user who sent the message.
                - command: The parsed command name (without the prefix).
                - args: A list of arguments following the command.
        """
        username = data.get("username", "")
        msg = data.get("msg", "")

        parts = msg.split()
        if not parts:
            return username, "", []

        command = parts[0].casefold()[1:]
        args = parts[1:]
        return username, command, args
