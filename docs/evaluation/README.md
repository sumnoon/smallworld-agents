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
