<div align="center">

# Smallworld Agents

**A small town where every resident has a routine, a memory, and somewhere to be.**

A playable **2.5D isometric simulation** with original artwork, autonomous residents, and local language-model cognition through **Ollama**.

[Quick start](#quick-start) · [Local AI](#bring-the-town-to-life-with-ollama) · [How it works](#how-it-works) · [Roadmap](#roadmap)

<img src="assets/isometric/buildings.png" width="560" alt="Original isometric artwork: a neighborhood cafe, general store, and two homes">

*Original building artwork used in the town.*

</div>

Walk into the neighborhood as **Alex**. Meet Maya at the cafe, chat with Samir, or ask someone to bring coffee to Elena. Residents move through the world, remember their own experiences, and carry out requests that you can follow step by step.

Inspired by [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442), Smallworld Agents is a first playable adaptation of its ideas. It combines a language-model layer with a simulation that checks what actually happens.

## What you can do

| Feature | In the town |
| --- | --- |
| Explore | Eight-direction walking, isometric depth, camera pan and zoom |
| Meet residents | Five distinct residents with roles, routines, needs, and relationships |
| Talk | Proximity conversations, speech bubbles, and persistent conversation history |
| Assign errands | Deliver coffee or parcels, visit a place, meet a resident, or wait |
| Inspect memories | Personal observations, conversations, reflections, and retrieved context |
| Follow progress | Task steps, blockers, cancellations, and completion evidence |
| Keep your town | SQLite autosave and resume for residents, memories, tasks, and inventory |
| Choose cognition | Offline demo, local Ollama, or an optional OpenAI adapter |

**Delivery means delivery.** The resident must collect an item, find its recipient, and transfer it at close range. A language-model reply alone cannot mark the task complete.

## Quick start

**Requirements:** Python 3.11+ and a modern browser. No third-party Python packages or frontend build are required. Node.js is only needed for developer checks and rebuilding asset metadata.

```sh
git clone https://github.com/sumnoon/smallworld-agents.git
cd smallworld-agents
python run.py
```

Open **[localhost:8766](http://127.0.0.1:8766/)**.

A fresh clone starts in **OFFLINE DEMO**: movement and tasks work immediately, with rule-based decisions and template conversations. Press **Ctrl+C** in the terminal to save and stop.

## Bring the town to life with Ollama

With [Ollama](https://ollama.com/) installed, make sure your model is available:

```sh
ollama list
```

The tested model is **`gemma4:31b`**. Use the exact model name shown by your Ollama installation. If needed, obtain it with `ollama pull gemma4:31b`; it is a large download and requires suitable memory.

Copy `.env.example` to `.env`:

```sh
# macOS / Linux
cp .env.example .env
```

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

Then configure:

```dotenv
AGENT_PROVIDER=ollama
AGENT_MODEL=gemma4:31b
OLLAMA_BASE_URL=http://127.0.0.1:11434
AGENT_MODEL_TIMEOUT=120
AGENT_MAX_REQUESTS=1000
```

Keep Ollama running and restart `python run.py`. The interface displays **OLLAMA LIVE** and the model name. No cloud API key is needed, and the default Ollama endpoint is on your computer.

**Using a custom model folder on Windows?** Start Ollama in a separate terminal with:

```powershell
./tools/start-ollama.ps1 -ModelsDirectory 'D:\path-to-your-models'
```

The helper uses `OLLAMA_MODELS` when set, otherwise the standard user model folder. It accepts `-OllamaExecutable` for a custom installation and changes no global settings. Use it when Ollama is stopped; an existing service must already be configured for the right folder.

### What to expect from local inference

Player requests take priority over queued background decisions. One local inference request runs at a time, with an 8,192-token context, bounded output, and thinking disabled. Residents display **Thinking…** while queued or generating.

Direct tests with `gemma4:31b` produced warm responses in approximately **12–29 seconds** on the development machine; performance depends on your hardware and context length. Start at **1× speed** for slower inference.

The UI shows requests, token usage, and errors. The request cap resets when the simulation server restarts. On a provider error, the adapter waits 30 seconds before retrying and uses demo fallbacks in the meantime. It never switches from Ollama to a cloud provider automatically.

<details>
<summary><strong>Optional OpenAI configuration</strong></summary>

Set `AGENT_PROVIDER=openai`, select a Responses API model supporting structured outputs through `AGENT_MODEL`, and provide `OPENAI_API_KEY` in `.env`. Only selecting that provider sends context to OpenAI, with `store: false`. The key remains on the server.

The OpenAI adapter is covered by mocked tests; no credentialed OpenAI run has been performed.

</details>

## Your first errand

1. Select **Samir** on the map or in the residents panel.
2. Choose **Assign task** and enter: **“Bring a coffee to Elena.”**
3. Alex walks over and makes the request.
4. Watch the task card as Samir collects the coffee, finds Elena, and hands it over.
5. Inspect Elena's inventory and the recorded world events.

**Chat sends a message; Assign task starts a tracked errand.** Flexible language understanding does not add actions the world has not implemented.

| Try this | Result |
| --- | --- |
| “Deliver a parcel to Noah.” | Collect and transfer a parcel |
| “Visit the park.” | Walk to the park |
| “Meet Maya.” | Find Maya and have a conversation |
| “Wait for 2 minutes.” | Wait for two simulated minutes |
| “What do you remember?” in Chat | Discuss retrieved personal memories |

Click walkable ground to move Alex. Drag to pan, scroll to zoom, and use **Recenter** to fit the map. Use the send button or **Ctrl+Enter**. Pause the town or select 1×, 2×, or 4× speed; at 1×, six simulated seconds pass per real second.

Close the cafe to see coffee requests become blocked; reopen it to allow retries. Each resident handles one assigned task at a time.

## How it works

```mermaid
flowchart LR
    Player[Player interaction] --> World[Python simulation]
    World --> Memory[Personal memory retrieval]
    Memory --> Model[Ollama or optional provider]
    Model -->|Proposed decisions| World
    World -->|Validated actions and events| View[Isometric Canvas view]
    World <--> Save[SQLite memories and snapshots]
```

The **server owns the world**: positions, navigation, inventory, visibility, simulated time, and task completion. The model interprets requests and generates dialogue, activity choices, and reflections. Returned decisions are validated; stale decisions are discarded when an interaction changes the resident's plan.

The browser renders interpolated snapshots with Canvas. A Python HTTP server sends updates through server-sent events and receives JSON commands. Memory retrieval currently combines lexical similarity, recency, and importance.

```text
client/                 Isometric renderer and interaction panels
server/world.py         Simulation, navigation, conversations, and tasks
server/model.py         Offline, Ollama, and OpenAI cognition adapters
server/storage.py       Personal memories, event log, and saved state
scenarios/              Town layout and resident personas
assets/                 Original artwork, prompts, and frame metadata
tests/                  Simulation, provider, and HTTP tests
tools/                  Asset inspection, smoke check, and Ollama launcher
IMPLEMENTATION_PLAN.md  Research analysis and development roadmap
```

### Saving and resuming

Progress autosaves every five seconds to `data/neighborhood.sqlite3`. **Save town** saves immediately, and restarting resumes the saved world. Local settings and saves are excluded from Git.

For another town without changing your existing save:

```sh
python -m server.app --port 8767 --database data/another-town.sqlite3
```

An abrupt crash can lose the latest snapshot interval. The event log is not yet a deterministic replay system.

## Original artwork

All artwork was created for this project: AI-generated raster sprite sheets and authored SVG interface icons. The pack includes **six character sheets, 16 terrain tiles, four building exteriors, 16 props, and eight icons**—236 source frames/icons in total.

Generation prompts, measured sprite rectangles, anchors, and facing corrections are retained under `assets/`. Final sheets have verified transparency. See the [asset notes](assets/README.md) for production details and known animation limitations.

For a separate art gallery and eight-facing animation inspector:

```sh
python -m http.server 8765 --bind 127.0.0.1
```

Open [asset-preview.html](http://127.0.0.1:8765/asset-preview.html). This is a scripted art preview; the playable simulation runs on port 8766.

## Development and checks

```sh
python -m unittest discover -s tests -v
node --check client/app.js
node --check client/renderer.js
node tools/inspect-assets.mjs
```

The **26 automated tests** cover delivery and inventory conservation, blocked-task recovery, cancellation, navigation, pause, private memories and history, command deduplication, save/resume, stale cognition, local request priority, provider errors, and HTTP boundaries. CI runs Python tests and checks browser syntax and asset metadata without contacting a live model.

Live Ollama tests passed for task interpretation, dialogue, activity selection, and reflection. Running-server checks also verified physical deliveries and restored saved progress.

`python tools/check-running-simulation.py` runs an additional delivery check against an **offline** server on port 8766. It creates an actual task and consumes one coffee in that saved town.

## Scope and roadmap

This is a first playable prototype, **not a reproduction of the paper's experiments**. The current town has one walkable ground level, exterior buildings, and a fixed camera orientation. Generated walk cycles retain some pose variation. Crowd navigation can still benefit from stronger reservations. Arbitrary real-world tool execution is outside the current scope.

Planned improvements:

- Semantic embedding retrieval with memory-accuracy evaluations.
- Hierarchical plans and richer relationship-dependent dialogue.
- Coordinated errands involving multiple residents.
- Transactional saves and deterministic replay.
- Enterable interiors with separate roof and wall layers.
- Evaluations of task success, persona consistency, latency, and inference cost before scaling the population.

See the [implementation plan](IMPLEMENTATION_PLAN.md) for the detailed design and research comparison.

## References

- [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) — the research inspiration.
- [Authors' implementation](https://github.com/joonspk-research/generative_agents) — reference architecture and prompts.
- [Ollama chat API](https://docs.ollama.com/api/chat) and [structured outputs](https://docs.ollama.com/capabilities/structured-outputs) — the local cognition interface.
