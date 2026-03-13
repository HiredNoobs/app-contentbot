from typing import Dict, List

from contentbot.chatbot.blackjack.deck import Deck
from contentbot.chatbot.blackjack.utils import calculate_hand_value


class Player:
    """Represents a blackjack player, including hand state, betting, and split logic."""

    def __init__(self, name: str, balance: int = 100) -> None:
        """
        Initialise a new player.

        Args:
            name (str): The player's username.
            balance (int): Starting chip balance for the player.
        """
        self.name = name
        self.hand: List[Dict[str, str]] = []
        self.hands: List[List[Dict[str, str]]] | None = None
        self._active_hand_index: int = 0
        self.balance = balance
        self.bet = 0
        self.finished = False
        self._split_count = 0

    def get_active_hand(self) -> List[Dict[str, str]]:
        """
        Retrieve the hand currently being played.

        Returns:
            List[Dict[str, str]]: The active hand, whether split or not.
        """
        if self.hands is not None:
            return self.hands[self._active_hand_index]
        return self.hand

    def add_card_to_active_hand(self, card: Dict[str, str]) -> None:
        """
        Add a card to the player's active hand.

        Args:
            card (Dict[str, str]): The card to add.
        """
        if self.hands is not None:
            self.hands[self._active_hand_index].append(card)
        else:
            self.hand.append(card)

    def calculate_active_hand_value(self) -> int:
        """
        Calculate the blackjack value of the active hand.

        Returns:
            int: The numeric value of the active hand.
        """
        return calculate_hand_value(self.get_active_hand())

    def _can_double(self) -> bool:
        """
        Determine whether the player is eligible to double down.

        Conditions:
            - Active hand must contain exactly two cards.
            - Player must have an existing bet.
            - Player must have enough balance to double the bet.

        Returns:
            bool: True if doubling is allowed, otherwise False.
        """
        hand = self.get_active_hand()

        if len(hand) != 2:
            return False

        if self.bet <= 0:
            return False

        if self.balance < self.bet:
            return False

        return True

    def double_bet(self) -> bool:
        """
        Attempt to double the player's bet.

        Returns:
            bool: True if the bet was successfully doubled, otherwise False.
        """
        if not self._can_double():
            return False

        self.balance -= self.bet
        self.bet *= 2
        return True

    def _can_split(self) -> bool:
        """
        Check whether the active hand can be split.

        Conditions:
            - Hand must contain exactly two cards.
            - Both cards must have the same rank.

        Returns:
            bool: True if the hand can be split, otherwise False.
        """
        hand = self.get_active_hand()
        return len(hand) == 2 and hand[0]["rank"] == hand[1]["rank"]

    def do_split(self, deck: Deck) -> bool:
        """
        Perform a split on the active hand if allowed.

        If a split is performed:
            - The two cards in the active hand are separated into two hands.
            - Each new hand receives one additional card from the deck.

        Args:
            deck (Deck): The deck to draw new cards from.

        Returns:
            bool: True if the split was successful, otherwise False.
        """
        if not self._can_split():
            return False

        if self.hands is None:
            self.hands = [self.hand]
            self._active_hand_index = 0

        current_hand = self.hands[self._active_hand_index]
        new_hand = [current_hand.pop()]

        try:
            current_hand.append(deck.draw_card())
            new_hand.append(deck.draw_card())
        except Exception:
            current_hand.append(new_hand.pop())
            return False

        self.hands.insert(self._active_hand_index + 1, new_hand)
        self._split_count += 1
        return True

    def finish_active_hand(self) -> None:
        """
        Mark the current active hand as finished.

        Behaviour:
            - If multiple split hands exist, move to the next hand.
            - If no more hands remain, mark the player as fully finished.
        """
        if self.hands is None:
            self.finished = True
        else:
            if self._active_hand_index < len(self.hands) - 1:
                self._active_hand_index += 1
            else:
                self.finished = True

    def reset_hands(self) -> None:
        """Reset all hand-related state."""
        self.hand = []
        self.hands = None
        self._active_hand_index = 0
        self.finished = False
        self.bet = 0
        self._split_count = 0
