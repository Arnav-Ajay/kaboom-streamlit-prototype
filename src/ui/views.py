from __future__ import annotations

from pathlib import Path
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
from kaboom.players.player import Player
from kaboom.powers.types import PowerType

from .presenter import (
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


def ensure_app_state() -> None:
    st.session_state.setdefault("page", "landing")
    st.session_state.setdefault("engine", None)
    st.session_state.setdefault("selected_viewer_id", 0)
    st.session_state.setdefault("show_full_state", False)
    st.session_state.setdefault("event_log", [])
    st.session_state.setdefault("power_reveal", [])


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

    top_cols = st.columns([1, 1], gap="large")
    with top_cols[0]:
        num_players = st.slider("Players", min_value=2, max_value=MAX_PLAYERS, value=DEFAULT_PLAYERS)
    with top_cols[1]:
        hand_size = st.slider("Hand size", min_value=2, max_value=6, value=DEFAULT_HAND_SIZE)

    with st.form("new_game_form"):
        st.markdown("### Table Setup")
        player_names = [
            st.text_input(f"Player {index + 1}", value=f"P{index + 1}", key=f"landing_player_{index}")
            for index in range(num_players)
        ]
        submitted = st.form_submit_button("Start Local Inspector")

    if submitted:
        engine = GameEngine(game_id=0, num_players=num_players, hand_size=hand_size)
        for index, player in enumerate(engine.state.players):
            player.name = player_names[index].strip() or f"P{index + 1}"

        st.session_state.engine = engine
        st.session_state.selected_viewer_id = engine.state.players[0].id
        st.session_state.show_full_state = False
        st.session_state.power_reveal = []
        st.session_state.event_log = [
            f"Started local inspector with {num_players} players and hand size {hand_size}."
        ]
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
        _render_memory_panels(engine)
        _render_event_log()


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
        _render_rules_button("Rules")

        if st.button("Reset To Landing"):
            st.session_state.engine = None
            st.session_state.event_log = []
            st.session_state.power_reveal = []
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
    if state.kaboom_called_by is not None:
        st.warning(f"Kaboom called by {player_name(state.players, state.kaboom_called_by)}.")
    if st.session_state.power_reveal:
        st.success("Power reveal: " + " | ".join(st.session_state.power_reveal))
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
    actions = get_valid_actions(state)

    st.subheader("Legal Actions")
    if not actions:
        st.info("No legal actions available.")
        return

    st.caption("Every action below comes from `get_valid_actions(state)`.")
    _render_phase_help(state.phase)

    with st.container(border=True):
        if state.phase == GamePhase.OPENING_PEEK:
            _render_opening_peek_panel(engine)
            return
        for index, action in enumerate(actions):
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
        st.caption("Reaction window: first applied action wins the contested discard event.")


def _render_direct_action(engine: GameEngine, action, index: int) -> None:
    label = describe_action(engine.state.players, action)
    if st.button(label, key=f"action_button_{index}", use_container_width=True):
        results = _execute_action(engine, action)
        _record_results(results)
        st.rerun()


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
        results = engine.perform_opening_peek(player.id, tuple(chosen))
        _record_results(results)
        st.rerun()


def _render_use_power_action(engine: GameEngine, action: UsePower, index: int) -> None:
    state = engine.state
    actor = state.resolve_player(action.actor_id)

    with st.form(f"use_power_form_{index}"):
        st.markdown(f"**{player_label(actor)} use power: `{action.power_name.value}`**")
        st.caption(
            f"Source card: {format_card(action.source_card)}. "
            "The card is discarded first; power and reaction then compete for priority."
        )
        payload = _build_power_payload_inputs(state, action, index)
        submitted = st.form_submit_button(f"Discard for power: {action.power_name.value}")

    if submitted:
        results = engine.use_power(
            power_name=action.power_name,
            player=actor.id,
            target_player_id=payload["target_player_id"],
            target_card_index=payload["target_card_index"],
            second_target_player_id=payload["second_target_player_id"],
            second_target_card_index=payload["second_target_card_index"],
        )
        _record_results(results)
        st.rerun()


def _build_power_payload_inputs(state, action: UsePower, index: int) -> dict[str, int | None]:
    actor = state.resolve_player(action.actor_id)
    other_players = [player for player in state.players if player.id != actor.id and player.active]
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
            key=f"power_self_index_{index}",
        )
        return payload

    if action.power_name == PowerType.SEE_OTHER:
        target_player_id = st.selectbox(
            "Target player",
            options=other_player_ids,
            format_func=lambda player_id: player_name(state.players, player_id),
            key=f"power_other_player_{index}",
        )
        target_player = state.resolve_player(target_player_id)
        payload["target_player_id"] = target_player.id
        payload["target_card_index"] = st.selectbox(
            "Target card index",
            options=list(range(len(target_player.hand))),
            key=f"power_other_index_{index}",
        )
        return payload

    if action.power_name in {PowerType.BLIND_SWAP, PowerType.SEE_AND_SWAP}:
        payload["target_player_id"] = actor.id
        payload["target_card_index"] = st.selectbox(
            "Your card index",
            options=list(range(len(actor.hand))),
            key=f"power_swap_own_index_{index}",
        )
        second_player_id = st.selectbox(
            "Other player",
            options=other_player_ids,
            format_func=lambda player_id: player_name(state.players, player_id),
            key=f"power_swap_other_player_{index}",
        )
        second_player = state.resolve_player(second_player_id)
        payload["second_target_player_id"] = second_player.id
        payload["second_target_card_index"] = st.selectbox(
            "Other player card index",
            options=list(range(len(second_player.hand))),
            key=f"power_swap_other_index_{index}",
        )
        return payload

    return payload


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


def _record_results(results: Iterable[object]) -> None:
    for result in results:
        st.session_state.event_log.append(format_result(result))
    st.session_state.event_log = st.session_state.event_log[-DEFAULT_EVENT_LOG_LIMIT:]


def _render_event_log() -> None:
    st.subheader("Event Log")
    log = st.session_state.event_log or ["(empty)"]
    st.code("\n\n".join(reversed(log)))


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
) -> list[str]:
    if pending is None or not reveal_snapshot:
        return []

    actor_name = player_name(engine.state.players, pending.actor_id)
    if pending.power_name == PowerType.SEE_SELF:
        _, card_index, card_label = reveal_snapshot[0]
        return [f"{actor_name} saw own card at index {card_index}: {card_label}"]

    if pending.power_name == PowerType.SEE_OTHER:
        target_player_id, card_index, card_label = reveal_snapshot[0]
        target_name = player_name(engine.state.players, target_player_id)
        return [f"{actor_name} saw {target_name}[{card_index}]: {card_label}"]

    if pending.power_name == PowerType.SEE_AND_SWAP:
        first_pid, first_index, first_card = reveal_snapshot[0]
        second_pid, second_index, second_card = reveal_snapshot[1]
        return [
            (
                f"{actor_name} saw "
                f"{player_name(engine.state.players, first_pid)}[{first_index}]={first_card} and "
                f"{player_name(engine.state.players, second_pid)}[{second_index}]={second_card}"
            )
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
            --paper: #f5efdf;
            --ink: #1d1f1c;
            --accent: #a93f2b;
            --accent-soft: #ead0c7;
            --panel: #fffaf0;
            --line: #d8c8ae;
            --muted: #6f695e;
            --deep: #26342b;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(169, 63, 43, 0.08), transparent 28%),
                linear-gradient(180deg, #fcf7ea 0%, #f2ead5 100%);
            color: var(--ink);
        }
        .hero-shell, .page-head {
            background: linear-gradient(135deg, rgba(255,250,240,0.92), rgba(247,238,220,0.9));
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 1.25rem 1.4rem;
            margin-bottom: 1rem;
            box-shadow: 0 10px 24px rgba(49, 42, 31, 0.08);
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
            color: var(--muted);
            max-width: 58rem;
        }
        .player-shell {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 0.9rem 1rem 0.7rem;
            box-shadow: 0 8px 18px rgba(54, 46, 35, 0.05);
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
            color: var(--muted);
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
        code {
            color: var(--deep);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
