from contentbot.chatbot.blackjack.utils import calculate_hand_value


class TestUtils:
    def test_calculate_hand_value_numeric(self):
        """Calculates the value for a hand with number cards correctly."""
        hand = [{"rank": "5", "suit": "Hearts"}, {"rank": "7", "suit": "Diamonds"}]
        assert calculate_hand_value(hand) == 12

    def test_calculate_hand_value_face(self):
        """Face cards count as 10."""
        hand = [{"rank": "K", "suit": "Hearts"}, {"rank": "Q", "suit": "Diamonds"}]
        assert calculate_hand_value(hand) == 20

    def test_calculate_hand_value_ace(self):
        """Aces count as 11 unless that would bust the hand."""
        hand = [{"rank": "A", "suit": "Spades"}, {"rank": "5", "suit": "Clubs"}]
        assert calculate_hand_value(hand) == 16

        hand = [
            {"rank": "A", "suit": "Spades"},
            {"rank": "K", "suit": "Clubs"},
            {"rank": "5", "suit": "Hearts"},
        ]
        assert calculate_hand_value(hand) == 16
