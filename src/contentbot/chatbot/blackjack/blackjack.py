from typing import Dict, List, Optional

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.blackjack.deck import Deck
from contentbot.chatbot.blackjack.player import Player
from contentbot.chatbot.blackjack.utils import calculate_hand_value
from contentbot.exceptions import InvalidBlackjackState


class BlackjackGame:
    """Manage the flow, state, and logic of blackjack game."""

    def __init__(self, sio: AsyncSocket) -> None:
        """
        Initialise a new BlackjackGame instance.

        Args:
            sio (AsyncSocket): Socket interface used to send chat messages.
        """
        self.deck: Deck = Deck()
        self.dealer_hand: List[Dict[str, str]] = []
        self._players: Dict[str, Player] = {}
        self._state: str = "idle"
        self._sio = sio

    def start_game(self) -> None:
        """Set the game state to 'joining', allowing players to enter."""
        self.state = "joining"

    def stop_game(self) -> None:
        """Reset the game to its initial idle state, clearing players and hands."""
        self._state = "idle"
        self._players = {}
        self.dealer_hand = []

    def get_player(self, username: str) -> Optional[Player]:
        """
        Retrieve a player object by username.

        Args:
            username (str): The player's username.

        Returns:
            Optional[Player]: The Player instance if found, otherwise None.
        """
        return self._players.get(username)

    def get_players(self) -> List[Player]:
        """
        Get a list of all players currently in the game.

        Returns:
            List[Player]: All active players.
        """
        return list(self._players.values())

    async def add_player(self, username: str, initial_balance: int = 100) -> None:
        """
        Add a new player to the game during the joining phase.

        Args:
            username (str): The player's username.
            initial_balance (int): Starting chip balance for the player.
        """
        if not self._state == "joining":
            await self._sio.send_chat_msg("Cannot join at this time.")
            return

        if username not in self._players:
            self._players[username] = Player(username, initial_balance)
            await self._sio.send_chat_msg(f"{username} joined!")

    def remove_player(self, username: str) -> None:
        """
        Remove a player from the game.

        Args:
            username (str): Username of the player to remove.
        """
        self._players.pop(username, None)

    def pre_round_checks(self) -> bool:
        """
        Validate that all players have placed bets and the game can begin.

        Returns:
            bool: True if the round can start, otherwise False.
        """
        if self._state != "joining":
            return False

        if any(player.bet == 0 for player in self._players.values()):
            return False

        return True

    def mid_round_checks(self) -> bool:
        """
        Validate that the game is currently in the playing state.

        Returns:
            bool: True if mid-round actions are allowed, otherwise False.
        """
        return self._state == "playing"

    def start_round(self) -> None:
        """
        Begin a new round: reset deck, deal initial cards, and set state to playing.

        Raises:
            Exception: If no players are present.
        """
        if not self._players:
            raise Exception("No players to start the round.")

        self.deck = Deck()
        self.dealer_hand = []
        self._state = "playing"

        for _ in range(2):
            for player in self._players.values():
                if player.hands is None:
                    player.hand.append(self.deck.draw_card())
                else:
                    player.add_card_to_active_hand(self.deck.draw_card())
            self.dealer_hand.append(self.deck.draw_card())

    def dealer_play(self) -> None:
        """
        Execute the dealer's turn, drawing until reaching a value of 17 or more.
        """
        while calculate_hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.draw_card())

    async def resolve_round(self) -> None:
        """
        Compare all player hands against the dealer, update balances,
        announce results, and reset for the next joining phase.
        """
        dealer_value = calculate_hand_value(self.dealer_hand)
        await self._sio.send_chat_msg(f"Dealer's hand: {self.dealer_hand} (Value: {dealer_value})")

        for player in self._players.values():
            hands_to_evaluate = [player.hand] if player.hands is None else player.hands

            for hand in hands_to_evaluate:
                player_value = calculate_hand_value(hand)
                bet = player.bet

                if player_value > 21:
                    await self._sio.send_chat_msg(f"{player.name} busts on hand {hand}! You lose.")
                    player.balance -= bet
                elif dealer_value > 21 or dealer_value < player_value:
                    await self._sio.send_chat_msg(f"{player.name} wins on hand {hand}! You win {bet} chips.")
                    player.balance += bet
                elif dealer_value == player_value:
                    await self._sio.send_chat_msg(f"{player.name}, it's a tie on hand {hand}! {bet} is returned.")
                else:
                    await self._sio.send_chat_msg(f"{player.name}, dealer wins against hand {hand}. You lose {bet}.")
                    player.balance -= bet

        # Reset for next round
        for player in self._players.values():
            player.reset_hands()

        self.dealer_hand = []
        self._state = "joining"

        await self._sio.send_chat_msg(
            "Round over. Use 'join' to enter the game or 'start_blackjack' to start a new round."
        )

    def all_players_done(self) -> bool:
        """
        Check whether all players have completed their actions.

        Returns:
            bool: True if all players are finished, otherwise False.
        """
        return all(player.finished for player in self._players.values())

    async def place_bet(self, username: str, bet_str: str) -> None:
        """
        Set a player's bet for the round.

        Args:
            username (str): Player placing the bet.
            bet_str (str): Bet amount as a string (validated and converted to int).
        """
        if self._state != "joining":
            await self._sio.send_chat_msg("Betting is not allowed at this time.")
            return

        player = self._players.get(username)
        if not player:
            await self._sio.send_chat_msg(f"Player {username} not found.")
            return

        try:
            bet_amount = int(bet_str)
            if bet_amount <= 0 or bet_amount > player.balance:
                await self._sio.send_chat_msg("Invalid bet. Please enter a valid amount.")
            else:
                player.bet = bet_amount
                await self._sio.send_chat_msg(f"{username} bet set to {bet_amount}.")
        except ValueError:
            await self._sio.send_chat_msg("Invalid input. Please enter a valid integer bet.")

    @property
    def state(self) -> str:
        """
        Current game state.

        Returns:
            str: One of 'idle', 'joining', or 'playing'.
        """
        return self._state

    @state.setter
    def state(self, new_state: str):
        """
        Set the game state, validating allowed transitions.

        Args:
            new_state (str): Desired state.

        Raises:
            InvalidBlackjackState: If the state is not recognised.
        """
        if new_state.lower() in ["idle", "joining", "playing"]:
            self._state = new_state.lower()
        else:
            raise InvalidBlackjackState(f"Attempted to set state to {new_state.lower()}")
