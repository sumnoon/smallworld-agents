"""Repeatable simulation acceptance and scale checks; no human-study claims."""
import argparse
import itertools
import json
import os
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.world import World, distance
from server.model import Cognition


def evaluate(population=5, ticks=1200, retrieval=True, reflections=True):
    world = World(cognition=Cognition("demo"),restore=False,residents=population)
    world.semantic.enabled = retrieval
    world.reflections_enabled = reflections
    latency, collisions = [],0
    start = time.monotonic()
    try:
        for a in world.agents.values():
            a["next_decision"] = a["next_reflect"] = 10**10
        world.next_social = 10**10
        request = "Bring coffee to Elena then report back"
        actor = world.agents["samir"]
        task = world.create_task("samir",request,world.fallback.task(world._context(actor,request,request=request)))
        # Keep the task scenario reproducible; autonomous load follows it.
        for _ in range(1500):
            world.tick(.5)
            if task["status"] in ("completed","failed"):
                break
        delivery = {"status":task["status"],"steps_completed":len(task["step_results"]),"transfer_count":sum(e["kind"]=="transfer" for e in world.storage.events(1000))}
        for a in world.agents.values():
            if a["id"] != "visitor":
                a["next_decision"] = a["next_reflect"] = world.time
        world.next_social = world.time
        for _ in range(ticks):
            t = time.perf_counter()
            world.tick(.5)
            latency.append((time.perf_counter()-t)*1000)
            if any(distance(a,b)<.419 for a,b in itertools.combinations(world.agents.values(),2)):
                collisions += 1
            if world.jobs:
                time.sleep(.001)
        frames = world.storage.replay_index()
        for frame in frames:
            world.storage.replay_frame(frame["id"])
        ids = [item["id"] for a in world.agents.values() for item in a["inventory"]]
        return {"population":population,"provider":"demo","retrieval":retrieval,"reflections":reflections,"ticks":ticks,
            "delivery_and_report":delivery,"collision_ticks":collisions,"unique_inventory":len(ids)==len(set(ids)),
            "stock_nonnegative":all(n>=0 for n in world.stock.values()),"replay_frames_verified":len(frames),
            "tick_ms_median":round(statistics.median(latency),3),"tick_ms_p95":round(sorted(latency)[int(len(latency)*.95)],3),
            "wall_seconds":round(time.monotonic()-start,2),"events":world.storage.db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "human_believability":"not evaluated"}
    finally:
        world.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--population",type=int,choices=(5,25),default=5)
    parser.add_argument("--ticks",type=int,default=1200)
    parser.add_argument("--ablate",choices=("none","retrieval","reflection"),default="none")
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    if not 1 <= args.ticks <= 100000:
        parser.error("ticks must be 1-100000")
    result = evaluate(args.population,args.ticks,args.ablate!="retrieval",args.ablate!="reflection")
    rendered = json.dumps(result,indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(rendered+"\n")
    if result["collision_ticks"] or not result["unique_inventory"] or not result["stock_nonnegative"] or result["delivery_and_report"]["status"] != "completed":
        raise SystemExit(1)
