import pytest

from cytubebot.src.cytubebot.blackjack.blackjack import BlackjackGame
from cytubebot.src.cytubebot.blackjack.deck import Deck
from cytubebot.src.cytubebot.blackjack.player import Player
from cytubebot.src.cytubebot.exceptions import InvalidBlackjackState


# fake socket to capture messages from the game.
class FakeSocket:
    def __init__(self):
        self.messages = []

    def send_chat_msg(self, msg: str):
        self.messages.append(msg)


@pytest.fixture
def game():
    """Create a BlackjackGame instance with its internal socket replaced by a fake."""
    game = BlackjackGame()
    fake_socket = FakeSocket()
    game._sio = fake_socket
    return game


class TestBlackjack:
    def test_add_player(self, game):
        """add_player should add a new player to the game."""
        game.add_player("Alice")
        assert "Alice" in game.players
        assert isinstance(game.players["Alice"], Player)

    def test_remove_player(self, game):
        """remove_player should remove an existing player."""
        game.add_player("Alice")
        game.remove_player("Alice")
        assert "Alice" not in game.players

    def test_start_round_no_players(self, game):
        """start_round should raise an Exception if there are no players."""
        with pytest.raises(Exception, match="No players to start the round."):
            game.start_round()

    def test_start_round_success(self, monkeypatch, game):
        """start_round should deal two cards to each player and two to the dealer and set state to 'playing'."""
        game.add_player("Alice")
        game.add_player("Bob")

        def fixed_draw(self):
            return {"rank": "5", "suit": "Hearts"}

        monkeypatch.setattr(Deck, "draw_card", fixed_draw)
        game.start_round()
        for player in game.players.values():
            assert len(player.hand) == 2
        assert len(game.dealer_hand) == 2
        assert game._state == "playing"

    def test_dealer_play(self, monkeypatch, game):
        """dealer_play should continue drawing until dealer's hand value is at least 17."""
        game.dealer_hand = [
            {"rank": "5", "suit": "Hearts"},
            {"rank": "5", "suit": "Diamonds"},
        ]

        def fixed_draw(self):
            return {"rank": "10", "suit": "Clubs"}

        monkeypatch.setattr(Deck, "draw_card", fixed_draw)
        game.dealer_play()
        total = game.calculate_hand_value(game.dealer_hand)
        assert total >= 17

    def test_resolve_round_player_bust(self, game):
        """resolve_round should report a bust and deduct the bet from the player's balance."""
        game.add_player("Alice")
        game.players["Alice"].bet = 50

        game.players["Alice"].hand = [
            {"rank": "10", "suit": "Hearts"},
            {"rank": "10", "suit": "Diamonds"},
            {"rank": "5", "suit": "Clubs"},
        ]

        game.dealer_hand = [
            {"rank": "10", "suit": "Clubs"},
            {"rank": "8", "suit": "Hearts"},
        ]
        initial_balance = game.players["Alice"].balance
        game.resolve_round()

        msgs = game._sio.messages
        assert any("busts on hand" in msg for msg in msgs)
        assert game.players["Alice"].balance == initial_balance - 50

    def test_resolve_round_player_win(self, game):
        """If the player's hand beats the dealer's, resolve_round should add the bet to player's balance."""
        game.add_player("Alice")
        game.players["Alice"].bet = 50
        game.players["Alice"].hand = [
            {"rank": "10", "suit": "Hearts"},
            {"rank": "Q", "suit": "Diamonds"},
        ]

        game.dealer_hand = [
            {"rank": "10", "suit": "Clubs"},
            {"rank": "8", "suit": "Hearts"},
        ]
        initial_balance = game.players["Alice"].balance
        game.resolve_round()

        msgs = game._sio.messages
        assert any("wins on hand" in msg for msg in msgs)
        assert game.players["Alice"].balance == initial_balance + 50

    def test_resolve_round_tie(self, game):
        """If the player's hand ties with the dealer, the bet is returned."""
        game.add_player("Alice")
        game.players["Alice"].bet = 50

        game.players["Alice"].hand = [
            {"rank": "10", "suit": "Hearts"},
            {"rank": "8", "suit": "Diamonds"},
        ]
        game.dealer_hand = [
            {"rank": "9", "suit": "Clubs"},
            {"rank": "9", "suit": "Hearts"},
        ]
        initial_balance = game.players["Alice"].balance
        game.resolve_round()

        msgs = game._sio.messages
        assert any("it's a tie" in msg for msg in msgs)
        assert game.players["Alice"].balance == initial_balance

    def test_all_players_done(self, game):
        """all_players_done should only return True if every player is finished."""
        game.add_player("Alice")
        game.add_player("Bob")

        for p in game.players.values():
            p.finished = False
        assert game.all_players_done() is False

        for p in game.players.values():
            p.finished = True
        assert game.all_players_done() is True

    def test_place_bet_valid(self, game):
        """place_bet should set the player's bet with valid input and confirm with a message."""
        game.add_player("Alice")
        game.place_bet("Alice", "30")

        msgs = game._sio.messages
        assert "Alice bet set to 30." in msgs[0]
        assert game.players["Alice"].bet == 30

    def test_place_bet_invalid_amount(self, game):
        """If the bet exceeds the player's balance, place_bet should report an error."""
        game.add_player("Alice")
        game.place_bet("Alice", "200")

        msgs = game._sio.messages
        assert any("Invalid bet" in msg for msg in msgs)
        assert game.players["Alice"].bet == 0

    def test_place_bet_invalid_input(self, game):
        """Non-integer bet input should be rejected."""
        game.add_player("Alice")
        game.place_bet("Alice", "notanumber")

        msgs = game._sio.messages
        assert any("Invalid input" in msg for msg in msgs)
        assert game.players["Alice"].bet == 0

    def test_state_getter_setter(self, game):
        """Valid state assignments should update the game state correctly."""
        game.state = "idle"
        assert game.state == "idle"

        game.state = "joining"
        assert game.state == "joining"

        game.state = "playing"
        assert game.state == "playing"

        with pytest.raises(InvalidBlackjackState):
            game.state = "finished"
