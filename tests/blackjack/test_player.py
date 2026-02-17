from cytubebot.blackjack.deck import Deck
from cytubebot.blackjack.player import Player


class TestPlayer:
    def test_get_active_hand_no_split(self):
        """If no split has occurred, the active hand is the same as the basic hand."""
        p = Player("Alice")
        p.hand = [{"rank": "5", "suit": "Hearts"}]
        assert p.get_active_hand() == p.hand

    def test_add_card_to_active_hand_no_split(self):
        """Adding a card when no split has occurred appends to the player's hand."""
        p = Player("Alice")
        p.hand = []
        p.hands = None
        p.add_card_to_active_hand({"rank": "7", "suit": "Spades"})
        assert p.hand == [{"rank": "7", "suit": "Spades"}]

    def test_calculate_hand_value_numeric(self):
        """Calculates the value for a hand with number cards correctly."""
        p = Player("Alice")
        hand = [{"rank": "5", "suit": "Hearts"}, {"rank": "7", "suit": "Diamonds"}]
        assert p.calculate_hand_value(hand) == 12

    def test_calculate_hand_value_face(self):
        """Face cards count as 10."""
        p = Player("Alice")
        hand = [{"rank": "K", "suit": "Hearts"}, {"rank": "Q", "suit": "Diamonds"}]
        assert p.calculate_hand_value(hand) == 20

    def test_calculate_hand_value_ace(self):
        """Aces count as 11 unless that would bust the hand."""
        p = Player("Alice")
        hand = [{"rank": "A", "suit": "Spades"}, {"rank": "5", "suit": "Clubs"}]
        assert p.calculate_hand_value(hand) == 16

        hand = [
            {"rank": "A", "suit": "Spades"},
            {"rank": "K", "suit": "Clubs"},
            {"rank": "5", "suit": "Hearts"},
        ]
        assert p.calculate_hand_value(hand) == 16

    def test_calculate_active_hand_value(self):
        """calculate_active_hand_value returns the value of the current active hand."""
        p = Player("Alice")
        p.hand = [{"rank": "9", "suit": "Hearts"}, {"rank": "Q", "suit": "Clubs"}]
        assert p.calculate_active_hand_value() == 19

    def test_can_split_true(self):
        """A hand of exactly two cards with the same rank can be split."""
        p = Player("Alice")
        p.hand = [{"rank": "8", "suit": "Hearts"}, {"rank": "8", "suit": "Diamonds"}]
        assert p.can_split() is True

    def test_can_split_false_different_ranks(self):
        """A hand with two cards of different ranks cannot be split."""
        p = Player("Alice")
        p.hand = [{"rank": "8", "suit": "Hearts"}, {"rank": "9", "suit": "Diamonds"}]
        assert p.can_split() is False

    def test_do_split_success(monkeypatch):
        """do_split should split a splittable hand and update internal state accordingly."""
        p = Player("Alice")
        p.hand = [{"rank": "8", "suit": "Hearts"}, {"rank": "8", "suit": "Diamonds"}]
        p.hands = None
        deck = Deck()
        result = p.do_split(deck)

        assert result is True
        assert p.hands is not None
        assert len(p.hands) == 2
        assert p.split_count == 1

    def test_do_split_failure_when_not_splittable(self):
        """do_split returns False if the hand cannot be split."""
        p = Player("Alice")
        p.hand = [{"rank": "8", "suit": "Hearts"}, {"rank": "9", "suit": "Diamonds"}]
        deck = Deck()
        result = p.do_split(deck)
        assert result is False

    def test_finish_active_hand_no_split(self):
        """When no split exists, finish_active_hand marks the player as finished."""
        p = Player("Alice")
        p.hands = None
        p.finished = False
        p.finish_active_hand()
        assert p.finished is True

    def test_finish_active_hand_with_split(self):
        """When split hands exist, finish_active_hand advances the active hand then eventually marks finished."""
        p = Player("Alice")
        p.hands = [
            [{"rank": "8", "suit": "Hearts"}],
            [{"rank": "8", "suit": "Diamonds"}],
        ]
        p.active_hand_index = 0
        p.finished = False
        p.finish_active_hand()

        # After finishing first hand, active_hand_index should advance.
        assert p.active_hand_index == 1
        assert p.finished is False

        # Now finish the second hand.
        p.finish_active_hand()
        assert p.finished is True

    def test_reset_hands(self):
        """reset_hands should restore initial values for a player preparing for a new round."""
        p = Player("Alice")
        p.hand = [{"rank": "K", "suit": "Spades"}]
        p.hands = [[{"rank": "K", "suit": "Spades"}]]
        p.active_hand_index = 1
        p.finished = True
        p.bet = 50
        p.split_count = 2

        p.reset_hands()

        assert p.hand == []
        assert p.hands is None
        assert p.active_hand_index == 0
        assert p.finished is False
        assert p.bet == 0
        assert p.split_count == 0
