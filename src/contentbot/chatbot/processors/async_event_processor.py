import logging
from typing import Dict, List

from contentbot.chatbot.commands import Commands
from contentbot.chatbot.processors.base_processor import BaseProcessor
from contentbot.exceptions import AuthenticationError

logger: logging.Logger = logging.getLogger("contentbot")


class AsyncEventProcessor(BaseProcessor):
    """Generic event processor responsible for handling core Cytube events."""

    # -----------------------------------------------------
    # Event handlers
    # -----------------------------------------------------

    async def handle_connect(self):
        """
        Handle the initial connection event.

        Joins the configured channel immediately after connecting.
        """
        await self._sio.join_channel()

    async def handle_channel_opts(self):
        """
        Handle channel options being received from the server.

        Triggers the login process.
        """
        await self._sio.login()

    def handle_disconnect(self):
        """
        Handle a disconnection event.

        Clears all locally stored state where required.
        """
        self._sio.data.reset_data()

    async def handle_chat_message(self, data: Dict):
        """
        Handle an incoming chat message.

        Args:
            data (Dict): Raw chat event payload.
        """
        username, command, args = self._parse_chat_event(data)
        await self._handle_command(username, command, args)

    async def handle_user_join(self, data: Dict) -> None:
        """
        Handle a user joining the channel.

        Args:
            data (Dict): Contains the user's name and rank.
        """
        user = data["name"]
        rank = data["rank"]
        self._sio.data.add_or_update_user(user, rank)

    async def handle_user_leave(self, data: Dict) -> None:
        """
        Handle a user leaving the channel.

        Args:
            data (Dict): Contains the user's name.
        """
        user = data["name"]
        self._sio.data.remove_user(user)

        if self._sio.data.only_remaining_user():
            await self._sio.become_leader()

    async def handle_successful_login(self, _: Dict) -> None:
        """
        Handle a successful login event.

        Marks the bot as logged in and notifies the server that the player is ready.
        """
        logger.info("Login successful.")
        self._sio.data.logged_in = True

        await self._sio.emit("playerReady")
        await self._sio.emit("initUserPLCallbacks")

    async def handle_failed_login(self, data: Dict) -> None:
        """
        Handle a failed login attempt.

        Args:
            data (Dict): Contains the error message from the server.

        Raises:
            AuthenticationError: If the login cannot be recovered.
        """
        logger.error("Login failed.")

        self._sio.data.logged_in = False
        error = data["error"]

        if error.lower() == "session expired":
            logger.info("Session expired.")
            await self._sio.login()
        else:
            raise AuthenticationError(f"Login failed due to {error}")

    def handle_set_permissions(self, data: Dict) -> None:
        """
        Handle updated channel permissions from the server.

        Args:
            data (Dict): Permission mapping.
        """
        self._sio.data.channel_permissions = data

    async def handle_user_list(self, data: Dict) -> None:
        """
        Handle a full user list update from the server.

        Syncs local user state with the server's authoritative list.

        Args:
            data (Dict): List of user metadata dictionaries.
        """
        server_users = set()
        for userdata in data:
            user = userdata["name"]
            rank = userdata["rank"]
            server_users.add(user)
            self._sio.data.add_or_update_user(user, rank)

        local_users = set(self._sio.data.users.keys())
        remove_users = local_users - server_users
        logger.debug("Removing %s from SIOData.", remove_users)

        for user in remove_users:
            self._sio.data.remove_user(user)

        if self._sio.data.only_remaining_user():
            await self._sio.become_leader()

    # -----------------------------------------------------
    # Command handlers
    # -----------------------------------------------------

    # username and args (set to _)
    async def _handle_command(self, _: str, command: str, __: List[str]) -> None:
        """
        Route a parsed chat command to the appropriate handler.

        Args:
            username (str): User issuing the command.
            command (str): Command keyword.
            args (List[str]): Command arguments.
        """
        match command:
            case "help":
                await self._cmd_help()

    # It's too awkward to send the help info in chat due to
    # the chat limits, instead a link to the readme is sent.
    async def _cmd_help(self) -> None:
        """Display help information link."""
        symbol = Commands.COMMAND_SYMBOL.value
        await self._sio.send_chat_msg(
            f"Prefix commands with: ``{symbol}``. Commands: https://github.com/HiredNoobs/app-contentbot/blob/master/README.md#commands"
        )
