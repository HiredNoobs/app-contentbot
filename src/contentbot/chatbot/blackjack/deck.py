import random
from typing import Dict, List


class Deck:
    """Represents a standard 52-card deck used for blackjack."""

    def __init__(self) -> None:
        """
        Initialise a new shuffled deck of 52 cards.

        The deck is automatically created and shuffled on instantiation.
        """
        self.cards = self._create_deck()
        self.shuffle()

    def _create_deck(self) -> List[Dict[str, str]]:
        """
        Create a standard 52-card deck.

        Returns:
            List[Dict[str, str]]: A list of card dictionaries, each containing
            'rank' and 'suit' keys.
        """
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        suits = ["Hearts", "Diamonds", "Clubs", "Spades"]
        return [{"rank": rank, "suit": suit} for rank in ranks for suit in suits]

    def shuffle(self) -> None:
        """Shuffle the deck."""
        random.shuffle(self.cards)

    def draw_card(self) -> Dict[str, str]:
        """
        Draw and return the top card from the deck.

        Returns:
            Dict[str, str]: A dictionary representing the drawn card.

        Raises:
            Exception: If the deck is empty.
        """
        if self.cards:
            return self.cards.pop()
        else:
            raise Exception("Deck is empty.")
