"""Authoritative simulation: models propose; this module owns physical effects."""
import copy
import heapq
import json
import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .model import Cognition, ModelError
from .storage import Storage
from .maps import obstacle_cells

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"completed", "failed", "cancelled", "declined"}


def distance(a, b):
    if a.get("room", "") != b.get("room", ""):
        return math.inf
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


class CommandError(ValueError):
    pass


class BaseWorld:
    def __init__(self, database=":memory:", cognition=None, restore=True):
        self.layout = self.initial_layout()
        self.storage = Storage(database)
        self.cognition = cognition or Cognition()
        self.fallback = Cognition("demo")
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1 if self.cognition.mode == "ollama" else 2, thread_name_prefix="cognition")
        self.jobs = []
        self.time = 9 * 3600.0
        self.speed = 1
        self.paused = False
        self.cafe_open = True
        self.stock = {"coffee": 12, "parcel": 8}
        self.tasks = {}
        self.conversations = {}
        self.pending_interaction = None
        self.last_saved = 0
        self.next_social = self.time + 20
        self.blocked = obstacle_cells(self.layout)
        self.agents = {}
        for profile in self.layout["residents"]:
            self.agents[profile["id"]] = {**profile, "x": float(profile["x"]), "y": float(profile["y"]),
                "path": [], "face": 0, "moving": False, "status": "Ready to explore" if profile["id"] == "visitor" else "Enjoying the morning",
                "inventory": [], "task": None, "conversation": None, "revision": 0, "thinking": False,
                "needs": {"energy": 85.0, "hunger": 20.0, "social": 70.0}, "known_positions": {},
                "relationships": {}, "bubble": "", "bubble_until": 0, "next_decision": self.time + 20,
                "next_observe": 0, "next_reflect": self.time + 600, "cooldown": 0, "stalled": 0,
                "routine": None, "retrieved": []}
        saved = self.storage.load() if restore else None
        if saved:
            self.layout = saved.get("layout",self.layout)
            self.blocked = obstacle_cells(self.layout)
            self.time = saved["time"]
            self.agents = saved["agents"]
            self.tasks = saved["tasks"]
            self.stock = saved["stock"]
            self.cafe_open = saved["cafe_open"]
            self.paused = saved.get("paused", False)
            self.speed = saved.get("speed", 1)
            self.next_social = self.time + 20
            for a in self.agents.values():
                a["thinking"] = False
                a["conversation"] = None
                a["revision"] += 1
            for task in self.tasks.values():
                if task.get("conversation"):
                    task.pop("conversation", None)
            self.event("system", "resume", "Resumed the saved neighborhood.")
        else:
            for a in self.agents.values():
                self.storage.memory(a["id"], "identity", f"My name is {a['name']}. I am {a['role']}. {a['bio']}", self.time, 9)
            self.event("system", "start", "A new morning in the neighborhood.")
        self.observe()

    def event(self, actor, kind, text, payload=None):
        return self.storage.event(self.time, actor, kind, text, payload)

    def valid(self, x, y, extra=()):
        return 0 <= x < self.layout["size"] and 0 <= y < self.layout["size"] and (x, y) not in self.blocked and (x, y) not in extra

    def pathfind(self, actor, goal, extra=()):
        end = round(goal["x"]), round(goal["y"])
        if not self.valid(*end, extra):
            return None
        others = [b for b in self.agents.values() if b is not actor and b.get("room", "") == actor.get("room", "")]
        extra = set(extra) | {(round(b["x"]), round(b["y"])) for b in others
                              if (round(b["x"]), round(b["y"])) != end}
        # Replanning can happen between tiles, on the near side of a resident.
        # Connect to a reachable grid center instead of skipping across the
        # rounded start tile (which may contain that resident).
        def reachable_start(cell):
            if not self.valid(*cell, extra):
                return False
            steps = max(1, math.ceil(math.dist((actor["x"], actor["y"]), cell) * 12))
            previous = round(actor["x"]), round(actor["y"])
            for i in range(1, steps + 1):
                point = {"x": actor["x"] + (cell[0] - actor["x"]) * i / steps,
                         "y": actor["y"] + (cell[1] - actor["y"]) * i / steps, "room":actor.get("room", "")}
                current = round(point["x"]), round(point["y"])
                if not self.valid(*current) or any(distance(point, b) < .42 for b in others):
                    return False
                if current[0] != previous[0] and current[1] != previous[1]:
                    if not self.valid(current[0], previous[1]) or not self.valid(previous[0], current[1]):
                        return False
                previous = current
            return True
        rounded = round(actor["x"]), round(actor["y"])
        candidates = [(rounded[0] + dx, rounded[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        candidates.sort(key=lambda p: math.dist((actor["x"], actor["y"]), p))
        start = next((p for p in candidates if reachable_start(p)), None)
        if start is None:
            return None
        prefix = [{"x": start[0], "y": start[1]}] if math.dist((actor["x"], actor["y"]), start) > .01 else []
        if start == end:
            return prefix
        frontier = [(0, start)]
        cost, parent = {start: 0}, {}
        while frontier:
            _, pos = heapq.heappop(frontier)
            if pos == end:
                path = []
                while pos != start:
                    path.append({"x": pos[0], "y": pos[1]})
                    pos = parent[pos]
                return prefix + list(reversed(path))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if not (dx or dy):
                        continue
                    nxt = pos[0] + dx, pos[1] + dy
                    if not self.valid(*nxt, extra):
                        continue
                    if dx and dy and (not self.valid(pos[0] + dx, pos[1], extra) or not self.valid(pos[0], pos[1] + dy, extra)):
                        continue
                    new = cost[pos] + math.hypot(dx, dy)
                    if new < cost.get(nxt, math.inf):
                        cost[nxt], parent[nxt] = new, pos
                        heapq.heappush(frontier, (new + math.dist(nxt, end), nxt))
        return None

    def visible(self, a, b, radius=4):
        if distance(a, b) > radius:
            return False
        steps = max(1, math.ceil(distance(a, b) * 4))
        for i in range(1, steps):
            x = round(a["x"] + (b["x"] - a["x"]) * i / steps)
            y = round(a["y"] + (b["y"] - a["y"]) * i / steps)
            # World geometry blocks perception; decorative props do not block sight.
            for building in self.layout["buildings"]:
                if building["x"] - 2 <= x <= building["x"] + 1 and building["y"] - 2 <= y <= building["y"] + 1:
                    return False
            for landmark in self.layout.get("landmarks",[]):
                x0,y0,x1,y1 = landmark["footprint"]
                if landmark.get("blocks_view") and x0<=x<=x1 and y0<=y<=y1:
                    return False
        return True

    def observe(self):
        for a in self.agents.values():
            if a["next_observe"] > self.time:
                continue
            a["next_observe"] = self.time + 12
            for b in self.agents.values():
                if a is b or not self.visible(a, b):
                    continue
                first = b["id"] not in a["known_positions"]
                a["known_positions"][b["id"]] = {"x": b["x"], "y": b["y"], "time": self.time, "room":b.get("room", "")}
                if first and a["id"] != "visitor":
                    seq = self.event(a["id"], "observation", f"{a['name']} noticed {b['name']} nearby.")
                    self.storage.memory(a["id"], "observation", f"I saw {b['name']} in the neighborhood.", self.time, 3, [seq])

    def _context(self, a, query="", **extra):
        memories = self.storage.retrieve(a["id"], query or a["status"], self.time)
        a["retrieved"] = [m["id"] for m in memories]
        return {"agent": {k: copy.deepcopy(a[k]) for k in ("id", "name", "role", "bio", "status", "plan", "needs", "inventory")},
                "time": self.time, "places": self.layout["places"], "memories": memories,
                "observations": [{"name": b["name"], "status": b["status"]} for b in self.agents.values() if b is not a and self.visible(a, b)],
                "residents": [{"id": b["id"], "name": b["name"]} for b in self.agents.values()],
                "active_task": copy.deepcopy(self.tasks.get(a["task"])), **extra}

    def yield_to_player(self, method, extra):
        """Cancel queued background jobs so a player request waits for at most the current call."""
        if self.cognition.mode != "ollama" or not (method == "task" or (method == "chat" and extra.get("other") == "visitor")):
            return
        for job in self.jobs:
            if job["method"] == "task" or job.get("other") == "visitor" or job["future"].cancelled():
                continue
            if job["future"].cancel():
                owner = self.agents[job["agent"]]
                if owner["revision"] == job["revision"]:
                    owner["thinking"] = False
                    owner["next_decision"] = max(owner["next_decision"], self.time + 30)
                    if job["method"] == "reflect":
                        owner["next_reflect"] = self.time + 60
                conv = self.conversations.get(job.get("conversation"))
                if conv:
                    conv["waiting"] = False
                    conv["next_turn"] = self.time + 30

    def submit(self, method, a, context, **extra):
        self.yield_to_player(method, extra)
        a["thinking"] = True
        self.jobs.append({"future": self.pool.submit(self._cognition_job, method, context), "method": method,
                          "agent": a["id"], "revision": a["revision"], "context": context, "queued_at":time.monotonic(), **extra})

    def _jobs(self):
        pending = []
        for job in self.jobs:
            if job["future"].cancelled():
                continue
            if not job["future"].done():
                pending.append(job)
                continue
            a = self.agents[job["agent"]]
            if a["revision"] != job["revision"]:
                continue
            a["thinking"] = False
            try:
                result = self.consume_result(job, job["future"].result())
            except Exception:
                self.event(a["id"], "model_fallback", f"{a['name']} is using a demo fallback because the model could not respond.")
                if job["method"] == "task":
                    from .performance import fast_task
                    result = fast_task(job["context"]) or {"kind":"unsupported", "reply":"The model could not interpret this request. Please try a specific supported action."}
                else:
                    result = getattr(self.fallback, job["method"])(job["context"])
                job["source"] = "demo_fallback"
                self.storage.decision(self.time,a["id"],job["method"],{"mode":"demo_fallback","result":result})
            try:
                if job["method"] == "task":
                    task = self.create_task(a["id"], job["context"]["request"], result)
                    task["interpretation"] = job.get("source",self.cognition.mode)
                elif job["method"] == "chat":
                    other = job.get("other", "visitor")
                    if other == "visitor" and not job.get("conversation"):
                        message = job["context"].get("message", "")
                        spec = self.fallback.task({**job["context"], "request": message})
                        if spec["kind"] != "unsupported":
                            self.propose(a["id"],message)
                            result = "That was sent as chat, so I haven't started a new task. Select Assign task and send that request to put it in my task list."
                    self.speak(a["id"], str(result)[:360], [other])
                    if job.get("conversation") in self.conversations:
                        conv = self.conversations[job["conversation"]]
                        conv["history"].append({"name": a["name"], "text": str(result)[:360]})
                        conv["turn"] += 1
                        conv["next_turn"] = self.time + 24
                        conv["waiting"] = False
                    else:
                        a["status"] = "Finished talking with Alex"
                        a["cooldown"] = self.time + 90
                        a["next_decision"] = self.time + 30
                elif job["method"] == "decide":
                    place = result.get("place")
                    if place not in self.layout["places"]:
                        raise CommandError("The model proposed an unknown location")
                    minutes = max(1, min(20, int(result["minutes"])))
                    a["routine"] = {"place": place, "activity": str(result["activity"])[:100], "duration": minutes * 60, "arrived": None}
                    a["next_decision"] = self.time + 60
                elif job["method"] == "reflect":
                    allowed = {m["id"] for m in job["context"]["memories"] if m["kind"] != "reflection"}
                    refs = [n for n in result.get("memory_ids", []) if type(n) is int and n in allowed]
                    if refs and result.get("insight"):
                        a["last_reflection"] = self.time
                        self.storage.memory(a["id"], "reflection", str(result["insight"])[:500], self.time, 7,
                                            [{"memory_id": n} for n in refs])
                        self.event(a["id"], "reflection", f"{a['name']} reflected on recent experiences.")
            except (ValueError, TypeError, KeyError) as exc:
                if job["method"] == "task":
                    tid = "task_"+uuid.uuid4().hex[:10]
                    self.tasks[tid] = {"id":tid,"agent":a["id"],"request":job["context"]["request"],"kind":"unsupported","status":"declined","steps":[],"step":0,"evidence":[],"blocker":str(exc),"created":self.time}
                    self.event(a["id"],"task_declined",str(exc),{"task":tid})
                self.speak(a["id"], str(exc)[:180], ["visitor"])
                a["next_decision"] = self.time + 30
        self.jobs = pending

    def speak(self, actor, text, recipients=()):
        a = self.agents[actor]
        a["bubble"], a["bubble_until"] = text[:360], self.time + 36
        seq = self.event(actor, "dialogue", f"{a['name']}: {text}", {"recipients": list(recipients)})
        for owner in set([actor, *recipients]):
            self.storage.memory(owner, "conversation", f"{a['name']}: {text}", self.time, 6, [seq])
        return seq

    def _interrupt(self, a):
        if a["conversation"]:
            self.end_conversation(a["conversation"])
        a["revision"] += 1
        for job in self.jobs:
            if job["agent"] == a["id"]:
                job["future"].cancel()
        a["thinking"] = False
        a["path"] = []
        a["routine"] = None

    def create_task(self, agent_id, text, spec):
        a = self.agents[agent_id]
        if a["task"] and self.tasks[a["task"]]["status"] not in TERMINAL:
            raise CommandError("Please cancel or finish my current task first.")
        kind, recipient, place, item = (spec.get(k, "") for k in ("kind", "recipient", "place", "item"))
        if kind not in ("deliver", "visit", "meet", "wait"):
            raise CommandError(spec.get("reply") or "I need a clearer task.")
        if kind in ("deliver", "meet") and (recipient not in self.agents or recipient == agent_id):
            raise CommandError("Please name another resident as the recipient.")
        if kind == "deliver" and item not in ("coffee", "parcel"):
            raise CommandError("I can deliver coffee or a parcel in this neighborhood.")
        if kind == "visit" and place not in self.layout["places"]:
            raise CommandError("Please choose the cafe, shop, park, home, or studio.")
        minutes = spec.get("minutes", 0)
        if kind == "wait" and (type(minutes) is not int or not 1 <= minutes <= 30):
            raise CommandError("Please specify a wait between 1 and 30 simulated minutes.")
        self._interrupt(a)
        task_id = "task_" + uuid.uuid4().hex[:10]
        steps = {"deliver": ["Collect the item", "Find the recipient", "Hand over the item"],
                 "visit": ["Walk to the destination"], "meet": ["Find the resident", "Have a conversation"],
                 "wait": ["Wait for the requested duration"]}[kind]
        task = {"id": task_id, "agent": agent_id, "request": text, "kind": kind, "recipient": recipient,
                "place": place, "item": item, "minutes": minutes, "status": "accepted", "steps": steps,
                "step": 0, "created": self.time, "evidence": [], "blocker": "", "retry_at": 0,
                "deadline": self.time + 3600, "search": 0, "next_repath": 0}
        self.tasks[task_id] = task
        a["task"] = task_id
        a["status"] = "Starting your task"
        seq = self.event(agent_id, "task_accepted", f"{a['name']} accepted: {text}", {"task": task_id})
        self.storage.memory(agent_id, "task", f"Alex asked me to {text}", self.time, 9, [seq])
        self.speak(agent_id, "I'll get started. You can follow my progress in the task list.", ["visitor"])
        return task

    def block_task(self, a, task, reason):
        if task["status"] != "blocked" or task["blocker"] != reason:
            self.event(a["id"], "task_blocked", f"{a['name']}: {reason}", {"task": task["id"]})
        task.update(status="blocked", blocker=reason, retry_at=self.time + 60)
        a["status"] = reason
        a["path"] = []

    def complete_task(self, a, task, description):
        task.update(status="completed", step=len(task["steps"]), completed=self.time, blocker="")
        a["task"] = None
        a["path"] = []
        a["next_decision"] = self.time + 45
        a["status"] = "Task completed"
        seq = self.event(a["id"], "task_completed", description, {"task": task["id"], "evidence": task["evidence"]})
        self.storage.memory(a["id"], "task", description, self.time, 9, [seq])
        self.speak(a["id"], description, ["visitor"])

    def go(self, a, goal, label):
        if distance(a, goal) <= .8:
            a["path"] = []
            return True
        if not a["path"]:
            path = self.pathfind(a, goal)
            if path is None:
                return None
            a["path"] = path
        a["status"] = label
        return False

    def find_resident(self, a, task):
        target = self.agents[task["recipient"]]
        if self.visible(a, target, 1.5):
            a["path"] = []
            return target
        if self.visible(a, target):
            a["known_positions"][target["id"]] = {"x": target["x"], "y": target["y"], "time": self.time, "room":target.get("room", "")}
        known = a["known_positions"].get(target["id"])
        if self.time >= task["next_repath"]:
            a["path"] = []
            task["next_repath"] = self.time + 12
        if known and distance(a, known) <= 1 and not self.visible(a,target):
            a["known_positions"].pop(target["id"],None)
            known = None
        if known and distance(a, known) > 1:
            self.go(a, known, f"Looking for {target['name']}")
        else:
            places = list(self.layout["places"].values())
            x, y = places[task["search"] % len(places)]
            if self.go(a, {"x": x, "y": y}, f"Searching for {target['name']}"):
                task["search"] += 1
        return None

    def _task(self, a):
        task = self.tasks[a["task"]]
        if self.time > task["deadline"]:
            task.update(status="failed", blocker="The task could not be completed within one simulated hour.")
            self.event(a["id"], "task_failed", task["blocker"], {"task": task["id"]})
            a["task"], a["path"] = None, []
            return
        if task["status"] == "blocked" and self.time < task["retry_at"]:
            return
        task.update(status="running", blocker="")
        if task["kind"] == "deliver":
            if task["step"] == 0:
                existing = next((i for i in a["inventory"] if i["kind"] == task["item"]), None)
                if existing:
                    task.update(item_id=existing["id"], step=1)
                    return
                place = "cafe" if task["item"] == "coffee" else "shop"
                if place == "cafe" and not self.cafe_open:
                    self.block_task(a, task, "The cafe is closed. I'll check again shortly.")
                    return
                if self.stock[task["item"]] <= 0:
                    self.block_task(a, task, "The requested item is out of stock.")
                    return
                x, y = self.layout["places"][place]
                arrived = self.go(a, {"x": x, "y": y}, f"Collecting {task['item']} at the {place}")
                if arrived is None:
                    self.block_task(a, task, "I cannot reach the collection point.")
                elif arrived:
                    if "collect_until" not in task:
                        task["collect_until"] = self.time + 18
                    if self.time >= task["collect_until"]:
                        obj = {"id": uuid.uuid4().hex[:12], "kind": task["item"]}
                        a["inventory"].append(obj)
                        self.stock[task["item"]] -= 1
                        task.update(item_id=obj["id"], step=1)
                        task["evidence"].append(self.event(a["id"], "pickup", f"{a['name']} collected {task['item']}.", {"task": task["id"], "item": obj["id"]}))
            else:
                target = self.find_resident(a, task)
                if target:
                    obj = next((i for i in a["inventory"] if i["id"] == task.get("item_id")), None)
                    if not obj:
                        self.block_task(a, task, "I no longer have the requested item.")
                        return
                    a["inventory"].remove(obj)
                    target["inventory"].append(obj)
                    self.face_each_other(a, target)
                    seq = self.event(a["id"], "transfer", f"{a['name']} gave {task['item']} to {target['name']}.", {"task": task["id"], "item": obj["id"], "recipient": target["id"]})
                    task["evidence"].append(seq)
                    self.storage.memory(target["id"], "observation", f"{a['name']} brought me {task['item']}.", self.time, 7, [seq])
                    self.complete_task(a, task, f"I delivered the {task['item']} to {target['name']}.")
        elif task["kind"] == "visit":
            x, y = self.layout["places"][task["place"]]
            arrived = self.go(a, {"x": x, "y": y}, f"Walking to the {task['place']}")
            if arrived is None:
                self.block_task(a, task, "I cannot reach that destination.")
            elif arrived:
                task["evidence"].append(self.event(a["id"], "arrival", f"{a['name']} reached the {task['place']}.", {"task": task["id"]}))
                self.complete_task(a, task, f"I've arrived at the {task['place']}.")
        elif task["kind"] == "wait":
            task.setdefault("until", self.time + task["minutes"] * 60)
            a["status"] = "Waiting as requested"
            if self.time >= task["until"]:
                task["evidence"].append(self.event(a["id"], "wait_elapsed", "Requested wait elapsed.", {"task": task["id"]}))
                self.complete_task(a, task, f"I've waited for {task['minutes']} minutes.")
        elif task["kind"] == "meet":
            target = self.find_resident(a, task)
            if target and not target["thinking"] and not target["conversation"]:
                task["step"] = 1
                task["conversation"] = self.start_conversation(a, target, task["id"])

    @staticmethod
    def facing(dx, dy):
        angle = math.atan2((dx + dy) * 16, (dx - dy) * 32)
        octant = int(math.floor(angle / (math.pi / 4) + .5)) % 8
        return [6, 7, 0, 1, 2, 3, 4, 5][octant]

    def face_each_other(self, a, b):
        a["face"] = self.facing(b["x"] - a["x"], b["y"] - a["y"])
        b["face"] = self.facing(a["x"] - b["x"], a["y"] - b["y"])

    def move(self, a, dt):
        a["moving"] = False
        if not a["path"]:
            return
        p = a["path"][0]
        dx, dy = p["x"] - a["x"], p["y"] - a["y"]
        d = math.hypot(dx, dy)
        if d < .01:
            a["path"].pop(0)
            return
        step = min(d, dt * .17)
        proposed = {"x": a["x"] + dx / d * step, "y": a["y"] + dy / d * step, "room": a.get("room", "")}
        occupied = [b for b in self.agents.values() if b is not a and distance(b, proposed) < .42]
        if occupied:
            a["stalled"] += dt
            if a["stalled"] > 18:
                detour = self.pathfind(a, a["path"][-1], {(round(b["x"]), round(b["y"])) for b in occupied})
                if detour:
                    a["path"] = detour
                a["stalled"] = 0
            return
        a.update(proposed)
        a["face"] = self.facing(dx, dy)
        a["moving"], a["stalled"] = True, 0
        if step == d:
            a["path"].pop(0)

    def start_conversation(self, a, b, task=None):
        if a["conversation"] or b["conversation"]:
            return None
        self._interrupt(a)
        self._interrupt(b)
        cid = "chat_" + uuid.uuid4().hex[:10]
        for participant, other in ((a, b), (b, a)):
            participant["conversation"] = cid
            participant["status"] = f"Talking with {other['name']}"
        self.face_each_other(a, b)
        self.conversations[cid] = {"id": cid, "participants": [a["id"], b["id"]], "turn": 0,
                                   "history": [], "next_turn": self.time, "waiting": False, "task": task}
        self.event(a["id"], "conversation_started", f"{a['name']} and {b['name']} stopped to talk.")
        return cid

    def end_conversation(self, cid):
        conv = self.conversations.pop(cid, None)
        if not conv:
            return
        for aid in conv["participants"]:
            a = self.agents[aid]
            other = next(x for x in conv["participants"] if x != aid)
            a.update(conversation=None, thinking=False, cooldown=self.time + 180, next_decision=self.time + 40)
            a["revision"] += 1
            a["relationships"][other] = min(100, a["relationships"].get(other, 0) + len(conv["history"]))
            a["needs"]["social"] = min(100, a["needs"]["social"] + 10)
        task = self.tasks.get(conv.get("task"))
        if task and task["status"] not in TERMINAL:
            task.pop("conversation", None)
            if len(conv["history"]) >= 2:
                seq = self.event(task["agent"], "meeting", "The requested residents spoke to each other.", {"task": task["id"]})
                task["evidence"].append(seq)
                self.complete_task(self.agents[task["agent"]], task, f"I met with {self.agents[task['recipient']]['name']}.")

    def _conversations(self):
        for cid, conv in list(self.conversations.items()):
            if conv["waiting"] or self.time < conv["next_turn"]:
                continue
            if conv["turn"] >= 4:
                self.end_conversation(cid)
                continue
            aid = conv["participants"][conv["turn"] % 2]
            other = conv["participants"][(conv["turn"] + 1) % 2]
            a = self.agents[aid]
            if aid == "visitor":
                text = "Thanks for taking a moment to talk."
                self.speak(aid, text, [other])
                conv["history"].append({"name": "Alex", "text": text})
                conv["turn"] += 1
                conv["next_turn"] = self.time + 24
                continue
            context = self._context(a, "conversation with " + self.agents[other]["name"], conversation=copy.deepcopy(conv["history"]), other_name=self.agents[other]["name"], message=conv["history"][-1]["text"] if conv["history"] else "Hello")
            conv["waiting"] = bool(self.submit("chat", a, context, conversation=cid, other=other))

    def _interaction(self):
        p = self.pending_interaction
        if not p:
            return
        visitor, a = self.agents["visitor"], self.agents[p["agent"]]
        if self.visible(visitor, a, 1.8):
            visitor["path"] = []
            visitor["status"] = "Ready to explore"
            self.pending_interaction = None
            self._interrupt(a)
            self.face_each_other(visitor, a)
            self.speak("visitor", p["text"], [a["id"]])
            a["status"] = "Listening to Alex"
            if p["kind"] == "task":
                self.submit("task", a, self._context(a, p["text"], request=p["text"]))
            else:
                self.submit("chat", a, self._context(a, p["text"], message=p["text"]), other="visitor")
        elif self.time > p["expires"]:
            self.event("visitor", "interaction_failed", "Could not reach the selected resident. Try again from a nearby path.")
            self.pending_interaction = None
            visitor["path"] = []
        elif self.time >= p["repath"]:
            visitor["path"] = []
            self.go(visitor, a, f"Walking over to {a['name']}")
            p["repath"] = self.time + 12

    def tick(self, dt):
        with self.lock:
            if self.paused:
                return
            dt = max(0, min(dt, 1)) * 6 * self.speed
            self.time += dt
            self._jobs()
            self.observe()
            self._interaction()
            self._conversations()
            for a in self.agents.values():
                a["moving"] = False
                if a["conversation"] or a["thinking"]:
                    continue
                if a["id"] == "visitor":
                    self.move(a, dt)
                    continue
                a["needs"]["energy"] = max(0, a["needs"]["energy"] - dt * .002)
                a["needs"]["hunger"] = min(100, a["needs"]["hunger"] + dt * .004)
                a["needs"]["social"] = max(0, a["needs"]["social"] - dt * .002)
                if a["task"]:
                    self._task(a)
                elif a["routine"]:
                    routine = a["routine"]
                    x, y = self.layout["places"][routine["place"]]
                    arrived = self.go(a, {"x": x, "y": y}, "Walking to the " + routine["place"])
                    if arrived:
                        a["status"] = routine["activity"]
                        if routine["arrived"] is None:
                            routine["arrived"] = self.time
                            seq = self.event(a["id"], "activity", f"{a['name']} is {routine['activity'].lower()}.")
                            self.storage.memory(a["id"], "observation", f"I spent time at the {routine['place']}: {routine['activity']}.", self.time, 3, [seq])
                        if routine["place"] == "cafe":
                            a["needs"]["hunger"] = max(0, a["needs"]["hunger"] - dt * .05)
                        if routine["place"] == "home":
                            a["needs"]["energy"] = min(100, a["needs"]["energy"] + dt * .05)
                        if self.time >= routine["arrived"] + routine["duration"]:
                            a["routine"] = None
                            a["next_decision"] = self.time
                    elif arrived is None:
                        a["routine"] = None
                        a["next_decision"] = self.time + 60
                elif self.time >= a["next_reflect"] and self.reflection_due(a):
                    a["next_reflect"] = self.time + 600
                    self.submit("reflect", a, self._context(a, "recent conversations and experiences"))
                elif self.time >= a["next_decision"]:
                    self.submit("decide", a, self._context(a, "next activity daily plan"))
                self.move(a, dt)
            if self.time >= self.next_social:
                self.next_social = self.time + 20
                available = [a for a in self.agents.values() if a["id"] != "visitor" and not a["task"] and not a["thinking"] and not a["conversation"] and a["cooldown"] <= self.time]
                for i, a in enumerate(available):
                    match = next((b for b in available[i + 1:] if self.visible(a, b, 1.8)), None)
                    if match:
                        self.start_conversation(a, match)
                        break

    def command(self, data):
        with self.lock:
            cid = data.get("id")
            if not isinstance(cid, str) or not 1 <= len(cid) <= 100:
                raise CommandError("A command ID is required")
            previous = self.storage.command_result(cid)
            if previous is not None:
                return previous
            kind = data.get("kind")
            result = {"ok": True}
            if kind in ("chat", "task"):
                aid, text = data.get("agent"), data.get("text")
                if aid not in self.agents or aid == "visitor":
                    raise CommandError("Select a resident first")
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000:
                    raise CommandError("Enter a message of 1-1000 characters")
                a = self.agents[aid]
                if kind == "task" and a["task"]:
                    raise CommandError("This resident already has a task. Cancel it or wait for completion.")
                self.pending_interaction = {"kind": kind, "agent": aid, "text": text.strip(), "repath": 0, "expires": self.time + 600}
                self._interrupt(self.agents["visitor"])
                self._interaction()
                result["message"] = "Walking over to " + a["name"] if self.pending_interaction else "Message received"
            elif kind == "move":
                x, y = data.get("x"), data.get("y")
                if type(x) is not int or type(y) is not int or not self.valid(x, y):
                    raise CommandError("Choose a walkable ground tile")
                a = self.agents["visitor"]
                path = self.pathfind(a, {"x": x, "y": y})
                if path is None:
                    raise CommandError("No path to that tile")
                self._interrupt(a)
                self.pending_interaction = None
                a["path"], a["status"] = path, "Exploring the neighborhood"
            elif kind == "cancel":
                task = self.tasks.get(data.get("task"))
                if not task or task["status"] in TERMINAL:
                    raise CommandError("That task is no longer active")
                a = self.agents[task["agent"]]
                task["status"] = "cancelled"
                self._interrupt(a)
                a["task"], a["status"], a["next_decision"] = None, "Task cancelled", self.time + 20
                self.event(a["id"], "task_cancelled", f"{a['name']}'s task was cancelled.", {"task": task["id"]})
            elif kind == "pause":
                if type(data.get("paused")) is not bool:
                    raise CommandError("paused must be a boolean")
                self.paused = data["paused"]
            elif kind == "speed":
                if type(data.get("speed")) is not int or data["speed"] not in (1, 2, 4):
                    raise CommandError("Choose 1x, 2x or 4x speed")
                self.speed = data["speed"]
            elif kind == "cafe":
                if type(data.get("open")) is not bool:
                    raise CommandError("open must be a boolean")
                self.cafe_open = data["open"]
                self.event("system", "world_change", "The cafe is " + ("open." if self.cafe_open else "closed."))
                for task in self.tasks.values():
                    if task["status"] == "blocked":
                        task["retry_at"] = self.time
            elif kind == "save":
                self.save()
                result["message"] = "Smallworld Agents: town saved"
            else:
                raise CommandError("Unknown command")
            self.storage.remember_command(cid, result)
            return result

    def snapshot(self):
        with self.lock:
            keys = ("id", "name", "role", "bio", "x", "y", "face", "moving", "status", "thinking", "task", "conversation", "inventory", "needs", "bubble", "bubble_until")
            return {"time": self.time, "paused": self.paused, "speed": self.speed,
                    "agents": [{k: copy.deepcopy(a[k]) for k in keys} for a in self.agents.values()],
                    "tasks": copy.deepcopy(list(self.tasks.values())[-30:]), "events": self.storage.events(35),
                    "model": self.cognition.status(), "cafe_open": self.cafe_open, "stock": dict(self.stock),
                    "pending_interaction": copy.deepcopy(self.pending_interaction), "last_saved": self.last_saved}

    def inspect(self, aid):
        with self.lock:
            if aid not in self.agents:
                raise CommandError("Unknown resident")
            a = self.agents[aid]
            return {"id": aid, "memories": self.storage.memories(aid), "plan": copy.deepcopy(a["plan"]),
                    "relationships": dict(a["relationships"]), "retrieved": a["retrieved"], "known_positions": copy.deepcopy(a["known_positions"]),
                    "dialogue": self.storage.dialogue(aid)}

    def save_state(self):
        return {"time": self.time, "agents": self.agents, "tasks": self.tasks, "stock": self.stock,
                "cafe_open": self.cafe_open, "paused": self.paused, "speed": self.speed}

    def save(self):
        with self.lock:
            self.last_saved = self.time
            self.storage.save(self.save_state())

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
        with self.lock:
            self.save()
            self.storage.close()


from .roadmap import RoadmapMixin
from .community import CommunityMixin


class World(CommunityMixin, RoadmapMixin, BaseWorld):
    """Public simulation with the roadmap capabilities enabled."""
