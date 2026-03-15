from kaboom import Card, GameEngine, Rank, Suit
from kaboom.game.actions import Discard, Replace, ResolvePendingPower, UsePower
from kaboom.game.game_state import GameState
from kaboom.game.phases import GamePhase
from kaboom.players.player import Player
from kaboom.powers.types import PowerType

from src.agent.policy import choose_agent_decision


def make_card(rank: Rank, suit: Suit) -> Card:
    return Card(rank=rank, suit=suit)


def test_agent_opening_peek_chooses_first_two_indices():
    engine = GameEngine(game_id=1, num_players=2, hand_size=4)

    decision = choose_agent_decision(engine, actor_id=0)

    assert decision is not None
    assert decision.action == ("opening_peek", 0, (0, 1))


def test_agent_replaces_known_higher_card_with_lower_draw():
    p0 = Player(id=0, name="Agent", hand=[make_card(Rank.K, Suit.SPADES), make_card(Rank.THREE, Suit.HEARTS)])
    p1 = Player(id=1, name="Human", hand=[make_card(Rank.FIVE, Suit.CLUBS), make_card(Rank.SEVEN, Suit.DIAMONDS)])
    p0.remember(0, 0, p0.hand[0])
    p0.remember(0, 1, p0.hand[1])
    state = GameState(
        players=[p0, p1],
        deck=[],
        phase=GamePhase.TURN_RESOLVE,
        drawn_card=make_card(Rank.TWO, Suit.CLUBS),
    )
    engine = GameEngine(game_id=1, num_players=2, hand_size=4)
    engine.state = state

    decision = choose_agent_decision(engine, actor_id=0)

    assert decision is not None
    assert isinstance(decision.action, Replace)
    assert decision.action.target_index == 0


def test_agent_uses_see_other_on_unknown_opponent_card():
    p0 = Player(id=0, name="Agent", hand=[make_card(Rank.FOUR, Suit.SPADES)])
    p1 = Player(id=1, name="Human", hand=[make_card(Rank.FIVE, Suit.CLUBS), make_card(Rank.SEVEN, Suit.DIAMONDS)])
    state = GameState(
        players=[p0, p1],
        deck=[],
        phase=GamePhase.TURN_RESOLVE,
        drawn_card=make_card(Rank.NINE, Suit.HEARTS),
    )
    engine = GameEngine(game_id=1, num_players=2, hand_size=4)
    engine.state = state

    decision = choose_agent_decision(engine, actor_id=0)

    assert decision is not None
    assert isinstance(decision.action, UsePower)
    assert decision.action.power_name == PowerType.SEE_OTHER
    assert decision.payload is not None
    assert decision.payload["target_player_id"] == 1
    assert decision.payload["target_card_index"] == 0


def test_agent_resolves_own_pending_power_before_other_reaction_steps():
    p0 = Player(id=0, name="Agent", hand=[make_card(Rank.FOUR, Suit.SPADES)])
    p1 = Player(id=1, name="Human", hand=[make_card(Rank.FIVE, Suit.CLUBS)])
    state = GameState(
        players=[p0, p1],
        deck=[],
        phase=GamePhase.REACTION,
        reaction_open=True,
        reaction_rank="7",
    )
    state.pending_power_action = UsePower(
        actor_id=0,
        power_name=PowerType.SEE_SELF,
        source_card=make_card(Rank.SEVEN, Suit.HEARTS),
        target_player_id=None,
        target_card_index=0,
    )
    engine = GameEngine(game_id=1, num_players=2, hand_size=4)
    engine.state = state

    decision = choose_agent_decision(engine, actor_id=0)

    assert decision is not None
    assert isinstance(decision.action, ResolvePendingPower)


def test_agent_reaction_returns_none_when_it_only_has_close_available():
    p0 = Player(id=0, name="Agent", hand=[make_card(Rank.FOUR, Suit.SPADES)])
    p1 = Player(id=1, name="Human", hand=[make_card(Rank.FIVE, Suit.CLUBS)])
    state = GameState(
        players=[p0, p1],
        deck=[],
        phase=GamePhase.REACTION,
        reaction_open=True,
        reaction_rank="7",
    )
    engine = GameEngine(game_id=1, num_players=2, hand_size=4)
    engine.state = state

    decision = choose_agent_decision(engine, actor_id=0)

    assert decision is None


def test_agent_discards_when_no_better_replace_or_power_exists():
    p0 = Player(id=0, name="Agent", hand=[make_card(Rank.TWO, Suit.SPADES), make_card(Rank.THREE, Suit.HEARTS)])
    p1 = Player(id=1, name="Human", hand=[make_card(Rank.FIVE, Suit.CLUBS), make_card(Rank.SEVEN, Suit.DIAMONDS)])
    p0.remember(0, 0, p0.hand[0])
    p0.remember(0, 1, p0.hand[1])
    state = GameState(
        players=[p0, p1],
        deck=[],
        phase=GamePhase.TURN_RESOLVE,
        drawn_card=make_card(Rank.Q, Suit.HEARTS),
    )
    engine = GameEngine(game_id=1, num_players=2, hand_size=4)
    engine.state = state

    decision = choose_agent_decision(engine, actor_id=0)

    assert decision is not None
    assert isinstance(decision.action, Discard)
