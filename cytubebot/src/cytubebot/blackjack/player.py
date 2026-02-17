from typing import Dict, List

from cytubebot.blackjack.deck import Deck


class Player:
    def __init__(self, name: str, balance: int = 100) -> None:
        self.name = name
        self.hand: List[Dict[str, str]] = []
        self.hands: List[List[Dict[str, str]]] | None = None
        # Index for the hand in active play (if hands have been split)
        self.active_hand_index: int = 0
        self.balance = balance
        self.bet = 0
        self.finished = False
        self.split_count = 0

    def get_active_hand(self) -> List[Dict[str, str]]:
        if self.hands is not None:
            return self.hands[self.active_hand_index]
        return self.hand

    def add_card_to_active_hand(self, card: Dict[str, str]) -> None:
        if self.hands is not None:
            self.hands[self.active_hand_index].append(card)
        else:
            self.hand.append(card)

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

    def calculate_active_hand_value(self) -> int:
        return self.calculate_hand_value(self.get_active_hand())

    def can_split(self) -> bool:
        """Returns a bool for whether the current hand can be split"""
        hand = self.get_active_hand()
        return len(hand) == 2 and hand[0]["rank"] == hand[1]["rank"]

    def do_split(self, deck: Deck) -> bool:
        """
        Splits the active hand if possible.
        The active hand (which must have exactly two cards of the same rank) is
        split into two separate hands. Each resulting hand is dealt one extra card.
        Returns True if the split is successful.
        """
        if not self.can_split():
            return False

        # If this is the first split, create the hand container.
        if self.hands is None:
            self.hands = [self.hand]
            self.active_hand_index = 0

        current_hand = self.hands[self.active_hand_index]
        # Remove the second card to create a new hand.
        new_hand = [current_hand.pop()]
        try:
            # Deal one new card to each hand.
            current_hand.append(deck.draw_card())
            new_hand.append(deck.draw_card())
        except Exception:
            # Roll back the split in case of an error.
            current_hand.append(new_hand.pop())
            return False

        # Insert the new hand into the list right after the active one.
        self.hands.insert(self.active_hand_index + 1, new_hand)
        self.split_count += 1
        return True

    def finish_active_hand(self) -> None:
        """
        Marks the current active hand as finished.
        If there are split hands, automatically advance to the next hand.
        Otherwise, mark the player as finished.
        """
        if self.hands is None:
            self.finished = True
        else:
            if self.active_hand_index < len(self.hands) - 1:
                self.active_hand_index += 1
            else:
                self.finished = True

    def reset_hands(self) -> None:
        """Reset all hand data to prepare for a new round."""
        self.hand = []
        self.hands = None
        self.active_hand_index = 0
        self.finished = False
        self.bet = 0
        self.split_count = 0
