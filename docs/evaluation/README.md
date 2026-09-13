# Evaluation notes

These are development measurements, not a replication of the Generative Agents human study. Reports were collected on the development Windows machine with Python 3.14. Timing varies by machine, model warmth and worker scheduling.

| Run | Delivery and report | Overlap ticks | Inventory unique | Median / p95 update |
| --- | --- | --- | --- | --- |
| Five residents | Completed | 0 | Yes | 1.03 / 2.39 ms |
| 25 residents | Completed | 0 | Yes | 6.94 / 17.10 ms |
| Retrieval disabled | Completed | 0 | Yes | 0.92 / 2.08 ms |
| Reflection disabled | Completed | 0 | Yes | 0.97 / 2.14 ms |
| 25 residents, expanded map with community systems | Completed | 0 | Yes | 8.72 / 24.35 ms |

The last row is `community-scale-25.json`. After the snapshot write was reduced to a single serialization per save, a repeat run measured 8.61 / 24.94 ms, which is within run-to-run noise; most update time is elsewhere.

## Tick performance

Per-tick phase timing on the 25-resident workload showed that slow (p95) ticks were dominated by pathfinding: about 21 of 30 ms, across 4–8 searches in the same tick. Saving and replay recording were a few milliseconds each. The changes:

- A* checks neighbors against one merged obstacle set and skips stale heap entries. Search order and resulting paths are unchanged.
- Sight lines test a cached set of view-blocking cells instead of looping over every building per step.
- The rollback snapshot taken before each tick uses `pickle`, an exact copy of the plain-data state that is cheaper than `copy.deepcopy`.
- Lexical retrieval caches tokens per text and decodes evidence only for the memories it returns.
- The reflection threshold is summed in SQL.
- Tasks finished more than two simulated hours ago move to a `task_archive` table, keeping the newest 30, so per-tick copies and saves stay bounded.

Both versions were run alternately in one session with `python tools/evaluate.py --population 25`:

| Run | `main` median / p95 | This change median / p95 |
| --- | --- | --- |
| 1 | 13.64 / 39.68 ms | 9.17 / 22.96 ms |
| 2 | 10.62 / 39.85 ms | 5.34 / 15.38 ms |

Every run completed the delivery with zero overlap ticks. The machine was busier than for the earlier rows (`main` previously measured 24.94 ms at p95), so compare within this table only. The second report is `tick-performance-25.json`. The remaining spikes come from several residents building model contexts in the same tick (about 2.4 ms each) and from replay frames, which are recorded every other update at this time step.

## Cooperative picnic

`python tools/evaluate-community.py` runs one offline picnic with Maya as host and writes `community-picnic.json`. The committed run completed in 571 updates (28.55 simulated minutes): Noah accepted the supply errand and finished it, and Maya, Noah and Elena were served at the plaza. There were no overlap ticks, item IDs stayed unique, and exactly one seed and one market supply were consumed. It exits nonzero if the picnic fails, residents overlap, or an item is duplicated.

## Latency defaults

`local-latency.json` compares one Maya chat reply with `gemma4:31b` before and after the compact-context defaults. Before: 17.0 s and 1,211 tokens. After: 40.4 s cold (30.8 s of it model load), then 8.1 s and 7.9 s warm, using 344 tokens. Generation ran at about 3 tokens per second on the development machine, so shorter outputs account for most of the gain. The local errand parser took 0.8 ms. These are a handful of calls, not a latency distribution.

Each offline run performs the task scenario, then 1,200 updates (one simulated hour at the test step) with autonomous activity. Every retained replay frame is decoded and hash-checked. Overlap detection compares each pair of residents at every update; it does not establish optimal routing or absence of all possible traffic deadlocks. Stock must remain nonnegative and item IDs unique.

```sh
python tools/evaluate.py --population 5 --output data/baseline.json
python tools/evaluate.py --population 25 --output data/scale.json
python tools/evaluate.py --ablate retrieval --output data/no-retrieval.json
python tools/evaluate.py --ablate reflection --output data/no-reflection.json
python -m unittest discover -s tests -v
```

Ablations are functional switches and invariant checks. Similar task success is expected because the world engine owns physical actions. These offline results do not measure the contribution of memory or reflection to language-model believability.

## Local model checks

- `gemma4:31b` produced a valid coffee delivery followed by report-back plan in 82.18 seconds, using 1,482 tokens. The output was accepted by world validation. This was one request, not a latency distribution.
- `embeddinggemma` retrieved Elena's gardening experience for a query about growing flowers in 7.34 seconds on its first call; the batch used 28 tokens. This is a semantic integration check, not a memory benchmark.
- A second end-to-end run used local embeddings and `gemma4:31b` through the actual cognition worker, then completed both physical task steps with no provider failures. It used 1,339 chat tokens and 40 embedding tokens; total worker latency was 99.41 seconds. See `live-end-to-end.json`.
- OpenAI remains covered by mocked responses, without a credentialed integration run.

## Human evaluation protocol (not yet conducted)

For each configuration (full cognition, no retrieval, no reflection), record at least ten sessions with the same resident profiles and task prompts. Randomize recording order and hide the condition from reviewers. Ask reviewers to score each on a 1-5 scale:

1. Identity and speaking-style consistency.
2. Correct recall and source attribution.
3. Plausible daily activity and response to interruptions.
4. Social coherence, commitments and follow-through.
5. Overall believability, with a free-text explanation.

Count hallucinated completions separately using authoritative event evidence. Report task success, invalid decisions, request failures, token use, and latency alongside human scores. Publish sample counts and uncertainty; do not infer human performance from the offline invariant reports.
