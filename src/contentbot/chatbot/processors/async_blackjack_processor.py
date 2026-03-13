from typing import Dict, List

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.blackjack.blackjack import BlackjackGame
from contentbot.chatbot.blackjack.utils import calculate_hand_value
from contentbot.chatbot.processors.base_processor import BaseProcessor


class AsyncBlackjackProcessor(BaseProcessor):
    """Processor for Blackjack events (mainly chat commands.)"""

    def __init__(self, sio: AsyncSocket) -> None:
        super().__init__(sio)
        self._blackjack = BlackjackGame(sio)

    # -----------------------------------------------------
    # Event handlers
    # -----------------------------------------------------

    async def handle_chat_message(self, data: Dict):
        username, command, args = self._parse_chat_event(data)
        await self._handle_command(username, command, args)

    async def _handle_end_round(self) -> None:
        self._blackjack.dealer_play()
        dealer_value = calculate_hand_value(self._blackjack.dealer_hand)
        await self._sio.send_chat_msg(
            f"Dealer's hand: {self._blackjack.dealer_hand} (Value: {dealer_value})",
        )
        await self._blackjack.resolve_round()

    # -----------------------------------------------------
    # Command handlers
    # -----------------------------------------------------

    async def _handle_command(self, username: str, command: str, args: List[str]) -> None:
        match command:
            case "bet":
                if not args:
                    await self._sio.send_chat_msg("Please specify a bet amount.")
                    return
                await self._cmd_bet(username, args[0])
            case "hit":
                if self._blackjack.mid_round_checks():
                    await self._cmd_hit(username)
            case "join":
                await self._cmd_join(username)
            case "split":
                if self._blackjack.mid_round_checks():
                    await self._cmd_split(username)
            case "stand":
                if self._blackjack.mid_round_checks():
                    await self._cmd_stand(username)
            case "init_blackjack":
                if self._sio.data.is_user_admin(username):
                    await self._cmd_init_blackjack()
                else:
                    await self._sio.send_chat_msg("You don't have permission to do that.")
            case "start_blackjack":
                if self._sio.data.is_user_admin(username):
                    if not self._blackjack.pre_round_checks():
                        await self._sio.send_chat_msg("Round not ready to start...")
                        return
                    await self._cmd_start_blackjack()
                else:
                    await self._sio.send_chat_msg("You don't have permission to do that.")
            case "stop_blackjack":
                if self._sio.data.is_user_admin(username):
                    await self._cmd_stop_blackjack()
                else:
                    await self._sio.send_chat_msg("You don't have permission to do that.")

        # After every command, if the game is in play and all players have finished, resolve the round.
        if self._blackjack.mid_round_checks() and self._blackjack.all_players_done():
            await self._handle_end_round()

    async def _cmd_bet(self, username: str, bet: str) -> None:
        await self._blackjack.place_bet(username, bet)

    async def _cmd_hit(self, username: str) -> None:
        player = self._blackjack.get_player(username)
        if not player:
            return

        if player.finished:
            return

        card = self._blackjack.deck.draw_card()
        player.add_card_to_active_hand(card)

        hv = player.calculate_active_hand_value()
        await self._sio.send_chat_msg(f"{player.name}, active hand: {player.get_active_hand()} (value {hv})")

        if hv > 21:
            await self._sio.send_chat_msg(f"{username} busts on this hand!")
            player.finish_active_hand()
        elif hv == 21:
            await self._sio.send_chat_msg(f"{username} got Blackjack on this hand!")
            player.finish_active_hand()

    async def _cmd_join(self, username: str) -> None:
        await self._blackjack.add_player(username)

    async def _cmd_split(self, username: str) -> None:
        player = self._blackjack.get_player(username)
        if not player:
            return

        if player.do_split(self._blackjack.deck):
            await self._sio.send_chat_msg(f"Now playing hand: {player.get_active_hand()}")
        else:
            await self._sio.send_chat_msg("Cannot split hand.")

    async def _cmd_stand(self, username: str) -> None:
        player = self._blackjack.get_player(username)
        if not player:
            return

        player.finish_active_hand()
        await self._sio.send_chat_msg(f"{username} stands on active hand.")

    async def _cmd_init_blackjack(self) -> None:
        self._blackjack.start_game()
        await self._sio.send_chat_msg("Blackjack initialized. Use 'join' to enter the game.")

    async def _cmd_start_blackjack(self) -> None:
        self._blackjack.start_round()
        await self._sio.send_chat_msg(f"Dealer's first card is {self._blackjack.dealer_hand[0]}.")

        for player in self._blackjack.get_players():
            hv = player.calculate_active_hand_value()
            await self._sio.send_chat_msg(f"{player.name}, active hand: {player.get_active_hand()} (value {hv})")

    async def _cmd_stop_blackjack(self) -> None:
        self._blackjack.stop_game()
        await self._sio.send_chat_msg("Blackjack stopped.")
