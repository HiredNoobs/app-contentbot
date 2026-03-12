import logging
from typing import Dict

from contentbot.chatbot.async_socket import AsyncSocket

logger: logging.Logger = logging.getLogger("contentbot")


class AsyncEventProcessor:
    def __init__(self, sio: AsyncSocket) -> None:
        self._sio = sio

    # -----------------------------------------------------
    # Event handlers
    # -----------------------------------------------------

    async def handle_connect(self):
        await self._sio.join_channel()

    async def handle_channel_opts(self):
        await self._sio.login()

    def handle_disconnect(self):
        self._sio.data.reset_data()

    async def handle_user_join(self, data: Dict) -> None:
        user = data["name"]
        rank = data["rank"]
        self._sio.data.add_or_update_user(user, rank)

    async def handle_user_leave(self, data: Dict) -> None:
        user = data["name"]
        self._sio.data.remove_user(user)
        if self._sio.data.only_remaining_user():
            await self._sio.become_leader()

    async def handle_successful_login(self, _: Dict) -> None:
        # playerReady tells the server to start sending changeMedia events.
        await self._sio.emit("playerReady")
        # This is sent by the client during the login, not sure what it does as it doesn't appear to be
        # handled on the server side. Mainly adding it to test if anything changes...
        # https://github.com/calzoneman/sync/blob/589f999a9c526bf773a8b21ecf29ba30faf14739/www/js/callbacks.js#L472
        await self._sio.emit("initUserPLCallbacks")

    def handle_set_permissions(self, data: Dict) -> None:
        self._sio.data.channel_permissions = data

    async def handle_user_list(self, data: Dict) -> None:
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
