import pytest

from cytubebot.blackjack.deck import Deck


class TestDeck:
    def test_deck_initialization(self):
        """After creating a deck it should contain 52 cards."""
        deck = Deck()
        assert len(deck.cards) == 52

    def test_deck_unique_cards(self):
        """The deck should include 52 unique cards (13 ranks x 4 suits)."""
        deck = Deck()
        unique_cards = {(card["rank"], card["suit"]) for card in deck.cards}
        assert len(unique_cards) == 52

    def test_draw_card_reduces_deck(self):
        """Drawing a card should reduce the number of cards in the deck by one and return a dict."""
        deck = Deck()
        initial_count = len(deck.cards)
        card = deck.draw_card()

        assert isinstance(card, dict)
        assert len(deck.cards) == initial_count - 1

    def test_draw_all_cards_and_exception(self):
        """After drawing all 52 cards, drawing one more should raise an Exception."""
        deck = Deck()
        for _ in range(52):
            deck.draw_card()

        with pytest.raises(Exception, match="Deck is empty."):
            deck.draw_card()

    def test_shuffle_changes_order(self):
        """Two different deck instances (or re-shuffled deck) should not always present the same order."""
        deck1 = Deck()
        deck2 = Deck()

        order1 = [(card["rank"], card["suit"]) for card in deck1.cards]
        order2 = [(card["rank"], card["suit"]) for card in deck2.cards]

        # Surely the shuffle won't return the same order ever, right?
        if order1 == order2:
            deck1.shuffle()
            order1 = [(card["rank"], card["suit"]) for card in deck1.cards]
            assert order1 != order2
        else:
            assert order1 != order2
