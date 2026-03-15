from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Iterable

from kaboom import (
    CallKaboom,
    Card,
    CloseReaction,
    Discard,
    Draw,
    OpeningPeek,
    ReactDiscardOtherCard,
    ReactDiscardOwnCard,
    Replace,
    ResolvePendingPower,
    UsePower,
)
from kaboom.players.player import Player


def render_hand_for_viewer(player: Player, viewer: Player, reveal_all: bool) -> str:
    cards = []
    for index, card in enumerate(player.hand):
        if reveal_all or player.revealed:
            cards.append(f"[{index}:{format_card(card)}]")
            continue
        remembered = viewer.memory.get((player.id, index))
        cards.append(f"[{index}:{format_card(remembered) if remembered else '??'}]")
    return " ".join(cards) if cards else "(empty)"


def render_score_for_viewer(player: Player, viewer: Player, reveal_all: bool) -> str:
    if reveal_all or player.revealed:
        return str(player.total_score())
    known = [viewer.memory.get((player.id, index)) for index in range(len(player.hand))]
    if all(card is not None for card in known):
        return str(sum(card.score_value for card in known))
    return "?"


def describe_action(players: list[Player], action) -> str:
    actor = player_name(players, action.actor_id)

    if isinstance(action, Draw):
        return f"{actor}: draw from deck"
    if isinstance(action, Discard):
        return f"{actor}: discard drawn card"
    if isinstance(action, Replace):
        return f"{actor}: replace hand card at index {action.target_index}"
    if isinstance(action, CallKaboom):
        return f"{actor}: call Kaboom"
    if isinstance(action, CloseReaction):
        return f"{actor}: close reaction window"
    if isinstance(action, ResolvePendingPower):
        return f"{actor}: resolve pending power"
    if isinstance(action, ReactDiscardOwnCard):
        return (
            f"{actor}: attempt discard own card at index {action.card_index} "
            "(wrong guess = reveal + penalty)"
        )
    if isinstance(action, ReactDiscardOtherCard):
        target = player_name(players, action.target_player_id)
        return (
            f"{actor}: attempt discard {target}[{action.target_card_index}] "
            f"and give own card {action.give_card_index} on success"
        )
    if isinstance(action, UsePower):
        return f"{actor}: discard for power `{action.power_name.value}`"
    if isinstance(action, OpeningPeek):
        return f"{actor}: opening peek"
    return repr(action)


def format_result(result: object) -> str:
    fragments: list[str] = []
    if is_dataclass(result):
        items = [(field.name, getattr(result, field.name)) for field in fields(result)]
    else:
        items = result.__dict__.items()
    for field_name, value in items:
        if value is None or value is False:
            continue
        if isinstance(value, Card):
            value = format_card(value)
        fragments.append(f"{field_name}={value}")
    return " | ".join(fragments) if fragments else repr(result)


def format_memory_entries(entries: Iterable[tuple[tuple[int, int], Card]]) -> str:
    parts = []
    for (player_id, card_index), card in sorted(entries):
        parts.append(f"P{player_id}[{card_index}]={format_card(card)}")
    return "\n".join(parts)


def format_card(card: Card | None) -> str:
    if card is None:
        return "-"
    return f"{card.rank.value}{normalize_suit(card.suit.value)}"


def player_label(player: Player) -> str:
    return f"P{player.id} {player.name}"


def player_name(players: list[Player], player_id: int) -> str:
    return next(player_label(player) for player in players if player.id == player_id)


def normalize_suit(suit: str) -> str:
    return {
        "♠": "S",
        "♥": "H",
        "♦": "D",
        "♣": "C",
        "â™ ": "S",
        "â™¥": "H",
        "â™¦": "D",
        "â™£": "C",
        "Ã¢â„¢Â ": "S",
        "Ã¢â„¢Â¥": "H",
        "Ã¢â„¢Â¦": "D",
        "Ã¢â„¢Â£": "C",
    }.get(suit, suit)
