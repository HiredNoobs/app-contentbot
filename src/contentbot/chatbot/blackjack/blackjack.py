from typing import Dict, List

from contentbot.chatbot.async_socket import AsyncSocket
from contentbot.chatbot.blackjack.deck import Deck
from contentbot.chatbot.blackjack.player import Player
from contentbot.exceptions import InvalidBlackjackState


class BlackjackGame:
    def __init__(self) -> None:
        self.deck: Deck = Deck()
        self.dealer_hand: List[Dict[str, str]] = []
        self.players: Dict[str, Player] = {}
        self._state: str = "idle"
        self._sio = AsyncSocket("", "")

    def add_player(self, username: str, initial_balance: int = 100) -> None:
        if username not in self.players:
            self.players[username] = Player(username, initial_balance)

    def remove_player(self, username: str) -> None:
        self.players.pop(username, None)

    def start_round(self) -> None:
        if not self.players:
            raise Exception("No players to start the round.")

        self.deck = Deck()
        self.dealer_hand = []
        self._state = "playing"

        for _ in range(2):
            for player in self.players.values():
                if player.hands is None:
                    player.hand.append(self.deck.draw_card())
                else:
                    player.add_card_to_active_hand(self.deck.draw_card())
            self.dealer_hand.append(self.deck.draw_card())

    def dealer_play(self) -> None:
        while self.calculate_hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.draw_card())

    def calculate_hand_value(self, hand: List[Dict[str, str]]) -> int:
        value = 0
        num_aces = 0
        for card in hand:
            rank = card["rank"]
            if rank in ["J", "Q", "K"]:
                value += 10
            elif rank == "A":
                num_aces += 1
            else:
                value += int(rank)
        for _ in range(num_aces):
            value += 11 if value + 11 <= 21 else 1
        return value

    async def resolve_round(self) -> None:
        dealer_value = self.calculate_hand_value(self.dealer_hand)
        await self._sio.send_chat_msg(f"Dealer's hand: {self.dealer_hand} (Value: {dealer_value})")
        for player in self.players.values():
            if player.hands is None:
                hands_to_evaluate = [player.hand]
            else:
                hands_to_evaluate = player.hands

            for hand in hands_to_evaluate:
                player_value = player.calculate_hand_value(hand)
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

        # Prepare for the next round.
        for player in self.players.values():
            player.reset_hands()
        self.dealer_hand = []
        self._state = "joining"
        await self._sio.send_chat_msg(
            "Round over. Use 'join' to enter the game or 'start_blackjack' to start a new round."
        )

    def all_players_done(self) -> bool:
        return all(player.finished for player in self.players.values())

    async def place_bet(self, username: str, bet_str: str) -> None:
        player = self.players.get(username)
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
        return self._state

    @state.setter
    def state(self, new_state: str):
        if new_state.lower() in ["idle", "joining", "playing"]:
            self._state = new_state.lower()
        else:
            raise InvalidBlackjackState(f"Attempted to set state to {new_state.lower()}")
