# Roadmap implementation

The September 2026 update implements the remaining playable features in the existing lightweight stack. The original plan also includes research ambitions; those are distinguished from verified product behavior below.

| Area | Implemented behavior | Evidence |
| --- | --- | --- |
| Semantic memory | Owner-scoped candidates, Ollama vectors, recency and importance ranking, persisted content-hash cache, explicit lexical fallback | Cached semantic ranking test, failure test, live embedding report |
| Reflection | Accumulated importance threshold, references restricted to direct memories, originals retained, inspector distinguishes inference and reports | Reflection threshold and reference validation tests |
| Hierarchical action | Up to six validated ordered steps, explicit dependencies, evidence per completed step, physical report-back | Delivery/report, invalid later step, cancellation and resume tests |
| Reprioritization | Suspend an errand, run another, resume remaining timers and inventory; proposed chat tasks require acceptance | Suspended task and proposal tests |
| Social coordination | Walk to deliver invitations; accept or decline based on commitments; travel to appointment; record actual attendance separately | Acceptance, declined guest, attendance tests |
| Interiors | Four independent rooms with floor/back-wall layers, furniture, doorway transitions, room-specific navigation and hearing | Object-use, room visibility and save/resume tests; native Canvas render review |
| Object actions | Inspect/use capabilities, proximity checks, exclusive timed leases, needs effects, world evidence | Object duration and competing-user reservation tests |
| Persistence | World changes, memories, events, decisions and commands committed with snapshots; rollback restores in-memory state | Injected write failure and resume tests |
| Replay | Compressed checksummed states, retained timeline, read-only playback, no model regeneration | Integrity/immutability and HTTP replay tests |
| Model scheduling | At most eight queued/running jobs, player priority for local inference, per-operation time/token counts, separate embedding budget | Original priority/stale-result tests and scale run |
| Scenario editor | JSON import/edit/export, validation, population expansion, isolated new-database startup | Scenario and HTTP validation tests |
| Voice | Opt-in browser speech synthesis and review-before-send dictation where supported | Syntax reviewed; browser permissions/manual interaction pass outstanding |
| Population | Five original personas plus twenty generated residents using existing original skins | 25-resident validation and workload report |
| Evaluation | Repeatable task/inventory/collision/replay checks and memory/reflection ablation switches | Committed offline reports and local model checks |

## Deliberate scope choices

- Keep Canvas and standard-library Python instead of migrating to Phaser/FastAPI solely to satisfy an earlier technology proposal.
- Interiors are separate cutaway scenes. Building exteriors remain whole sprites; there are no upper floors, camera rotation, or a continuous roof-removal animation.
- Invitation acceptance is an explicit scheduling rule. It does not claim rich relationship-driven negotiation or inferred promises from arbitrary dialogue.
- The scenario editor exports a validated file. Applying it requires starting a new database, preventing memories and inventory from leaking between scenarios.
- Replay stores world-state samples every six simulated seconds plus commands, retaining up to 7,201 frames. It does not reconstruct every intermediate movement or reproduce live model outputs from a seed.
- Reflection depth is bounded to one. There is no general-purpose belief revision or contradiction-resolution engine.
- Crowd movement retains dynamic collision checks and replanning. Object use has explicit reservations; doors use atomic occupancy checks rather than a generalized traffic scheduler.
- No human-rated believability study, statistically powered live ablation study, external tool execution, multiplayer, or full 3D world is claimed.

## Verification limits

The new Canvas views were rendered from actual world snapshots and visually inspected. The browser automation runtime failed before opening a tab with a Windows sandbox initialization error. Automated HTTP tests cover the transport, but full browser interaction and speech permissions still need the manual checks below.

1. Assign a delivery followed by report-back; watch each plan step and transfer evidence.
2. Select an interior, walk Alex inside, and assign an object action.
3. Create an appointment and compare invited, accepted and attended counts.
4. Enter replay, scrub, play, and return; confirm the live town stays paused.
5. Enable speech, hear a new selected-resident line, dictate a message, review it, and send.
6. Export a 25-resident scenario and start it using a new database.

## Community and latency update

- **Community actions.** Plant, water, harvest, buy, prepare and share are validated plan steps with finite seeds, market supplies and resident credits. Each completed action records world evidence, and resources are included in rollback, save and resume.
- **Cooperative picnic.** The host recruits a free helper in person, grows and cooks food, receives the helper's supplies by physical handoff, invites guests, and serves only residents who attend. Rain blocks serving. Cancelling or failing the picnic cancels the helper's errand and scheduled appointment once; helper errands cannot be paused separately.
- **Latency.** A strict local parser resolves clear errands without the model, routine choices default to local rules, retrieval defaults to cached embeddings, and model contexts are compacted to a 4,096-token default. In Ollama mode, player requests cancel queued background work before the queue-capacity check.
- **Evidence.** 73 Python tests, the offline picnic report, a 25-resident community-map workload, and a small before/after `gemma4:31b` latency check. See [evaluation notes](evaluation/README.md).
- **Limits.** Helper selection and guest acceptance are scheduling rules, not negotiation. Weather is a manual switch. There is one bed per resident and no crop failure, pricing changes or restocking.

## Tick performance update

- **Measured cause.** Per-tick phase timing attributed slow updates to bursts of A* searches, not persistence.
- **Changes.**
  - Faster A* with identical paths.
  - Cached sight-line blockers.
  - A pickle-based rollback snapshot.
  - Lighter lexical retrieval and a SQL reflection threshold.
  - Finished tasks archived to SQLite after two simulated hours; the newest 30 stay live.
- **Result.** On the 25-resident workload, p95 update time dropped from about 40 ms to 15–23 ms in alternating runs against `main` on the same machine. See [evaluation notes](evaluation/README.md#tick-performance).
- **Browser pass.** In offline mode on a scratch database, the app loaded without console errors. The picnic panel ran a full picnic at 4× speed: helper recruited, supplies bought, all three residents attended and were served. District camera shortcuts and replay entry and return worked; returning left the town paused, as documented. The server no longer logs a traceback when the browser cancels a request mid-response. Speech permissions and scenario export were not exercised.
- **Limits.** Archived tasks leave live snapshots and replay frames and are not shown in the interface. They remain in the `task_archive` table.

## Map expansion update

The default map is now 24 x 24 with four new destinations and four original transparent sprites. Nine new Python checks cover preservation of old collision geometry, district reachability, boardwalk navigation, natural-language district names, actual resident travel, travel out of an interior, map validation, save migration and asset metadata. A dependency-free JavaScript check verifies the district camera targets. There are 57 Python tests in total. The original map is retained as a separate scenario, and old custom maps are not automatically replaced.
