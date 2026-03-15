from kaboom import ActionResult, Card, Draw, Player, Rank, ReactDiscardOwnCard, Replace, Suit

from src.ui.presenter import (
    describe_action,
    format_card,
    format_memory_entries,
    format_result,
    render_hand_for_viewer,
    render_score_for_viewer,
)


def make_card(rank: Rank, suit: Suit) -> Card:
    return Card(rank=rank, suit=suit)


def make_players():
    p0 = Player(id=0, name="P1")
    p1 = Player(id=1, name="P2")
    p0.hand = [make_card(Rank.A, Suit.SPADES), make_card(Rank.FIVE, Suit.HEARTS)]
    p1.hand = [make_card(Rank.TEN, Suit.CLUBS), make_card(Rank.K, Suit.DIAMONDS)]
    return p0, p1


def test_render_hand_for_viewer_uses_memory_until_revealed():
    viewer, other = make_players()
    viewer.remember(other.id, 1, other.hand[1])

    assert render_hand_for_viewer(other, viewer, reveal_all=False) == "[0:??] [1:KD]"


def test_render_score_for_viewer_shows_total_when_all_known():
    viewer, other = make_players()
    viewer.remember(other.id, 0, other.hand[0])
    viewer.remember(other.id, 1, other.hand[1])

    assert render_score_for_viewer(other, viewer, reveal_all=False) == "10"


def test_describe_action_includes_penalty_hint_for_reaction_guess():
    players = list(make_players())
    action = ReactDiscardOwnCard(actor_id=0, card_index=1)

    assert "wrong guess = reveal + penalty" in describe_action(players, action)


def test_format_result_formats_cards_and_flags():
    result = ActionResult(
        action="draw",
        actor_id=0,
        card=make_card(Rank.J, Suit.SPADES),
        phase_before="turn_draw",
        phase_after="turn_resolve",
        next_player_id=0,
        pending_power_created=False,
    )

    formatted = format_result(result)

    assert "action=draw" in formatted
    assert "card=JS" in formatted
    assert "phase_after=turn_resolve" in formatted


def test_format_memory_entries_orders_positions():
    viewer, other = make_players()
    viewer.remember(other.id, 1, other.hand[1])
    viewer.remember(other.id, 0, other.hand[0])

    assert format_memory_entries(viewer.memory.items()) == "P1[0]=10C\nP1[1]=KD"


def test_format_card_normalizes_suit():
    assert format_card(make_card(Rank.A, Suit.HEARTS)) == "AH"


def test_describe_basic_actions():
    players = list(make_players())

    assert describe_action(players, Draw(actor_id=0)) == "P0 P1: draw from deck"
    assert describe_action(players, Replace(actor_id=1, target_index=0)) == "P1 P2: replace hand card at index 0"
