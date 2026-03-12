import pytest

from contentbot.chatbot.blackjack.blackjack import BlackjackGame
from contentbot.chatbot.blackjack.deck import Deck
from contentbot.chatbot.blackjack.player import Player
from contentbot.chatbot.blackjack.utils import calculate_hand_value
from contentbot.exceptions import InvalidBlackjackState


class FakeSocket:
    def __init__(self):
        self.messages = []

    async def send_chat_msg(self, msg: str):
        self.messages.append(msg)


@pytest.fixture
def game():
    fake_socket = FakeSocket()
    return BlackjackGame(fake_socket)


class TestBlackjack:

    @pytest.mark.asyncio
    async def test_add_player(self, game):
        game.start_game()  # must be in joining state
        await game.add_player("Alice")
        assert "Alice" in game._players
        assert isinstance(game._players["Alice"], Player)

    @pytest.mark.asyncio
    async def test_remove_player(self, game):
        game.start_game()
        await game.add_player("Alice")
        game.remove_player("Alice")
        assert "Alice" not in game._players

    def test_start_round_no_players(self, game):
        with pytest.raises(Exception, match="No players to start the round."):
            game.start_round()

    @pytest.mark.asyncio
    async def test_start_round_success(self, monkeypatch, game):
        game.start_game()
        await game.add_player("Alice")
        await game.add_player("Bob")

        def fixed_draw(self):
            return {"rank": "5", "suit": "Hearts"}

        monkeypatch.setattr(Deck, "draw_card", fixed_draw)
        game.start_round()

        for player in game._players.values():
            assert len(player.hand) == 2

        assert len(game.dealer_hand) == 2
        assert game._state == "playing"

    def test_dealer_play(self, monkeypatch, game):
        game.dealer_hand = [
            {"rank": "5", "suit": "Hearts"},
            {"rank": "5", "suit": "Diamonds"},
        ]

        def fixed_draw(self):
            return {"rank": "10", "suit": "Clubs"}

        monkeypatch.setattr(Deck, "draw_card", fixed_draw)
        game.dealer_play()

        total = calculate_hand_value(game.dealer_hand)
        assert total >= 17

    @pytest.mark.asyncio
    async def test_resolve_round_player_bust(self, game):
        game.start_game()
        await game.add_player("Alice")
        game._players["Alice"].bet = 50

        game._players["Alice"].hand = [
            {"rank": "10", "suit": "Hearts"},
            {"rank": "10", "suit": "Diamonds"},
            {"rank": "5", "suit": "Clubs"},
        ]

        game.dealer_hand = [
            {"rank": "10", "suit": "Clubs"},
            {"rank": "8", "suit": "Hearts"},
        ]

        initial_balance = game._players["Alice"].balance
        await game.resolve_round()

        msgs = game._sio.messages
        assert any("busts on hand" in msg for msg in msgs)
        assert game._players["Alice"].balance == initial_balance - 50

    @pytest.mark.asyncio
    async def test_resolve_round_player_win(self, game):
        game.start_game()
        await game.add_player("Alice")
        game._players["Alice"].bet = 50

        game._players["Alice"].hand = [
            {"rank": "10", "suit": "Hearts"},
            {"rank": "Q", "suit": "Diamonds"},
        ]

        game.dealer_hand = [
            {"rank": "10", "suit": "Clubs"},
            {"rank": "8", "suit": "Hearts"},
        ]

        initial_balance = game._players["Alice"].balance
        await game.resolve_round()

        msgs = game._sio.messages
        assert any("wins on hand" in msg for msg in msgs)
        assert game._players["Alice"].balance == initial_balance + 50

    @pytest.mark.asyncio
    async def test_resolve_round_tie(self, game):
        game.start_game()
        await game.add_player("Alice")
        game._players["Alice"].bet = 50

        game._players["Alice"].hand = [
            {"rank": "10", "suit": "Hearts"},
            {"rank": "8", "suit": "Diamonds"},
        ]

        game.dealer_hand = [
            {"rank": "9", "suit": "Clubs"},
            {"rank": "9", "suit": "Hearts"},
        ]

        initial_balance = game._players["Alice"].balance
        await game.resolve_round()

        msgs = game._sio.messages
        assert any("it's a tie" in msg for msg in msgs)
        assert game._players["Alice"].balance == initial_balance

    @pytest.mark.asyncio
    async def test_all_players_done(self, game):
        game.start_game()
        await game.add_player("Alice")
        await game.add_player("Bob")

        for p in game._players.values():
            p.finished = False
        assert game.all_players_done() is False

        for p in game._players.values():
            p.finished = True
        assert game.all_players_done() is True

    @pytest.mark.asyncio
    async def test_place_bet_valid(self, game):
        game.start_game()
        await game.add_player("Alice")
        await game.place_bet("Alice", "30")

        msgs = game._sio.messages
        assert "Alice bet set to 30." in msgs[1]
        assert game._players["Alice"].bet == 30

    @pytest.mark.asyncio
    async def test_place_bet_invalid_amount(self, game):
        game.start_game()
        await game.add_player("Alice")
        await game.place_bet("Alice", "200")

        msgs = game._sio.messages
        assert any("Invalid bet" in msg for msg in msgs)
        assert game._players["Alice"].bet == 0

    @pytest.mark.asyncio
    async def test_place_bet_invalid_input(self, game):
        game.start_game()
        await game.add_player("Alice")
        await game.place_bet("Alice", "notanumber")

        msgs = game._sio.messages
        assert any("Invalid input" in msg for msg in msgs)
        assert game._players["Alice"].bet == 0

    def test_state_getter_setter(self, game):
        game.state = "idle"
        assert game.state == "idle"

        game.state = "joining"
        assert game.state == "joining"

        game.state = "playing"
        assert game.state == "playing"

        with pytest.raises(InvalidBlackjackState):
            game.state = "finished"
