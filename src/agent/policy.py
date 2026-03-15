from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kaboom import (
    CallKaboom,
    Discard,
    CloseReaction,
    Draw,
    GamePhase,
    ReactDiscardOtherCard,
    ReactDiscardOwnCard,
    Replace,
    ResolvePendingPower,
    UsePower,
    get_valid_actions,
)
from kaboom.game.engine import GameEngine
from kaboom.powers.types import PowerType


@dataclass(frozen=True)
class AgentDecision:
    action: Any
    note: str
    payload: dict[str, int | None] | None = None


def choose_agent_decision(engine: GameEngine, actor_id: int) -> AgentDecision | None:
    state = engine.state
    actions = [action for action in get_valid_actions(state) if getattr(action, "actor_id", None) == actor_id]
    if not actions:
        return None

    if state.phase == GamePhase.OPENING_PEEK:
        return _choose_opening_peek(engine, actor_id)

    if state.phase == GamePhase.TURN_DRAW:
        return _choose_turn_draw(engine, actor_id, actions)

    if state.phase == GamePhase.TURN_RESOLVE:
        return _choose_turn_resolve(engine, actor_id, actions)

    if state.phase == GamePhase.REACTION:
        return _choose_reaction(engine, actor_id, actions)

    return None


def _choose_opening_peek(engine: GameEngine, actor_id: int) -> AgentDecision:
    required = engine.state.required_opening_peek_count(actor_id)
    indices = tuple(range(required))
    return AgentDecision(action=("opening_peek", actor_id, indices), note=f"opening peek {indices}")


def _choose_turn_draw(engine: GameEngine, actor_id: int, actions: list[Any]) -> AgentDecision:
    player = engine.state.resolve_player(actor_id)
    if any(isinstance(action, CallKaboom) for action in actions):
        known_own = [player.memory.get((actor_id, index)) for index in range(len(player.hand))]
        if len(player.hand) <= 1 or (known_own and all(card is not None for card in known_own) and sum(card.score_value for card in known_own) <= 5):
            action = next(action for action in actions if isinstance(action, CallKaboom))
            return AgentDecision(action=action, note="call Kaboom on low known score")

    action = next(action for action in actions if isinstance(action, Draw))
    return AgentDecision(action=action, note="draw from deck")


def _choose_turn_resolve(engine: GameEngine, actor_id: int, actions: list[Any]) -> AgentDecision:
    state = engine.state
    drawn_card = state.drawn_card
    player = state.resolve_player(actor_id)
    if drawn_card is None:
        return None

    use_power_actions = [action for action in actions if isinstance(action, UsePower)]
    for action in use_power_actions:
        payload = _choose_power_payload(engine, action)
        if payload is not None:
            return AgentDecision(action=action, note=f"use power {action.power_name.value}", payload=payload)

    replace_actions = [action for action in actions if isinstance(action, Replace)]
    known_own = [
        (index, player.memory.get((actor_id, index)))
        for index in range(len(player.hand))
    ]

    known_worse = [
        (index, card.score_value)
        for index, card in known_own
        if card is not None and drawn_card.score_value < card.score_value
    ]
    if known_worse:
        target_index = max(known_worse, key=lambda item: item[1])[0]
        action = next(action for action in replace_actions if action.target_index == target_index)
        return AgentDecision(action=action, note=f"replace known higher card at index {target_index}")

    if drawn_card.score_value <= 3:
        unknown_indices = [index for index, card in known_own if card is None]
        if unknown_indices:
            target_index = unknown_indices[0]
            action = next(action for action in replace_actions if action.target_index == target_index)
            return AgentDecision(action=action, note=f"replace unknown card with low draw at index {target_index}")

    action = next(action for action in actions if isinstance(action, Discard))
    return AgentDecision(action=action, note="discard drawn card")


def _choose_reaction(engine: GameEngine, actor_id: int, actions: list[Any]) -> AgentDecision:
    state = engine.state
    player = state.resolve_player(actor_id)

    resolve = next((action for action in actions if isinstance(action, ResolvePendingPower)), None)
    if resolve is not None:
        return AgentDecision(action=resolve, note="resolve pending power")

    successful_reactions: list[tuple[int, AgentDecision]] = []
    for action in actions:
        if isinstance(action, ReactDiscardOwnCard):
            remembered = player.memory.get((actor_id, action.card_index))
            if remembered is not None and remembered.rank.value == state.reaction_rank:
                successful_reactions.append(
                    (
                        remembered.score_value,
                        AgentDecision(action=action, note=f"react with own known match at index {action.card_index}"),
                    )
                )
        elif isinstance(action, ReactDiscardOtherCard):
            remembered = player.memory.get((action.target_player_id, action.target_card_index))
            given = player.memory.get((actor_id, action.give_card_index))
            if remembered is not None and remembered.rank.value == state.reaction_rank:
                given_score = given.score_value if given is not None else 0
                successful_reactions.append(
                    (
                        given_score,
                        AgentDecision(
                            action=action,
                            note=(
                                f"react with known match at "
                                f"P{action.target_player_id}[{action.target_card_index}]"
                            ),
                        ),
                    )
                )

    if successful_reactions:
        return max(successful_reactions, key=lambda item: item[0])[1]

    return None


def _choose_power_payload(engine: GameEngine, action: UsePower) -> dict[str, int | None] | None:
    state = engine.state
    actor = state.resolve_player(action.actor_id)
    other_players = [player for player in state.players if player.id != actor.id and player.active and len(player.hand) > 0]

    if action.power_name == PowerType.SEE_SELF:
        unknown_indices = [index for index in range(len(actor.hand)) if actor.memory.get((actor.id, index)) is None]
        if not unknown_indices:
            return None
        return {
            "target_player_id": None,
            "target_card_index": unknown_indices[0],
            "second_target_player_id": None,
            "second_target_card_index": None,
        }

    if action.power_name == PowerType.SEE_OTHER:
        for other in other_players:
            unknown_indices = [index for index in range(len(other.hand)) if actor.memory.get((other.id, index)) is None]
            if unknown_indices:
                return {
                    "target_player_id": other.id,
                    "target_card_index": unknown_indices[0],
                    "second_target_player_id": None,
                    "second_target_card_index": None,
                }
        return None

    if action.power_name in {PowerType.BLIND_SWAP, PowerType.SEE_AND_SWAP}:
        own_candidates = _known_own_cards(actor)
        other_candidates = _known_other_cards(actor, other_players)

        if action.power_name == PowerType.BLIND_SWAP:
            for own_index, own_card in own_candidates:
                for other_player_id, other_index, other_card in other_candidates:
                    if own_card.score_value > other_card.score_value:
                        return {
                            "target_player_id": actor.id,
                            "target_card_index": own_index,
                            "second_target_player_id": other_player_id,
                            "second_target_card_index": other_index,
                        }
            return None

        own_index = None
        for index, card in own_candidates:
            if own_index is None or card.score_value > actor.memory[(actor.id, own_index)].score_value:
                own_index = index
        if own_index is None and actor.hand:
            own_index = 0

        target_choice = None
        for other in other_players:
            for index in range(len(other.hand)):
                remembered = actor.memory.get((other.id, index))
                if remembered is None:
                    target_choice = (other.id, index)
                    break
            if target_choice is not None:
                break

        if target_choice is None and other_candidates:
            best = min(other_candidates, key=lambda item: item[2].score_value)
            target_choice = (best[0], best[1])

        if own_index is None or target_choice is None:
            return None

        return {
            "target_player_id": actor.id,
            "target_card_index": own_index,
            "second_target_player_id": target_choice[0],
            "second_target_card_index": target_choice[1],
        }

    return None


def _known_own_cards(actor) -> list[tuple[int, Any]]:
    known: list[tuple[int, Any]] = []
    for index in range(len(actor.hand)):
        card = actor.memory.get((actor.id, index))
        if card is not None:
            known.append((index, card))
    return known


def _known_other_cards(actor, other_players) -> list[tuple[int, int, Any]]:
    known: list[tuple[int, int, Any]] = []
    for other in other_players:
        for index in range(len(other.hand)):
            card = actor.memory.get((other.id, index))
            if card is not None:
                known.append((other.id, index, card))
    return known
