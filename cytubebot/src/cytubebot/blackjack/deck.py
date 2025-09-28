import random
from typing import Dict, List


class Deck:
    def __init__(self) -> None:
        self.cards = self._create_deck()
        self.shuffle()

    def _create_deck(self) -> List[Dict[str, str]]:
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        suits = ["Hearts", "Diamonds", "Clubs", "Spades"]
        return [{"rank": rank, "suit": suit} for rank in ranks for suit in suits]

    def shuffle(self) -> None:
        random.shuffle(self.cards)

    def draw_card(self) -> Dict[str, str]:
        if self.cards:
            return self.cards.pop()
        else:
            raise Exception("Deck is empty.")
