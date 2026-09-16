# Autonomous gardening under seed contention

`tools/evaluate-gardening.py` measures what 25 self-directed residents do with 12 seeds over five simulated hours, using the unchanged world engine. It is an offline development measurement, not a human study or a performance benchmark. The saved report is `autonomous-gardening-25.json`.

**Baseline before the seed-release change.** This run measured behavior before autonomous plantings were changed to fail as soon as seeds run out. Its seed-starvation findings describe the earlier wait until the four-hour deadline, and they are kept unchanged as that baseline.

## Command and environment

```sh
python tools/evaluate-gardening.py --output docs/evaluation/autonomous-gardening-25.json
```

- **Defaults:** 25 non-visitor residents, 12 seeds, no beds, normal starting inventories (empty) and positions, 6,000 updates at `dt=0.5` and speed 1 (3 simulated seconds each), 09:00 to 14:00.
- **Isolation:** explicit demo cognition (local rules), an in-memory SQLite database, no `.env` and no player save. The report records the `AGENT_*` mode flags; all were unset for this run.
- **Controlled workload:** spontaneous conversations and reflections are disabled, and every resident is due for a decision at the first update. Needs, routines, later decision timing, movement, retries, resources and deadlines are the engine's own. There are no player commands, no restocking, no inventory removal, no forced arrivals and no fast-forwarded clock.
- **Source:** `cd8785d`, recorded as `dirty`. The changed paths are the uncommitted autonomous planting changes (`server/community.py`, `tests/test_community.py`) and the four evaluator files (`tools/evaluate-gardening.py`, `tests/test_evaluate_gardening.py`, and both report files).
- **How this run was made:** a person ran the command above directly from the repository root on 2026-09-15, using the corrected evaluator with the per-update invariant checks. It exited with code 0. Wall time was 23.66 s on that machine; it is descriptive only.

Winners depend on travel distance and update order, and task and item IDs are random, so repeated runs can pick different residents and produce slightly different times.

## Results

| Measure | Value |
| --- | --- |
| Gardening tasks accepted (all autonomous) | 25 plant, 12 water, 12 harvest |
| Terminal outcomes | plant 12 completed / 13 failed; water 12 completed; harvest 12 completed; none still open |
| Residents who planted, watered, harvested | 12, 12, 12 (the same residents) |
| Complete plant-water-harvest cycles | 12 |
| Seeds | 12 initial, 0 final; last seed planted at 09:04:51 (4.85 min) |
| Beds at end | 0 (12 planted, 12 harvested) |
| Vegetables at end | 12, one each for the 12 growers |
| Events read (all kinds) | 4,676, including 3,717 `task_blocked` |
| Tasks resolved | 49: 38 from live state, 11 from `task_archive` |
| Invariants | passed, 0 violations; no report blockers; exit code 0 |

Every successful action is listed in `successful_actions` with its task, action event, outcome event, site and harvested item ID.

## Blocked tasks and time

Unique blocked tasks, repeated `task_blocked` events, and blocked time are separate measures. A blocked task emits another event on every 60-second retry. Blocked time is sampled: each 3-second update counts once for every gardening task whose status is `blocked` after that update.

| Measure | Value |
| --- | --- |
| Unique blocked tasks | 14 plant, 3 harvest |
| `task_blocked` events: "No seeds remain" | 3,028 across 13 tasks |
| `task_blocked` events: "The work site is blocked; retrying" | 689 across 11 tasks |
| Peak concurrently blocked tasks | 16 at 09:15:03 (13 seed-starved plantings, 3 harvests) |
| Sampled blocked resident-minutes | 3,711.9 |

**Seed losers stay occupied until the deadline.** All 13 planting tasks that got no seed were created at 09:00:03 and first blocked between 09:00:06 and 09:09:51. Each stayed on its resident for 240.05 minutes, 230.25–235.7 sampled minutes of them blocked, and logged 231–236 blocked events. While the task was open, the resident could take no other task. Seven of the 13 also logged "The work site is blocked; retrying" before the seeds ran out.

**Deadline enforcement.** All 13 seed-starved tasks were observed past their deadline. Each failed with "Community task deadline elapsed" at 13:00:06, one update (3 s) after the 13:00:03 deadline, because the engine requires `time > deadline`. Each emitted exactly one `task_failed` event (events 4555–4567), and each resident was released on that same first processed update. No seeds remained afterwards; what those residents did in the last hour was not recorded.

**Seven harvests finished only after the losers were released.** Five harvests finished by 09:13:54. The other seven finished between 13:00:48 and 13:06:36, just after the 13:00:06 release. Their tasks ran 228.7–232.75 minutes (about 3.8 hours). Minutes before the deadline are the deadline minus the harvest time; the deadline is creation plus four hours, as in every deadline the report records:

| Resident | Harvest task created | Finished | Deadline | Minutes before deadline | Blocked |
| --- | --- | --- | --- | --- | --- |
| Noah | 09:08:03 | 13:00:48 | 13:08:03 | 7.25 | no events |
| Maya | 09:08:24 | 13:00:48 | 13:08:24 | 7.6 | no events |
| Iris | 09:15:00 | 13:06:36 | 13:15:00 | 8.4 | 226 sampled min, 226 events |
| Zara | 09:12:27 | 13:03:18 | 13:12:27 | 9.15 | 228 sampled min, 228 events |
| Arun | 09:13:48 | 13:03:48 | 13:13:48 | 10.0 | 227 sampled min, 227 events |
| Omar | 09:11:39 | 13:01:27 | 13:11:39 | 10.2 | no events |
| Rafi | 09:12:48 | 13:01:30 | 13:12:48 | 11.3 | no events |

Zara, Arun and Iris were blocked with "The work site is blocked; retrying". Their deadlines are recorded in the report. Noah, Maya, Omar and Rafi logged no blocked events, so their deadlines are derived from their recorded creation times.

One possible explanation is that residents waiting on seed-starved plantings stood in the garden and blocked paths or goal tiles. Positions were not recorded, so this cause is inferred, not verified. The seven late harvests finished 7.25–11.3 minutes before their own four-hour deadlines. The smallest margin was 7 minutes 15 seconds; a longer delay could have caused a harvest task to reach its deadline before completion.

## Invariants checked

Any violation exits with code 1 and lists task and event IDs. A violation is kept even if later state repairs it. If no autonomous plant-water-harvest cycle completes, the evaluator exits with code 2 and names that blocker.

**As each event is read** (after every update, and once more at the end for any remaining rows):

- An action event must belong to a completed gardening task of the same kind, by the task's owner, at the owner's bed, and be listed in that task's evidence. A task may have only one action event.
- A harvest event's item ID must be present and not seen before.
- A `task_completed` event for a gardening task must have exactly one action event. A failed or cancelled gardening task must have no action events or evidence.

**After every update:**

- Seeds stay nonnegative, and initial minus current seeds equals `community_plant` events read so far.
- Bed count equals initial beds plus plants minus harvests read so far.
- Vegetables held by residents equal the initial vegetables plus harvested item IDs, with no extras or missing items.
- No resident holds two open autonomous gardening tasks.
- A task past its deadline whose holder was processed on that update must have status `failed` with blocker "Community task deadline elapsed", exactly one `task_failed` event on that update, and its resident released. Cancellation or any other outcome is a violation. If the task is still open, that is also a violation, unless its holder was skipped because of a conversation or model call.

**At the end:**

- Each task is resolved once from live state or `task_archive`, including tasks archived before they were seen live.
- Each completed gardening task has exactly one matching action event, and each terminal task has exactly one outcome event that matches its status. Open tasks have none.
- Action events that reference no gardening task are violations.
- Replaying action events from the initial beds reproduces the final bed owners, with no second planting of a bed and no harvest without a bed.
- The seed and vegetable totals are rechecked against the final state.

## Limitations

- One run of one controlled workload. Conversations and reflections are off, and every resident starts due at once, which maximizes simultaneous dispatch. A naturalistic town would stagger demand.
- Resident positions and movement stalls are not recorded, so the harvest obstruction cause is inferred.
- Blocked time is sampled per update, not measured continuously.
- No browser, tick-performance or model-provider behavior was measured.

## Follow-up questions for planning

These need separate plans; nothing here changes world behavior.

1. **Seed starvation (since addressed).** Should a planting that finds no seeds give up or yield sooner than the four-hour community deadline, or should dispatch reserve seeds? Measured: 13 residents held planting tasks for 240.05 minutes each, with 3,028 seed-shortage retry events. Autonomous plantings now fail with "No seeds remain" as soon as seeds run out, which releases the resident; player plantings still wait and retry. Seed reservation was not added.
2. **Possible garden obstruction by waiting residents.** First confirm the cause by recording positions during the stalled harvests. If waiting residents are in the way, should a blocked resident wait away from the shared garden? Measured: seven harvests finished about 3.8 hours after they started, just after the losers were released, 7.25–11.3 minutes before their deadlines; four of them came within 9.15 minutes of failing. The obstruction itself is inferred, not observed.
