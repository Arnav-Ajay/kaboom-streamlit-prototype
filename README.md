# Kaboom Streamlit App

Streamlit application for Kaboom built on top of `kaboom-engine`.

This repository should now be treated as a fresh UI project, not as an authoritative implementation of Kaboom rules. The rules engine lives in `kaboom-core` and must remain the single source of truth for game setup, legality, state transitions, scoring, reactions, powers, and endgame behavior.

## Status

This repository has been reset to a new baseline around `kaboom-engine`.

The earlier prototype-only rules, Firebase helpers, and room-store implementation have been removed. What remains is the beginning of a fresh Streamlit app that talks directly to the engine.

Current implemented scope:
- local single-browser engine inspector
- player-perspective rendering using engine memory
- opening peek flow
- turn, reaction, and pending-power action execution from `get_valid_actions(state)`
- event log and raw engine snapshot for debugging

## Project Direction

The new Streamlit app should provide:
- a browser-based interface for local and multiplayer Kaboom sessions
- a debug-friendly visualization of engine state, legal actions, memory, reactions, and pending power resolution
- a clean boundary between UI concerns and engine concerns

The new Streamlit app should not:
- duplicate core game rules in UI code
- maintain its own deck, scoring, turn, or reaction logic
- mix Streamlit rerun behavior into engine state mutation logic

## Architecture Boundary

`kaboom-core` owns:
- game rules
- state machine and phases
- legal action generation
- action validation and state transitions
- scoring and winner determination
- result metadata for app/server layers

This repository should own:
- player identity and session state
- room and lobby UX
- rendering of game state and action choices
- action submission to the engine
- persistence and multiplayer transport
- event logs, replay views, and operator/debug views

## Legacy Prototype Assessment

### Kept in the reset

- [app.py](/d:/Users/arnav/Documents/Github_Repos/kaboom/kaboom-streamlit-prototype/app.py)
  Basic page routing is usable as a starting point.

- [src/ui/views.py](/d:/Users/arnav/Documents/Github_Repos/kaboom/kaboom-streamlit-prototype/src/ui/views.py)
  The high-level separation between landing, lobby, and game views is still useful.

### Removed from the repository

- legacy local game rules and phase logic
- Firebase transport helpers
- prototype room-store code
- unused placeholder component and utility modules

## Recommended Rebuild Strategy

Build this project incrementally around `kaboom-engine`:

1. Start with a single-browser engine inspector.
2. Add Streamlit views that render the current player perspective cleanly.
3. Introduce room state and persistence only after the local engine flow is stable.
4. Add multiplayer synchronization and event ordering on top of engine actions.

This order matters because the current CLI is already being used to find engine bugs. The Streamlit app should become a richer inspection surface, not another source of rules drift.

## Developer Goals

The first production-quality Streamlit version should support:
- room creation and joining
- opening peek flow
- draw, replace, discard, discard-for-power, and reaction windows
- pending power and contested discard visualization
- Kaboom declaration and endgame visibility
- memory-aware rendering per player
- event/result log for debugging

## Non-Goals for the first milestone

- polished animations
- public deployment hardening
- spectator mode
- AI or RL integration inside the Streamlit app
- replacing the CLI as the primary debugging tool

## Local Development

Expected dependencies:
- Python 3.11+
- `kaboom-engine` from the local `kaboom-core` repo during development
- Streamlit and any chosen persistence backend

Install and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

For local development against the sibling core repo:

```bash
pip install -e ../kaboom-core
```

## Documentation

- [PROJECT_PLAN.md](/d:/Users/arnav/Documents/Github_Repos/kaboom/kaboom-streamlit-prototype/PROJECT_PLAN.md): incremental delivery plan for rebuilding the app on top of `kaboom-engine`
- `kaboom-core` docs:
  - `docs/GAME_RULES.md`
  - `docs/ENGINE_FLOW.md`
  - `docs/GAME_ENGINE_API.md`

## Immediate Next Step

Milestone 1 is in place as a local engine inspector.

The next step is Milestone 2:
- tighten perspective-safe rendering
- improve the in-browser debugging surface
- prepare the app structure for room-based multiplayer without reintroducing app-side rules
