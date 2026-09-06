"""Capture an isolated, rule-driven town for a reproducible guided intro."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from server.world import World
from server.model import Cognition

world = World(cognition=Cognition("demo"), restore=False)
frames, sections = [], {}
def record():
    frames.append(world.snapshot())
def step():
    world.tick(.5)
    if world.jobs:
        time.sleep(.002)
    record()
def until(predicate, maximum=1500):
    for _ in range(maximum):
        step()
        if predicate(): return
    raise RuntimeError("Demo scenario did not finish")
try:
    record()
    sections["welcome"] = [0, 0]
    for _ in range(35): step()
    sections["residents"] = [0, len(frames)-1]
    start = len(frames)-1
    world.command({"id":"intro-chat", "kind":"chat", "agent":"maya", "text":"Hello Maya, how is your morning?"})
    until(lambda: world.pending_interaction is None and not world.agents["maya"]["thinking"])
    for _ in range(8): step()
    sections["conversation"] = [start, len(frames)-1]
    # Stage an uncluttered delivery demonstration while retaining all physical
    # navigation, proximity, inventory, and task validation rules.
    world.next_social = 10**10
    for a in world.agents.values():
        world._interrupt(a)
        a["next_decision"] = a["next_reflect"] = 10**10
    start = len(frames)-1
    world.command({"id":"intro-coffee", "kind":"task", "agent":"samir", "text":"Bring a coffee to Elena"})
    until(lambda: any(t["status"]=="completed" for t in world.tasks.values()))
    sections["delivery"] = [start, len(frames)-1]
    sections["memory"] = sections["ollama"] = sections["start"] = [len(frames)-1, len(frames)-1]
    task = next(iter(world.tasks.values()))
    assert task["recipient"]=="elena"
    assert any(i["id"]==task["item_id"] for i in world.agents["elena"]["inventory"])
    output={"sections":sections,"frames":frames,"detail":world.inspect("elena"),"task":task}
    target=ROOT/".video-build/demo.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(output),encoding="utf-8")
    print("Captured",len(frames),"frames. Delivery verified; evidence:",task["evidence"])
finally:
    world.close()
