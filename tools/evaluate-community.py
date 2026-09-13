"""Reproducible cooperative picnic acceptance run (no network or browser)."""
import itertools
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.world import World, distance
from server.model import Cognition

world = World(cognition=Cognition("demo"),restore=False)
try:
    world.next_social = 10**10
    for agent in world.agents.values():
        agent["next_decision"] = agent["next_reflect"] = 10**10
    task = world.create_task("maya","Organize a picnic",{"kind":"picnic"})
    collisions = 0
    work = Path(".video-build")
    work.mkdir(exist_ok=True)
    captured = False
    for tick in range(6000):
        world.tick(.5)
        collisions += any(distance(a,b)<.419 for a,b in itertools.combinations(world.agents.values(),2))
        if not captured and world.agents["maya"].get("working",{}).get("kind")=="water":
            state = world.snapshot();state["layout"] = world.layout
            (work/"community-garden-state.json").write_text(json.dumps(state),encoding="utf-8")
            captured = True
        if task["status"] in ("completed","failed"):
            break
    state = world.snapshot();state["layout"] = world.layout
    (work/"community-picnic-state.json").write_text(json.dumps(state),encoding="utf-8")
    ids = [i["id"] for a in world.agents.values() for i in a["inventory"]]
    result = {"provider":"demo", "status":task["status"],"ticks":tick+1,"simulated_minutes":round((world.time-32400)/60,2),
              "served":task["picnic"]["served"],"helper":task["picnic"]["helper"],"helper_status":world.tasks[task["picnic"]["helper_task"]]["status"],
              "collision_ticks":collisions,"unique_inventory":len(ids)==len(set(ids)),"seeds_remaining":world.community["seeds"],
              "market_supplies_remaining":world.community["supplies"],"events":world.storage.events(200)}
    output = Path("docs/evaluation/community-picnic.json")
    output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="events"},indent=2))
    if task["status"]!="completed" or collisions or len(ids)!=len(set(ids)):
        raise SystemExit(1)
finally:
    world.close()
