# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Three audiences share one screen, confirmed by the user as equally primary:

- **Someone evaluating the project.** Found the repo or the one-minute video, ran it locally, and is deciding in the first minutes whether this is real. They need to understand the town, talk to a resident, and see an errand actually complete.
- **Someone playing.** Returns across sessions to a saved town: routines, conversations, picnics, indoor rooms, scenario edits. Density and long-session comfort matter to them.
- **Someone studying or building on it.** Reads memories, retrieval highlighting, plans, task verification and model metrics to judge whether the agent behavior holds up.

All three are at a desktop or laptop with the server running on their own machine; the layout also has to hold on a narrow screen.

## Product Purpose

Smallworld Agents is a playable 2.5D isometric simulation of a small town where every resident keeps a routine, a memory and a plan. The player walks in as Alex, talks to residents, and assigns errands that the simulation verifies. Success is that a visitor believes the residents are actually living there, and can watch a request become a completed, evidenced outcome.

## Positioning

An interactive adaptation of the *Generative Agents* paper where the world, not the model, decides what happened. A language model proposes dialogue and actions; the simulation checks them. **Delivery means delivery:** a resident must collect an item, walk to its recipient and hand it over at close range, so a convincing model reply alone can never complete a task.

## Operating Context

- Run locally: `python -m server.app`, opened in a browser on the same machine. Cognition is offline demo rules by default, local Ollama, or an optional OpenAI adapter.
- One page holds everything: the world canvas with district shortcuts and interior views, community actions (garden, market, picnic, weather), the task list, the activity feed, town tools (playback, voice, proposals, meetings, interior objects, scenario editor, model metrics) and a resident panel with talk, memories and plans.
- The world is 576 tiles across five districts, five residents expandable to 25, four cutaway interiors, SQLite autosave and resume.
- Sessions are long and observational: the town keeps running while the player reads, so on-screen state changes without input.

## Capabilities and Constraints

- **No build step and no third-party packages**, on the server or in the browser. Plain browser JavaScript, one stylesheet, a Python standard-library server.
- **Self-hosted assets only** (user decision): any webfont must be committed and served from this repo, because the town must work with no network.
- Original artwork is drawn from committed sprite sheets through `assets/manifest.json`; the renderer composites it on a canvas. Artwork itself is not to be redrawn.
- Client files: `client/index.html`, `client/style.css`, `client/app.js`, `client/tools.js`, `client/renderer.js`, plus a standalone `asset-preview.html`.
- Server routes, APIs and simulation logic are fixed for this work.
- Terminology to keep: residents, districts, errands/tasks, needs, memories, plans, relationships, proposals, meetings, picnic, scenario, replay, offline demo mode, live mode.

## Brand Commitments

- Name **Smallworld Agents**; tagline in the header, "Every resident has a story."
- Voice is warm, plain and concrete, written about neighbors rather than systems ("Ask a resident to organize a picnic", "Walk Alex into this room"). Copy stays as written unless the user asks otherwise.
- The isometric artwork is the product's face; interface chrome supports it.

## Evidence on Hand

- Real running product with live state: `docs/media/expanded-town.png`, `docs/media/smallworld-agents-intro.mp4`, evaluation reports in `docs/evaluation/`.
- No customers, testimonials, benchmarks, pricing or deployment claims exist. Future work must not invent them.

## Product Principles

1. **The world leads.** The artwork and the living town are the product; interface chrome earns its space or leaves.
2. **Verified over asserted.** Show evidence of what actually happened — steps, blockers, completions — not model claims.
3. **One screen, three depths.** Watching, acting and inspecting coexist without the page becoming a control panel.
4. **Warm and specific.** Neighbors with names and routines, never "entities" or "agents" in the interface.
5. **Runs anywhere, offline.** Nothing may depend on a network, a build step or a package.

## Accessibility & Inclusion

Existing commitments in the markup to preserve: labelled canvas and controls, `role="status"` live regions, a visible focus ring on every interactive element, keyboard-reachable panels. The town animates continuously, so a reduced-motion path is required for any added motion.

## Scope of the current redesign

In scope: `client/index.html`, `client/style.css`, DOM produced by `client/app.js` and `client/tools.js`, and world styling inside `client/renderer.js` (ground tints, shadows, labels, speech bubbles, weather, selection rings). Out of scope: the sprite artwork itself, server logic, APIs and routes.
