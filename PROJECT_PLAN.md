# Project Plan

## Objective

Rebuild the Streamlit Kaboom app as a clean UI and multiplayer layer on top of `kaboom-engine`, without duplicating rules logic in the app.

## Principles

- `kaboom-engine` is the only rules authority.
- UI code should translate engine state and actions, not reinterpret them.
- Multiplayer concerns belong in the app layer, not in core.
- Build debug visibility early so the app helps expose engine issues instead of hiding them.
- Preserve only legacy pieces that reduce implementation time without preserving old architectural mistakes.

## Current Assessment

### Already kept after reset

- `app.py` routing skeleton
- page-level separation in `src/ui/views.py`

### Already removed

- all local game rules and state modeling from the prototype
- hardcoded or simplified phase handling
- Firebase-specific transport code
- any logic that directly mutates game state outside the engine

## Delivery Plan

### Milestone 0: Reset Baseline

Goal:
Create a trustworthy project baseline and remove ambiguity about architecture ownership.

Deliverables:
- formal README
- project plan
- repository audit of reusable vs disposable legacy code
- dependency review

Exit criteria:
- project direction is documented
- engine/UI boundary is explicit
- no one reading the repo can mistake the app for a second rules engine

### Milestone 1: Local Engine Inspector

Goal:
Build a single-browser Streamlit app that can drive a local `kaboom-engine` game instance end to end.

Deliverables:
- local game bootstrap from `kaboom-engine`
- opening peek flow
- current-player state rendering
- legal action rendering
- result/event log panel
- explicit display for reaction windows and pending powers

Exit criteria:
- a developer can play a full game locally in one browser session
- all actions shown in the UI are sourced from engine legal actions
- no app-side rule duplication exists

Current status:
- implemented
- presenter helpers have basic pytest coverage
- first-pass local human-vs-agent mode is implemented for 2-player tables
- JSON event logs are persisted locally for each session
- Streamlit runtime still needs manual browser verification in an environment with `streamlit` installed

### Milestone 2: Perspective-Safe Rendering

Goal:
Render the same engine state differently for each player identity without leaking hidden information.

Deliverables:
- per-player identity/session handling
- hidden-hand rendering based on memory and reveal state
- support for inactive/revealed Kaboom callers
- debug toggle for full-state inspection in development

Exit criteria:
- the same underlying game can be viewed safely from different player perspectives
- hidden information is controlled by UI rendering rules, not alternate game logic

### Milestone 2A: Local Agent Iteration

Goal:
Make the local agent opponent good enough to support realistic single-browser playtesting.

Deliverables:
- seat control between human and agent
- deterministic heuristic policy using only engine legal actions and player memory
- auto-step loop for agent-controlled opening peek, turns, and pending power resolution
- event log entries that explain agent choices
- reaction-window coordination that pauses correctly for the human side

Exit criteria:
- a human can play against one local agent without taking the other side manually
- the agent does not bypass hidden-information rules
- the app stops auto-play whenever human input is required

### Milestone 3: Room and Lobby Layer

Goal:
Add room creation, joining, and waiting-room flow without embedding rules into persistence code.

Deliverables:
- room model
- player roster and host controls
- room start conditions
- game session binding to a persisted engine state or event log

Exit criteria:
- players can create and join rooms
- the room can start a game that uses `kaboom-engine`
- lobby code does not implement any game logic

### Milestone 4: Multiplayer Turn Submission

Goal:
Allow multiple browser sessions to submit intents against a shared engine-backed game.

Deliverables:
- serialized game state storage
- action submission mechanism
- action/result refresh loop
- conflict-safe turn handling for normal turn actions

Exit criteria:
- two or more browser sessions can participate in the same game
- action application remains deterministic
- server/store logic submits engine actions rather than custom state patches

### Milestone 5: Contested Discard and Reaction UX

Goal:
Handle the most complex Kaboom flows cleanly in multiplayer.

Deliverables:
- reaction window UI
- pending power claim UI
- clear labeling of contested discard priority
- wrong-guess penalty rendering
- event-ordering policy at the app layer

Exit criteria:
- power and reaction conflicts are understandable to players
- wrong reaction attempts are visible and debuggable
- the app layer can order competing intents without redefining game rules

### Milestone 6: Persistence and Backend Hardening

Goal:
Replace prototype-grade storage assumptions with a maintainable backend choice.

Deliverables:
- environment-based configuration
- chosen persistence backend abstraction
- room/game cleanup strategy
- basic failure handling and reconnect behavior

Exit criteria:
- storage is configurable
- the app can recover or fail clearly on transient backend issues
- backend code is separated from UI rendering

### Milestone 7: Simulation and Inspection Support

Goal:
Make the app useful as an engine inspection and future simulation companion.

Deliverables:
- replay/event log view
- state snapshot panel
- optional developer controls for stepping through actions
- hooks for future simulation or bot-driven sessions

Exit criteria:
- developers can use the app to inspect engine behavior during bug hunts
- the app can eventually coexist with AI/RL work without another rewrite

## Proposed Repository Direction

Short term:
- keep the current top-level app structure
- stop using `src/game/*` as the source of gameplay behavior
- introduce an adapter layer between Streamlit views and `kaboom-engine`

Medium term:
- either delete `src/game/*` entirely or replace it with engine-facing view helpers only
- move backend/persistence code behind a small interface
- keep page and component code separate from engine orchestration

## Risks

- hidden-information rendering can accidentally leak state if the app shortcuts the engine model
- multiplayer event ordering can become confusing if not made explicit
- retaining too much of the prototype may preserve the same architecture problems under a new name
- Streamlit is fine for iteration, but it is not a multiplayer-first runtime, so room sync design must stay disciplined

## Definition of Done for the Rebuild

The project is in a good state when:
- gameplay correctness comes entirely from `kaboom-engine`
- the Streamlit UI can drive a full game without local rules duplication
- multiplayer state flow is deterministic and inspectable
- docs describe the real architecture, not the legacy prototype
- the remaining prototype code is either intentionally reused or removed
