from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Iterable

import streamlit as st
from kaboom import (
    CallKaboom,
    CloseReaction,
    Discard,
    Draw,
    GameEngine,
    GamePhase,
    OpeningPeek,
    ReactDiscardOtherCard,
    ReactDiscardOwnCard,
    Replace,
    ResolvePendingPower,
    UsePower,
    apply_action,
    get_valid_actions,
)
from kaboom.exceptions import InvalidActionError
from kaboom.players.player import Player
from kaboom.powers.types import PowerType

from src.agent import choose_agent_decision

from .presenter import (
    action_key,
    describe_action,
    format_card,
    format_memory_entries,
    format_result,
    player_label,
    player_name,
    render_hand_for_viewer,
    render_score_for_viewer,
)

MAX_PLAYERS = 6
DEFAULT_PLAYERS = 4
DEFAULT_HAND_SIZE = 4
DEFAULT_EVENT_LOG_LIMIT = 24
PLAYER_COLUMNS = 3
RULES_PATH = Path(__file__).resolve().parents[2] / "docs" / "GAME_RULES.md"
EVENT_LOG_DIR = Path(__file__).resolve().parents[2] / "backend" / "event_logs"


def ensure_app_state() -> None:
    st.session_state.setdefault("page", "landing")
    st.session_state.setdefault("engine", None)
    st.session_state.setdefault("selected_viewer_id", 0)
    st.session_state.setdefault("show_full_state", False)
    st.session_state.setdefault("event_log", [])
    st.session_state.setdefault("power_reveal", [])
    st.session_state.setdefault("player_control", {})
    st.session_state.setdefault("agent_mode", True)
    st.session_state.setdefault("human_player_id", 0)
    st.session_state.setdefault("reaction_passes", {})
    st.session_state.setdefault("reaction_window_key", None)
    st.session_state.setdefault("event_log_path", None)
    st.session_state.setdefault("queued_resolve_pending_power_actor_id", None)
    st.session_state.setdefault("previous_window_signature", None)
    st.session_state.setdefault("window_notice", None)


def landing_page() -> None:
    ensure_app_state()
    _inject_styles()

    st.markdown(
        """
        <div class="hero-shell">
            <div class="eyebrow">Kaboom Streamlit</div>
            <h1>Local Engine Inspector</h1>
            <p>
                Browser UI for inspecting the real <code>kaboom-engine</code>.
                One action at a time, no duplicate rules, no fake state machine.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    controls = st.columns([1, 1, 2], gap="medium")
    with controls[0]:
        _render_rules_button("View Rules")

    agent_mode = st.toggle("Play against local agent", value=st.session_state.agent_mode)
    st.session_state.agent_mode = agent_mode

    top_cols = st.columns([1, 1], gap="large")
    with top_cols[0]:
        if agent_mode:
            num_players = 2
            st.number_input("Players", min_value=2, max_value=2, value=2, disabled=True)
        else:
            num_players = st.slider("Players", min_value=2, max_value=MAX_PLAYERS, value=DEFAULT_PLAYERS)
    with top_cols[1]:
        hand_size = st.slider("Hand size", min_value=2, max_value=6, value=DEFAULT_HAND_SIZE)

    human_seat = 0
    if agent_mode:
        human_seat = st.radio(
            "Human seat",
            options=[0, 1],
            format_func=lambda seat: f"Seat {seat + 1}",
            horizontal=True,
        )

    with st.form("new_game_form"):
        st.markdown("### Table Setup")
        player_names = []
        for index in range(num_players):
            default_name = f"Player {index}"
            if agent_mode and index != human_seat:
                default_name = "Agent"
            player_names.append(
                st.text_input(
                    f"Player {index + 1}",
                    value=default_name,
                    key=f"landing_player_{index}",
                    disabled=agent_mode and index != human_seat,
                )
            )
        submitted = st.form_submit_button("Start Local Inspector")

    if submitted:
        engine = GameEngine(game_id=0, num_players=num_players, hand_size=hand_size)
        for index, player in enumerate(engine.state.players):
            player.name = player_names[index].strip() or f"Player {index}"

        player_control = {player.id: "human" for player in engine.state.players}
        if agent_mode:
            for player in engine.state.players:
                player_control[player.id] = "human" if player.id == human_seat else "agent"

        st.session_state.engine = engine
        st.session_state.player_control = player_control
        st.session_state.human_player_id = human_seat
        st.session_state.selected_viewer_id = human_seat if agent_mode else engine.state.players[0].id
        st.session_state.show_full_state = False
        st.session_state.power_reveal = []
        _set_event_log_path(engine)
        st.session_state.event_log = []
        _append_event_log(
            (
                f"Started local inspector with {num_players} players and hand size {hand_size}."
                if not agent_mode
                else f"Started human vs agent inspector with human seat {human_seat + 1} and hand size {hand_size}."
            )
        )
        st.session_state.page = "game"
        st.rerun()


def game_page() -> None:
    ensure_app_state()
    _inject_styles()

    engine: GameEngine | None = st.session_state.engine
    if engine is None:
        st.session_state.page = "landing"
        st.rerun()
        return

    _sync_reaction_pass_state(engine)
    _process_queued_actions(engine)
    current_signature = _state_window_signature(engine)
    _update_window_notice(engine, current_signature)

    st.markdown(
        """
        <div class="page-head">
            <div>
                <div class="eyebrow">Milestone 2</div>
                <h1>Kaboom Engine Inspector</h1>
            </div>
            <div class="page-note">Single-browser debugging surface backed directly by <code>kaboom-engine</code>.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    header_controls = st.columns([1, 3], gap="medium")
    with header_controls[0]:
        _render_rules_button("Rules")

    _render_sidebar(engine)
    _render_game_summary(engine)

    col_left, col_right = st.columns([1.65, 1.0], gap="large")

    with col_left:
        _render_player_table(engine)
        _render_actions(engine)

    with col_right:
        _render_power_reveal_panel()
        _render_memory_panels(engine)
        _render_event_log()

    st.session_state.previous_window_signature = current_signature
    _auto_step_agents(engine)


def _render_sidebar(engine: GameEngine) -> None:
    state = engine.state
    player_options = {player_label(player): player.id for player in state.players}

    with st.sidebar:
        st.header("Inspector")
        viewer_label = st.selectbox(
            "Perspective",
            options=list(player_options.keys()),
            index=_viewer_index(state.players, st.session_state.selected_viewer_id),
        )
        st.session_state.selected_viewer_id = player_options[viewer_label]
        st.session_state.show_full_state = st.checkbox(
            "Reveal full state",
            value=st.session_state.show_full_state,
            help="Development toggle. Shows all hidden cards regardless of memory.",
        )

        st.markdown("---")
        st.caption("This inspector executes one engine action at a time.")
        st.caption("During contested discard windows, the first applied action wins priority.")
        if st.session_state.agent_mode:
            st.caption("Agent seats auto-play until a human decision is required.")
            st.caption(
                f"Human controls: {player_name(state.players, st.session_state.human_player_id)} "
                f"| Viewing: {player_name(state.players, st.session_state.selected_viewer_id)}"
            )

        if st.button("Reset To Landing"):
            st.session_state.engine = None
            st.session_state.event_log = []
            st.session_state.power_reveal = []
            st.session_state.player_control = {}
            st.session_state.agent_mode = True
            st.session_state.human_player_id = 0
            st.session_state.reaction_passes = {}
            st.session_state.reaction_window_key = None
            st.session_state.event_log_path = None
            st.session_state.queued_resolve_pending_power_actor_id = None
            st.session_state.page = "landing"
            st.rerun()


def _render_game_summary(engine: GameEngine) -> None:
    state = engine.state
    current = state.current_player()

    top_discard = format_card(state.top_discard())
    drawn = format_card(state.drawn_card)
    pending_power = "-"
    if state.pending_power_action is not None:
        pending_power = (
            f"{state.pending_power_action.power_name.value} "
            f"(actor={player_name(state.players, state.pending_power_action.actor_id)})"
        )

    st.subheader("Game State")
    metrics_a = st.columns(4)
    metrics_b = st.columns(3)
    metrics_a[0].metric("Round", state.round_number)
    metrics_a[1].metric("Phase", state.phase.value)
    metrics_a[2].metric("Current", player_label(current))
    metrics_a[3].metric("Deck", len(state.deck))
    metrics_b[0].metric("Discard Top", top_discard)
    metrics_b[1].metric("Drawn Card", drawn)
    metrics_b[2].metric("Pending Power", pending_power)

    if state.phase == GamePhase.OPENING_PEEK:
        st.info("Setup phase: each player chooses exactly two of their own cards to remember.")
    if state.reaction_open:
        st.info(
            f"Reaction open for rank `{state.reaction_rank}`. "
            "Correct claims succeed. Wrong claims reveal the card to everyone and add a penalty card."
        )
    pending_hint = _format_pending_power_hint(engine)
    if pending_hint:
        st.warning(pending_hint)
    if state.kaboom_called_by is not None:
        st.warning(f"Kaboom called by {player_name(state.players, state.kaboom_called_by)}.")
    if st.session_state.power_reveal:
        st.info("A private reveal was recorded and can be used immediately in this same discard window.")
    if state.phase == GamePhase.GAME_OVER:
        st.success(f"Winner: {engine.get_winner()} | Scores: {engine.get_scores()}")


def _render_player_table(engine: GameEngine) -> None:
    state = engine.state
    viewer = state.resolve_player(st.session_state.selected_viewer_id)

    st.subheader("Table")
    st.caption(
        f"Perspective: {player_label(viewer)}. Hidden cards render from that player's memory unless full-state reveal is enabled."
    )
    for row_start in range(0, len(state.players), PLAYER_COLUMNS):
        row_players = state.players[row_start : row_start + PLAYER_COLUMNS]
        columns = st.columns(len(row_players), gap="large")
        for column, player in zip(columns, row_players):
            with column:
                _render_player_card(player, viewer, state.current_player().id, st.session_state.show_full_state)


def _render_memory_panels(engine: GameEngine) -> None:
    state = engine.state
    viewer = state.resolve_player(st.session_state.selected_viewer_id)

    st.subheader("Inspector Panels")
    memory_tab, all_memory_tab, snapshot_tab = st.tabs(["Viewer Memory", "All Memories", "Engine Snapshot"])

    with memory_tab:
        st.caption(f"Visible knowledge for {player_label(viewer)}.")
        viewer_memory = format_memory_entries(viewer.memory.items())
        st.code(viewer_memory or "(empty)")

    with all_memory_tab:
        for player in state.players:
            st.markdown(f"**{player_label(player)}**")
            st.code(format_memory_entries(player.memory.items()) or "(empty)")

    with snapshot_tab:
        st.json(
            {
                "phase": state.phase.value,
                "round_number": state.round_number,
                "current_player_id": state.current_player().id,
                "reaction_rank": state.reaction_rank,
                "reaction_open": state.reaction_open,
                "reaction_initiator": state.reaction_initiator,
                "pending_power": repr(state.pending_power_action),
                "kaboom_called_by": state.kaboom_called_by,
                "instant_winner": state.instant_winner,
            }
        )


def _render_actions(engine: GameEngine) -> None:
    state = engine.state
    actions = _app_visible_actions(engine, get_valid_actions(state))
    if st.session_state.agent_mode:
        actions = [
            action
            for action in actions
            if _control_for_actor(_action_actor_id(engine, action)) == "human"
        ]

    st.subheader("Legal Actions")
    _render_window_notice()
    if not actions:
        if st.session_state.agent_mode and engine.state.phase == GamePhase.REACTION:
            st.caption("Every action below comes from `get_valid_actions(state)`.")
            _render_phase_help(state.phase)
            with st.container(border=True):
                _render_pass_panel(engine)
                if _reaction_actor_passed(st.session_state.human_player_id):
                    st.info("Waiting for agent action.")
                else:
                    st.info("You can pass on this discard event or make a visible legal reaction if one appears.")
            return

        if st.session_state.agent_mode and engine.state.phase != GamePhase.GAME_OVER:
            st.info("Waiting for agent action.")
        else:
            st.info("No legal actions available.")
        return

    st.caption("Every action below comes from `get_valid_actions(state)`.")
    _render_phase_help(state.phase)

    with st.container(border=True):
        if state.phase == GamePhase.OPENING_PEEK:
            _render_opening_peek_panel(engine)
            return

        if state.pending_power_action is not None:
            _render_pending_power_panel(engine, actions)

        if state.phase == GamePhase.REACTION:
            _render_reaction_status(engine)
            _render_pass_panel(engine)

        for index, action in enumerate(actions):
            if isinstance(action, ResolvePendingPower):
                continue
            if isinstance(action, CloseReaction):
                continue
            if isinstance(action, UsePower):
                _render_use_power_action(engine, action, index)
                continue
            _render_direct_action(engine, action, index)


def _render_phase_help(phase: GamePhase) -> None:
    if phase == GamePhase.TURN_DRAW:
        st.caption("Turn draw: draw from deck or call Kaboom.")
    elif phase == GamePhase.TURN_RESOLVE:
        st.caption("Turn resolve: discard, replace, or discard for power.")
    elif phase == GamePhase.REACTION:
        st.caption(
            "Reaction window: first applied action wins the contested discard event. "
            "Informational powers reveal immediately when resolved, and the same window stays open."
        )


def _render_direct_action(engine: GameEngine, action, index: int) -> None:
    label = describe_action(engine.state.players, action)
    if st.button(label, key=action_key(action, "action_button"), use_container_width=True):
        try:
            results = _execute_action(engine, action)
            _record_results(results)
        except InvalidActionError as exc:
            st.error(str(exc))
        st.rerun()


def _render_pending_power_panel(engine: GameEngine, actions) -> None:
    pending = engine.state.pending_power_action
    if pending is None:
        return

    resolve_action = next((action for action in actions if isinstance(action, ResolvePendingPower)), None)
    st.markdown("### Pending Power")
    st.warning(
        "This discard event has a claimed power. Resolve it now to reveal/apply the power while keeping the same "
        "reaction window open."
    )
    st.markdown(f"`{_describe_pending_resolution(engine)}`")
    if resolve_action is not None:
        if st.button("Resolve Pending Power Now", key="resolve_pending_power_button", use_container_width=True):
            st.session_state.queued_resolve_pending_power_actor_id = resolve_action.actor_id
            st.rerun()


def _render_pass_panel(engine: GameEngine) -> None:
    if not st.session_state.agent_mode:
        return

    actor_id = st.session_state.human_player_id
    if _control_for_actor(actor_id) != "human":
        return

    if _reaction_actor_passed(actor_id):
        st.caption("You have already passed for this discard event.")
        return

    if st.button("Pass Reaction", key="pass_reaction_button", use_container_width=True):
        _mark_reaction_pass(actor_id, engine)
        actions = _app_visible_actions(engine, get_valid_actions(engine.state))
        if _can_finalize_reaction_window(actions):
            _finalize_reaction_window(engine)
        st.rerun()


def _render_reaction_status(engine: GameEngine) -> None:
    if not st.session_state.agent_mode:
        return

    st.markdown("### Reaction Status")
    cols = st.columns(len(engine.state.players))
    for col, player in zip(cols, engine.state.players):
        with col:
            if _reaction_actor_passed(player.id):
                status = "passed"
            elif _player_can_still_react(engine, player.id):
                status = "waiting"
            else:
                status = "done"
            st.caption(f"{player_label(player)}: {status}")


def _render_opening_peek_panel(engine: GameEngine) -> None:
    state = engine.state
    player = state.current_player()
    required = engine.state.required_opening_peek_count(player.id)

    with st.form("opening_peek_form"):
        st.markdown(f"**{player_label(player)} opening peek**")
        chosen = st.multiselect(
            "Choose cards to remember",
            options=list(range(len(player.hand))),
            default=list(range(required)),
            format_func=lambda card_index: f"Index {card_index}",
            max_selections=required,
            key="opening_peek_indices",
        )
        submitted = st.form_submit_button(f"Apply opening peek for {player.name}")

    if submitted:
        try:
            results = engine.perform_opening_peek(player.id, tuple(chosen))
            _record_results(results)
        except InvalidActionError as exc:
            st.error(str(exc))
        st.rerun()


def _render_use_power_action(engine: GameEngine, action: UsePower, index: int) -> None:
    state = engine.state
    actor = state.resolve_player(action.actor_id)
    other_players = [player for player in state.players if player.id != actor.id and player.active and len(player.hand) > 0]
    can_submit = True
    key_base = action_key(action, "use_power")

    with st.form(f"{key_base}_form"):
        st.markdown(f"**{player_label(actor)} use power: `{action.power_name.value}`**")
        st.caption(
            f"Source card: {format_card(action.source_card)}. "
            "The card is discarded first; power and reaction then compete for priority."
        )
        payload, can_submit = _build_power_payload_inputs(state, action, key_base, other_players)
        submitted = st.form_submit_button(f"Discard for power: {action.power_name.value}", disabled=not can_submit)

    if submitted:
        try:
            results = engine.use_power(
                power_name=action.power_name,
                player=actor.id,
                target_player_id=payload["target_player_id"],
                target_card_index=payload["target_card_index"],
                second_target_player_id=payload["second_target_player_id"],
                second_target_card_index=payload["second_target_card_index"],
            )
            _record_results(results)
        except InvalidActionError as exc:
            st.error(str(exc))
        st.rerun()


def _build_power_payload_inputs(
    state,
    action: UsePower,
    key_base: str,
    other_players,
) -> tuple[dict[str, int | None], bool]:
    actor = state.resolve_player(action.actor_id)
    other_player_ids = [player.id for player in other_players]

    payload = {
        "target_player_id": None,
        "target_card_index": None,
        "second_target_player_id": None,
        "second_target_card_index": None,
    }

    if action.power_name == PowerType.SEE_SELF:
        payload["target_card_index"] = st.selectbox(
            "Your card index",
            options=list(range(len(actor.hand))),
            key=f"{key_base}_self_index",
        )
        return payload, True

    if action.power_name == PowerType.SEE_OTHER:
        if not other_player_ids:
            st.info("No valid other player cards are available for this power.")
            return payload, False
        target_player_id = st.selectbox(
            "Target player",
            options=other_player_ids,
            format_func=lambda player_id: player_name(state.players, player_id),
            key=f"{key_base}_other_player",
        )
        target_player = state.resolve_player(target_player_id)
        payload["target_player_id"] = target_player.id
        payload["target_card_index"] = st.selectbox(
            "Target card index",
            options=list(range(len(target_player.hand))),
            key=f"{key_base}_other_index",
        )
        return payload, True

    if action.power_name in {PowerType.BLIND_SWAP, PowerType.SEE_AND_SWAP}:
        if not other_player_ids:
            st.info("No valid other player cards are available for this power.")
            return payload, False
        payload["target_player_id"] = actor.id
        payload["target_card_index"] = st.selectbox(
            "Your card index",
            options=list(range(len(actor.hand))),
            key=f"{key_base}_swap_own_index",
        )
        second_player_id = st.selectbox(
            "Other player",
            options=other_player_ids,
            format_func=lambda player_id: player_name(state.players, player_id),
            key=f"{key_base}_swap_other_player",
        )
        second_player = state.resolve_player(second_player_id)
        payload["second_target_player_id"] = second_player.id
        payload["second_target_card_index"] = st.selectbox(
            "Other player card index",
            options=list(range(len(second_player.hand))),
            key=f"{key_base}_swap_other_index",
        )
        return payload, True

    return payload, True


def _execute_action(engine: GameEngine, action):
    st.session_state.power_reveal = []
    if isinstance(action, Draw):
        return engine.draw_card(action.actor_id)
    if isinstance(action, Discard):
        return engine.discard_card(action.actor_id)
    if isinstance(action, Replace):
        return engine.replace_card(action.actor_id, action.target_index)
    if isinstance(action, CallKaboom):
        return engine.call_kaboom(action.actor_id)
    if isinstance(action, CloseReaction):
        return engine.close_reaction()
    if isinstance(action, ResolvePendingPower):
        pending = engine.state.pending_power_action
        reveal_snapshot = _snapshot_pending_power_reveal(engine, pending)
        results = engine.resolve_pending_power(action.actor_id)
        st.session_state.power_reveal = _format_power_reveal(engine, pending, reveal_snapshot)
        for reveal in st.session_state.power_reveal:
            _append_event_log(f"reveal={reveal['public']}")
        return results
    if isinstance(action, ReactDiscardOwnCard):
        return [engine.react_discard_own_card(action.actor_id, action.card_index)]
    if isinstance(action, ReactDiscardOtherCard):
        return [
            engine.react_discard_other_card(
                action.actor_id,
                action.target_player_id,
                action.target_card_index,
                action.give_card_index,
            )
        ]
    return apply_action(engine.state, action)


def _execute_agent_decision(engine: GameEngine, decision) -> None:
    st.session_state.power_reveal = []
    actor_id = _decision_actor_id(decision.action)
    actor_name = player_name(engine.state.players, actor_id) if actor_id is not None else "Agent"
    _append_event_log(f"agent={actor_name} | decision={decision.note}")

    if isinstance(decision.action, tuple) and decision.action[0] == "opening_peek":
        _, player_id, indices = decision.action
        results = engine.perform_opening_peek(player_id, indices)
        _record_results(results)
        return

    if isinstance(decision.action, UsePower):
        payload = decision.payload or {}
        results = engine.use_power(
            power_name=decision.action.power_name,
            player=decision.action.actor_id,
            target_player_id=payload.get("target_player_id"),
            target_card_index=payload.get("target_card_index"),
            second_target_player_id=payload.get("second_target_player_id"),
            second_target_card_index=payload.get("second_target_card_index"),
        )
        _record_results(results)
        return

    results = _execute_action(engine, decision.action)
    _record_results(results)


def _auto_step_agents(engine: GameEngine) -> None:
    steps_taken = False
    for _ in range(32):
        if engine.state.phase == GamePhase.GAME_OVER:
            break

        actions = _app_visible_actions(engine, get_valid_actions(engine.state))
        if not actions:
            break

        if engine.state.phase == GamePhase.REACTION and _can_finalize_reaction_window(actions):
            _finalize_reaction_window(engine)
            steps_taken = True
            continue

        if engine.state.phase == GamePhase.REACTION:
            agent_actor_id = _next_agent_actor_id(engine, actions)
            if agent_actor_id is not None:
                decision = choose_agent_decision(engine, agent_actor_id)
                if decision is None:
                    _mark_reaction_pass(agent_actor_id, engine)
                    steps_taken = True
                    continue

                _execute_agent_decision(engine, decision)
                steps_taken = True
                continue

        if _has_human_input_available(engine, actions):
            break

        agent_actor_id = _next_agent_actor_id(engine, actions)
        if agent_actor_id is None:
            break

        decision = choose_agent_decision(engine, agent_actor_id)
        if decision is None:
            _mark_reaction_pass(agent_actor_id, engine)
            steps_taken = True
            continue

        _execute_agent_decision(engine, decision)
        steps_taken = True

    if steps_taken:
        st.rerun()


def _has_human_input_available(engine: GameEngine, actions) -> bool:
    if not st.session_state.agent_mode:
        return True
    if engine.state.phase == GamePhase.REACTION:
        human_id = st.session_state.human_player_id
        human = engine.state.resolve_player(human_id)
        if human.active and not _reaction_actor_passed(human_id):
            return True
    return any(
        not isinstance(action, CloseReaction) and _control_for_actor(_action_actor_id(engine, action)) == "human"
        for action in actions
    )


def _next_agent_actor_id(engine: GameEngine, actions) -> int | None:
    for action in actions:
        actor_id = _action_actor_id(engine, action)
        if actor_id is not None and _control_for_actor(actor_id) == "agent":
            return actor_id
    return None


def _action_actor_id(engine: GameEngine, action) -> int | None:
    if isinstance(action, ResolvePendingPower):
        return action.actor_id
    if hasattr(action, "actor_id"):
        return action.actor_id
    return None


def _decision_actor_id(action) -> int | None:
    if isinstance(action, tuple):
        return action[1]
    return getattr(action, "actor_id", None)


def _control_for_actor(actor_id: int | None) -> str:
    if actor_id is None:
        return "human"
    return st.session_state.player_control.get(actor_id, "human")


def _current_reaction_window_key(engine: GameEngine):
    state = engine.state
    if state.phase != GamePhase.REACTION or not state.reaction_open:
        return None
    top = state.top_discard()
    top_label = format_card(top)
    pending = state.pending_power_action
    pending_signature = None
    if pending is not None:
        pending_signature = (
            pending.actor_id,
            pending.power_name.value,
            pending.target_player_id,
            pending.target_card_index,
            pending.second_target_player_id,
            pending.second_target_card_index,
        )
    return (
        state.round_number,
        len(state.discard_pile),
        state.reaction_rank,
        state.reaction_initiator,
        top_label,
        pending_signature,
    )


def _sync_reaction_pass_state(engine: GameEngine) -> None:
    window_key = _current_reaction_window_key(engine)
    if window_key is None:
        st.session_state.reaction_window_key = None
        st.session_state.reaction_passes = {}
        return
    if st.session_state.reaction_window_key != window_key:
        st.session_state.reaction_window_key = window_key
        st.session_state.reaction_passes = {}


def _reaction_actor_passed(actor_id: int) -> bool:
    return st.session_state.reaction_passes.get(actor_id, False)


def _mark_reaction_pass(actor_id: int, engine: GameEngine) -> None:
    st.session_state.reaction_passes[actor_id] = True
    actor_name = player_name(engine.state.players, actor_id)
    _append_event_log(f"pass={actor_name} passed on this discard event")


def _app_visible_actions(engine: GameEngine, actions):
    if engine.state.phase != GamePhase.REACTION:
        return actions

    filtered = []
    for action in actions:
        if isinstance(action, CloseReaction):
            filtered.append(action)
            continue
        actor_id = _action_actor_id(engine, action)
        if actor_id is not None and _reaction_actor_passed(actor_id):
            continue
        filtered.append(action)
    return filtered


def _can_finalize_reaction_window(actions) -> bool:
    if not actions:
        return False
    return all(isinstance(action, CloseReaction) for action in actions)


def _finalize_reaction_window(engine: GameEngine) -> None:
    results = engine.close_reaction()
    _record_results(results)


def _player_can_still_react(engine: GameEngine, player_id: int) -> bool:
    actions = _app_visible_actions(engine, get_valid_actions(engine.state))
    return any(
        not isinstance(action, CloseReaction) and _action_actor_id(engine, action) == player_id
        for action in actions
    )


def _record_results(results: Iterable[object]) -> None:
    for result in results:
        _append_event_log(format_result(result))


def _state_window_signature(engine: GameEngine):
    state = engine.state
    return (
        state.round_number,
        state.phase.value,
        state.current_player().id if state.phase != GamePhase.GAME_OVER else None,
        state.reaction_open,
        state.reaction_rank,
        format_card(state.top_discard()),
        format_card(state.drawn_card),
    )


def _update_window_notice(engine: GameEngine, current_signature) -> None:
    previous = st.session_state.previous_window_signature
    if previous is None or previous == current_signature:
        return

    state = engine.state
    current_player = player_name(state.players, state.current_player().id) if state.phase != GamePhase.GAME_OVER else "none"
    previous_round, previous_phase, previous_player_id, *_ = previous
    previous_player = (
        player_name(state.players, previous_player_id)
        if previous_player_id is not None
        else "none"
    )

    if previous_phase != state.phase.value or previous_player_id != state.current_player().id or previous_round != state.round_number:
        st.session_state.window_notice = (
            f"State updated: now Round {state.round_number}, Phase {state.phase.value}, Current {current_player}. "
            f"Previously you were viewing Round {previous_round}, Phase {previous_phase}, Current {previous_player}."
        )
    else:
        st.session_state.window_notice = "State updated."


def _render_window_notice() -> None:
    notice = st.session_state.window_notice
    if notice:
        st.warning(notice)


def _set_event_log_path(engine: GameEngine) -> None:
    EVENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    st.session_state.event_log_path = EVENT_LOG_DIR / f"game_{engine.game_id}_{timestamp}.json"
    _write_event_log_file()


def _append_event_log(entry: str) -> None:
    st.session_state.event_log.append(entry)
    st.session_state.event_log = st.session_state.event_log[-DEFAULT_EVENT_LOG_LIMIT:]
    _write_event_log_file()


def _write_event_log_file() -> None:
    path = st.session_state.event_log_path
    if path is None:
        return
    payload = {
        "generated_at": datetime.now().isoformat(),
        "entries": st.session_state.event_log,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _process_queued_actions(engine: GameEngine) -> None:
    actor_id = st.session_state.queued_resolve_pending_power_actor_id
    if actor_id is None:
        return
    st.session_state.queued_resolve_pending_power_actor_id = None
    try:
        results = _execute_action(engine, ResolvePendingPower(actor_id=actor_id))
        _record_results(results)
    except InvalidActionError as exc:
        st.error(str(exc))


def _render_event_log() -> None:
    st.subheader("Event Log")
    log = st.session_state.event_log or ["(empty)"]
    st.code("\n\n".join(reversed(log)))


def _render_power_reveal_panel() -> None:
    st.subheader("Last Reveal")
    reveals = st.session_state.power_reveal
    if not reveals:
        st.caption("No private reveal pinned yet.")
        return

    for reveal in reveals:
        if reveal["kind"] == "penalty":
            st.error(reveal["public"])
            continue
        if st.session_state.show_full_state or st.session_state.selected_viewer_id == reveal["actor_id"]:
            st.success(reveal["private"])
        else:
            st.info(reveal["public"])


def _format_pending_power_hint(engine: GameEngine) -> str | None:
    pending = engine.state.pending_power_action
    if pending is None:
        return None

    actor_name = player_name(engine.state.players, pending.actor_id)

    if pending.power_name == PowerType.SEE_SELF and pending.target_card_index is not None:
        return (
            f"Pending power: {actor_name} claimed `see_self` for own card index "
            f"{pending.target_card_index}. Use `ResolvePendingPower` to reveal it now. "
            "After reveal, the same reaction window stays open so that knowledge can be used immediately."
        )

    if (
        pending.power_name == PowerType.SEE_OTHER
        and pending.target_player_id is not None
        and pending.target_card_index is not None
    ):
        return (
            f"Pending power: {actor_name} claimed `see_other` for "
            f"{player_name(engine.state.players, pending.target_player_id)}[{pending.target_card_index}]. "
            "Use `ResolvePendingPower` to reveal it now. After reveal, the same reaction window stays open so that "
            "knowledge can be used immediately."
        )

    if (
        pending.power_name == PowerType.SEE_AND_SWAP
        and pending.target_player_id is not None
        and pending.target_card_index is not None
        and pending.second_target_player_id is not None
        and pending.second_target_card_index is not None
    ):
        return (
            f"Pending power: {actor_name} claimed `see_and_swap` for "
            f"{player_name(engine.state.players, pending.target_player_id)}[{pending.target_card_index}] and "
            f"{player_name(engine.state.players, pending.second_target_player_id)}"
            f"[{pending.second_target_card_index}]. Use `ResolvePendingPower` to reveal them now. "
            "After reveal, the same reaction window stays open until someone resolves or closes it."
        )

    if pending.power_name == PowerType.BLIND_SWAP:
        return (
            f"Pending power: {actor_name} claimed `blind_swap`. "
            "Use `ResolvePendingPower` to apply the swap. The reaction window stays open until a later action ends it."
        )

    return (
        f"Pending power: {actor_name} claimed `{pending.power_name.value}`. "
        "Use `ResolvePendingPower` to apply it now. The discard window remains open afterward unless another action closes it."
    )


def _describe_pending_resolution(engine: GameEngine) -> str:
    pending = engine.state.pending_power_action
    if pending is None:
        return "No pending power."

    actor_name = player_name(engine.state.players, pending.actor_id)
    if pending.power_name == PowerType.SEE_SELF and pending.target_card_index is not None:
        return f"{actor_name}: reveal own card at index {pending.target_card_index} now"
    if (
        pending.power_name == PowerType.SEE_OTHER
        and pending.target_player_id is not None
        and pending.target_card_index is not None
    ):
        return (
            f"{actor_name}: reveal {player_name(engine.state.players, pending.target_player_id)}"
            f"[{pending.target_card_index}] now"
        )
    if (
        pending.power_name == PowerType.SEE_AND_SWAP
        and pending.target_player_id is not None
        and pending.target_card_index is not None
        and pending.second_target_player_id is not None
        and pending.second_target_card_index is not None
    ):
        return (
            f"{actor_name}: reveal "
            f"{player_name(engine.state.players, pending.target_player_id)}[{pending.target_card_index}] and "
            f"{player_name(engine.state.players, pending.second_target_player_id)}"
            f"[{pending.second_target_card_index}] now"
        )
    if pending.power_name == PowerType.BLIND_SWAP:
        return f"{actor_name}: apply blind swap now"
    return f"{actor_name}: resolve `{pending.power_name.value}` now"


def _snapshot_pending_power_reveal(engine: GameEngine, pending: UsePower | None) -> list[tuple[int, int, str]]:
    if pending is None:
        return []

    state = engine.state
    snapshots: list[tuple[int, int, str]] = []

    if pending.power_name == PowerType.SEE_SELF and pending.target_card_index is not None:
        actor = state.resolve_player(pending.actor_id)
        card = actor.hand[pending.target_card_index]
        snapshots.append((actor.id, pending.target_card_index, format_card(card)))
        return snapshots

    if (
        pending.power_name == PowerType.SEE_OTHER
        and pending.target_player_id is not None
        and pending.target_card_index is not None
    ):
        target = state.resolve_player(pending.target_player_id)
        card = target.hand[pending.target_card_index]
        snapshots.append((target.id, pending.target_card_index, format_card(card)))
        return snapshots

    if (
        pending.power_name == PowerType.SEE_AND_SWAP
        and pending.target_player_id is not None
        and pending.target_card_index is not None
        and pending.second_target_player_id is not None
        and pending.second_target_card_index is not None
    ):
        first = state.resolve_player(pending.target_player_id)
        second = state.resolve_player(pending.second_target_player_id)
        snapshots.append((first.id, pending.target_card_index, format_card(first.hand[pending.target_card_index])))
        snapshots.append(
            (second.id, pending.second_target_card_index, format_card(second.hand[pending.second_target_card_index]))
        )
        return snapshots

    return []


def _format_power_reveal(
    engine: GameEngine,
    pending: UsePower | None,
    reveal_snapshot: list[tuple[int, int, str]],
) -> list[dict[str, object]]:
    if pending is None or not reveal_snapshot:
        return []

    actor_name = player_name(engine.state.players, pending.actor_id)
    if pending.power_name == PowerType.SEE_SELF:
        _, card_index, card_label = reveal_snapshot[0]
        return [
            {
                "kind": "power",
                "actor_id": pending.actor_id,
                "public": f"{actor_name} saw own card at index {card_index}",
                "private": f"{actor_name} saw own card at index {card_index}: {card_label}",
            }
        ]

    if pending.power_name == PowerType.SEE_OTHER:
        target_player_id, card_index, card_label = reveal_snapshot[0]
        target_name = player_name(engine.state.players, target_player_id)
        return [
            {
                "kind": "power",
                "actor_id": pending.actor_id,
                "public": f"{actor_name} saw {target_name}[{card_index}]",
                "private": f"{actor_name} saw {target_name}[{card_index}]: {card_label}",
            }
        ]

    if pending.power_name == PowerType.SEE_AND_SWAP:
        first_pid, first_index, first_card = reveal_snapshot[0]
        second_pid, second_index, second_card = reveal_snapshot[1]
        return [
            {
                "kind": "power",
                "actor_id": pending.actor_id,
                "public": (
                    f"{actor_name} saw "
                    f"{player_name(engine.state.players, first_pid)}[{first_index}] and "
                    f"{player_name(engine.state.players, second_pid)}[{second_index}]"
                ),
                "private": (
                    f"{actor_name} saw "
                    f"{player_name(engine.state.players, first_pid)}[{first_index}]={first_card} and "
                    f"{player_name(engine.state.players, second_pid)}[{second_index}]={second_card}"
                ),
            }
        ]

    return []


def _render_player_card(player: Player, viewer: Player, current_player_id: int, reveal_all: bool) -> None:
    badges = _player_badges(player, viewer.id, current_player_id)
    badge_markup = "".join(f'<span class="player-badge">{badge}</span>' for badge in badges)
    st.markdown(
        f"""
        <div class="player-shell">
            <div class="player-head">
                <div class="player-name">{player_label(player)}</div>
                <div class="player-badges">{badge_markup}</div>
            </div>
            <div class="player-meta">Cards: {len(player.hand)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.code(render_hand_for_viewer(player, viewer, reveal_all))
    st.caption(f"Score: {render_score_for_viewer(player, viewer, reveal_all)}")


def _player_badges(player: Player, viewer_id: int, current_player_id: int) -> list[str]:
    badges: list[str] = []
    if player.id == viewer_id:
        badges.append("viewer")
    if player.id == current_player_id:
        badges.append("current")
    if not player.active:
        badges.append("inactive")
    if player.revealed:
        badges.append("revealed")
    return badges


def _viewer_index(players: list[Player], selected_viewer_id: int) -> int:
    for index, player in enumerate(players):
        if player.id == selected_viewer_id:
            return index
    return 0


@st.cache_data(show_spinner=False)
def _load_rules_markdown() -> str:
    if not RULES_PATH.exists():
        return "Rules document not found. Expected: `kaboom-core/docs/GAME_RULES.md`."
    return RULES_PATH.read_text(encoding="utf-8")


def _render_rules_button(label: str) -> None:
    with st.popover(label, use_container_width=True):
        st.markdown(_load_rules_markdown())
        st.caption(f"Source: {RULES_PATH}")


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --accent: #a93f2b;
            --accent-soft: rgba(169, 63, 43, 0.14);
            --panel: var(--secondary-background-color);
            --line: rgba(127, 127, 127, 0.24);
            --muted: rgba(128, 128, 128, 0.92);
            --deep: var(--text-color);
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(169, 63, 43, 0.10), transparent 24%),
                radial-gradient(circle at bottom right, rgba(38, 52, 43, 0.08), transparent 18%);
        }
        .hero-shell, .page-head {
            background:
                linear-gradient(135deg, rgba(169, 63, 43, 0.08), transparent 40%),
                var(--panel);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 1.25rem 1.4rem;
            margin-bottom: 1rem;
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.08);
        }
        .page-head {
            display: flex;
            justify-content: space-between;
            align-items: end;
            gap: 1rem;
        }
        .eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.14em;
            color: var(--accent);
            font-size: 0.76rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .hero-shell h1, .page-head h1 {
            margin: 0;
            color: var(--deep);
            font-size: 2rem;
            line-height: 1.05;
        }
        .hero-shell p, .page-note {
            margin: 0.45rem 0 0;
            color: var(--text-color);
            opacity: 0.82;
            max-width: 58rem;
        }
        .player-shell {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 0.9rem 1rem 0.7rem;
            box-shadow: 0 8px 18px rgba(0, 0, 0, 0.05);
        }
        .player-head {
            display: flex;
            justify-content: space-between;
            align-items: start;
            gap: 0.75rem;
        }
        .player-name {
            font-weight: 700;
            color: var(--deep);
        }
        .player-meta {
            color: var(--text-color);
            opacity: 0.76;
            font-size: 0.9rem;
            margin-top: 0.35rem;
        }
        .player-badges {
            display: flex;
            flex-wrap: wrap;
            justify-content: end;
            gap: 0.3rem;
        }
        .player-badge {
            background: var(--accent-soft);
            color: var(--accent);
            border-radius: 999px;
            padding: 0.18rem 0.48rem;
            font-size: 0.74rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .stCodeBlock, div[data-testid="stCodeBlock"] {
            border-radius: 14px;
            overflow: hidden;
        }
        @media (prefers-contrast: more) {
            .player-badge {
                border: 1px solid currentColor;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
