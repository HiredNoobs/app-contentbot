import logging
from typing import List

from cytubebot.blackjack.blackjack import BlackjackGame
from cytubebot.src.cytubebot.socket_wrapper import SocketWrapper

logger = logging.getLogger(__name__)


class BlackjackBot:
    def __init__(self) -> None:
        self._sio = SocketWrapper("", "")
        self.blackjack = BlackjackGame()

    def process_chat_command(
        self, username: str, command: str, args: List[str]
    ) -> None:
        logger.debug(f"Processing blackjack command {command=}, {args=}")
        match command:
            case "init_blackjack":
                self._handle_init_blackjack()
            case "join":
                self._handle_join(username)
            case "bet":
                self._handle_bet(username, args)
            case "start_blackjack":
                self._handle_start_blackjack()
            case "hit":
                self._handle_hit(username)
            case "stand":
                self._handle_stand(username)
            case "split":
                self._handle_split(username)
            case "stop_blackjack":
                self._handle_stop_blackjack()
            case _:
                self._sio.send_chat_msg(f"Unknown blackjack command: {command}")

        # After every command, if the game is in play and all players have finished, resolve the round.
        if self.blackjack.state == "playing" and self.blackjack.all_players_done():
            self._handle_end_round()

    def _handle_init_blackjack(self) -> None:
        self.blackjack = BlackjackGame()
        self.blackjack.state = "joining"
        self._sio.send_chat_msg("Blackjack initialized. Use 'join' to enter the game.")

    def _handle_join(self, username: str) -> None:
        if self.blackjack.state == "joining":
            self.blackjack.add_player(username)
            self._sio.send_chat_msg(f"{username} joined blackjack!")
        else:
            self._sio.send_chat_msg("Cannot join at this time.")

    def _handle_bet(self, username: str, args: List[str]) -> None:
        if self.blackjack.state == "joining" and username in self.blackjack.players:
            if not args:
                self._sio.send_chat_msg("Please specify a bet amount.")
                return
            self.blackjack.place_bet(username, args[0])
        else:
            self._sio.send_chat_msg("Betting not allowed at this time.")

    def _handle_start_blackjack(self) -> None:
        if self.blackjack.state != "joining":
            logger.debug(f"{self.blackjack.state=} not joining, game not starting.")
            return

        if any(player.bet == 0 for player in self.blackjack.players.values()):
            self._sio.send_chat_msg("Missing bets from players.")
            return

        try:
            self.blackjack.start_round()
            self._sio.send_chat_msg(
                f"Dealer's first card is: {self.blackjack.dealer_hand[0]}",
            )
            for player in self.blackjack.players.values():
                if player.hands is None:
                    hv = player.calculate_hand_value(player.hand)
                    self._sio.send_chat_msg(
                        f"{player.name}, your hand: {player.hand} (Value: {hv})",
                    )
                else:
                    hv = player.calculate_active_hand_value()
                    self._sio.send_chat_msg(
                        f"{player.name}, active hand: {player.get_active_hand()} (Value: {hv})",
                    )
        except Exception as e:
            self._sio.send_chat_msg(f"Error starting round: {e}")

    def _handle_hit(self, username: str) -> None:
        if self.blackjack.state == "playing" and username in self.blackjack.players:
            player = self.blackjack.players[username]
            if not player.finished:
                try:
                    card = self.blackjack.deck.draw_card()
                except Exception as e:
                    self._sio.send_chat_msg(f"Error drawing card: {e}")
                    return
                player.add_card_to_active_hand(card)
                active_hand = player.get_active_hand()
                hand_value = player.calculate_hand_value(active_hand)
                self._sio.send_chat_msg(
                    f"{username}, your current hand: {active_hand} (Value: {hand_value})",
                )
                if hand_value > 21:
                    self._sio.send_chat_msg(f"{username} busts on this hand!")
                    player.finish_active_hand()
                elif hand_value == 21:
                    self._sio.send_chat_msg(f"{username} got Blackjack on this hand!")
                    player.finish_active_hand()
        else:
            self._sio.send_chat_msg("Hit not allowed at this time.")

    def _handle_stand(self, username: str) -> None:
        if self.blackjack.state == "playing" and username in self.blackjack.players:
            self.blackjack.players[username].finish_active_hand()
            self._sio.send_chat_msg(f"{username} stands on the current hand.")
        else:
            self._sio.send_chat_msg("Stand not allowed at this time.")

    def _handle_split(self, username: str) -> None:
        if self.blackjack.state != "playing":
            self._sio.send_chat_msg("Can only split during play.")
            return
        player = self.blackjack.players.get(username)
        if not player:
            self._sio.send_chat_msg(f"Player {username} not found.")
            return
        if not player.can_split():
            self._sio.send_chat_msg(
                "Current hand cannot be split (must be exactly two cards with the same rank).",
            )
            return
        try:
            if player.do_split(self.blackjack.deck):
                self._sio.send_chat_msg(f"{username} has split the hand!")
                self._sio.send_chat_msg(f"Now playing hand: {player.get_active_hand()}")
            else:
                self._sio.send_chat_msg("Error during splitting the hand.")
        except Exception as e:
            self._sio.send_chat_msg(f"Error splitting hand: {e}")

    def _handle_stop_blackjack(self) -> None:
        self.blackjack.state = "idle"
        self.blackjack.players = {}
        self.blackjack.dealer_hand = []
        self._sio.send_chat_msg("Blackjack stopped.")

    def _handle_end_round(self) -> None:
        self.blackjack.dealer_play()
        dealer_value = self.blackjack.calculate_hand_value(self.blackjack.dealer_hand)
        self._sio.send_chat_msg(
            f"Dealer's hand: {self.blackjack.dealer_hand} (Value: {dealer_value})",
        )
        self.blackjack.resolve_round()
