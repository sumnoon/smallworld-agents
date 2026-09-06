"""Exercise the public API of an already-running local demo; creates one coffee task."""
import json
import time
import urllib.request
import uuid

BASE = "http://127.0.0.1:8766"


def get():
    with urllib.request.urlopen(BASE + "/api/state", timeout=5) as response:
        return json.load(response)


def command(**data):
    request = urllib.request.Request(BASE + "/api/command", json.dumps({"id": uuid.uuid4().hex, **data}).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


initial = get()
if initial["model"]["mode"] != "demo":
    raise SystemExit("Acceptance check requires demo mode; no live model calls were made.")
agent = next(a for a in initial["agents"] if a["id"] in ("maya", "samir") and not a["task"])
before = {task["id"] for task in initial["tasks"]}
try:
    command(kind="pause", paused=False)
    command(kind="speed", speed=4)
    print(command(kind="task", agent=agent["id"], text="Bring a coffee to Noah"), flush=True)
    deadline = time.monotonic() + 50
    last = None
    while time.monotonic() < deadline:
        snapshot = get()
        task = next((t for t in snapshot["tasks"] if t["id"] not in before and t["agent"] == agent["id"]), None)
        status = (task["status"], task["step"]) if task else ("approaching", 0)
        if status != last:
            print(status, flush=True)
            last = status
        if task and task["status"] == "completed":
            recipient = next(a for a in snapshot["agents"] if a["id"] == "noah")
            assert any(item["id"] == task["item_id"] for item in recipient["inventory"])
            assert len(task["evidence"]) >= 2
            print("PASS: player approach, request interpretation, pickup, navigation, physical transfer, and completion through public API.", flush=True)
            break
        if task and task["status"] in ("failed", "cancelled"):
            raise AssertionError(task)
        time.sleep(.25)
    else:
        print(json.dumps({"pending": snapshot["pending_interaction"], "task": task,
                          "agents": [{k: a[k] for k in ("id", "x", "y", "status")} for a in snapshot["agents"]]}, indent=2))
        raise AssertionError("Timed out before delivery completed")
finally:
    command(kind="speed", speed=initial["speed"])
    command(kind="pause", paused=initial["paused"])
    command(kind="save")
