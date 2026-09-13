"""Extended world behavior: plans, rooms, appointments, retrieval and recorded playback."""
import copy
import json
import hashlib
import math
import os
import pickle
import time
import uuid
from contextlib import contextmanager
from concurrent.futures import Future
from .performance import fast_task
from .community import initial_community
from pathlib import Path
from .memory import SemanticMemory
from .maps import obstacle_cells, upgrade_classic
from .scenario import validate, populate, interiors

FINISHED = {"completed", "failed", "cancelled", "declined"}
# Finished tasks leave live state after two simulated hours; the newest 30 stay for the task list.
ARCHIVE_AFTER = 7200
KEEP_RECENT_TASKS = 30


class RoadmapMixin:
    def __init__(self, database=":memory:", cognition=None, restore=True, scenario=None, residents=None):
        self.community = initial_community()
        self.semantic = SemanticMemory()
        self.metrics = {}
        self.appointments = {}
        self.proposals = {}
        self.leases = {}
        self.last_frame = -1
        self.next_archive = 0
        self.reflections_enabled = os.getenv("AGENT_REFLECTIONS", "on") != "off"
        self.scenario_input = scenario
        self.population = residents
        super().__init__(database, cognition, restore)
        if self.cognition.mode == "demo":
            self.semantic.model = ""
        self.layout["interiors"] = interiors()
        saved = self.storage.load() if restore else None
        if saved:
            self.community = saved.get("community", self.community)
            self.appointments = saved.get("appointments", {})
            self.leases = saved.get("leases", {})
            self.proposals = saved.get("proposals", {})
        for a in self.agents.values():
            a.setdefault("credits", 25)
            a.setdefault("room", "")
            a.setdefault("skin", a["id"])
            a.setdefault("last_reflection", self.time)
        upgraded = False
        if saved and self.scenario_input is None:
            self.layout, upgraded = upgrade_classic(self.layout)
            if upgraded:
                self.blocked = obstacle_cells(self.layout)
                profiles = {p["id"]:p for p in self.layout["residents"]}
                previous = {p["id"]:p for p in saved.get("layout",{}).get("residents",[])}
                for aid,a in self.agents.items():
                    if aid in profiles and aid in previous and a["plan"] == previous[aid]["plan"]:
                        a["plan"] = copy.deepcopy(profiles[aid]["plan"])
                self.event("system","map_expanded","New paths lead to the market, gardens, waterfront and fountain square.")
        self.semantic.cache = {r["key"]:json.loads(r["vector"]) for r in self.storage.db.execute("SELECT * FROM embeddings")}
        if upgraded:
            self.save()
        self.record()

    def initial_layout(self):
        source = self.scenario_input
        if source is None:
            source = Path(__file__).resolve().parents[1] / "scenarios/neighborhood.json"
        layout = validate(json.loads(Path(source).read_text(encoding="utf-8")) if not isinstance(source, dict) else source)
        return populate(layout, self.population) if self.population else layout

    def _context(self, a, query="", **extra):
        context = super()._context(a, query, **extra)
        candidates = self.storage.memories(a["id"], 120)
        # Reflections cite direct experiences, preventing self-reinforcing chains.
        if query == "recent conversations and experiences":
            candidates = [m for m in candidates if m["kind"] != "reflection"]
            context["memories"] = [m for m in context["memories"] if m["kind"] != "reflection"]
        context.update(place_names={d["place"]:d["name"] for d in self.layout.get("districts",[])}, memory_candidates=candidates, memory_query=query or a["status"], capabilities="plans-v2",
            objects=[{**o,"room":room} for room,r in self.layout.get("interiors",{}).items() for o in r["objects"]],
            commitments=[copy.deepcopy(ap) for ap in self.appointments.values() if a["id"] in ap["accepted"] and ap["status"] == "scheduled"])
        return context

    def _cognition_job(self, method, context):
        began = time.monotonic()
        context = copy.deepcopy(context)
        if method in ("chat", "reflect"):
            context = self.semantic.rank(context, allow_network=os.getenv("AGENT_LIVE_EMBEDDINGS", "off") == "on")
        else:
            context["memories"] = []
        self.cognition.usage_local.tokens = 0
        result = getattr(self.cognition, method)(context)
        return {"_cognition_result": result,"memories":context["memories"],"latency":time.monotonic()-began,
                "tokens":self.cognition.usage_local.tokens,"source":self.cognition.mode,
                "timing":getattr(self.cognition.usage_local,"timing",{})}

    def submit(self, method, a, context, **extra):
        local = fast_task(context) if method == "task" else None
        if method == "decide" and os.getenv("AGENT_ROUTINE_MODEL", "off") != "on":
            local = self.fallback.decide(context)
        if local is not None:
            future = Future()
            future.set_result({"_cognition_result":local,"memories":[],"latency":0,"tokens":0,"source":"local_rules","timing":{}})
            a["thinking"] = True
            self.jobs.append({"future":future,"method":method,"agent":a["id"],"revision":a["revision"],"context":context,**extra})
            return True
        # Free queue slots before the capacity check; the base submit repeats this harmlessly.
        self.yield_to_player(method, extra)
        active = sum(not j["future"].done() for j in self.jobs)
        if active >= 8 and method in ("decide", "reflect"):
            a["next_decision"] = self.time+30
            return False
        if active >= 8 and method in ("task","chat"):
            a["status"] = "Model queue is full; please try again shortly"
            self.event(a["id"],"queue_full",a["status"])
            return False
        super().submit(method, a, context, **extra)
        return True

    def consume_result(self, job, result):
        if isinstance(result, dict) and "_cognition_result" in result:
            context = job["context"]
            context["memories"] = result["memories"]
            a = self.agents[job["agent"]]
            a["retrieved"] = [m["id"] for m in result["memories"]]
            self.storage.db.executemany("UPDATE memories SET accessed=? WHERE id=? AND owner=?",[(self.time,mid,a["id"]) for mid in a["retrieved"]])
            key = job["agent"]+":"+job["method"]
            metric = self.metrics.setdefault(key,{"calls":0,"seconds":0,"tokens":0})
            metric["calls"] += 1
            metric["seconds"] += result["latency"]
            metric["tokens"] += result["tokens"]
            metric["last_source"] = result.get("source", self.cognition.mode)
            metric["last_seconds"] = result["latency"]
            metric["timing"] = result.get("timing", {})
            job["source"] = metric["last_source"]
            result = result["_cognition_result"]
        self.storage.db.executemany("INSERT OR REPLACE INTO embeddings VALUES(?,?)",[(k,json.dumps(v)) for k,v in self.semantic.drain_dirty()])
        self.storage.decision(self.time,job["agent"],job["method"],{"model":self.cognition.model,"mode":self.cognition.mode,
            "source":job.get("source",self.cognition.mode),"result":result,"memory_ids":[m["id"] for m in job["context"].get("memories",[])],"revision":job["revision"]})
        return result

    def reflection_due(self, a):
        if not self.reflections_enabled:
            return False
        return self.storage.importance_since(a["id"],a.get("last_reflection",0)) >= 30

    def validate_step(self, aid, step):
        from .world import CommandError
        if not isinstance(step,dict):
            raise CommandError("Each task step must be an object")
        kind = step.get("kind")
        if kind not in ("deliver","visit","meet","wait","report","use","inspect","invite"):
            raise CommandError("That request needs clarification: choose a supported errand or meeting.")
        if kind in ("deliver","meet") and (step.get("recipient") not in self.agents or step["recipient"]==aid):
            raise CommandError("Name another resident")
        if kind == "deliver" and step.get("item") not in ("coffee","parcel"):
            raise CommandError("Only coffee and parcels can be delivered")
        if kind in ("visit","invite") and step.get("place") not in self.layout["places"]:
            raise CommandError("Choose a known meeting place or destination")
        if kind == "wait" and (type(step.get("minutes")) is not int or not 1 <= step["minutes"] <= 30):
            raise CommandError("Wait duration must be 1-30 minutes")
        if kind in ("use","inspect"):
            if not self.object_for(step.get("item"),step.get("place")):
                raise CommandError("Choose a known interior object")
        if kind == "invite":
            guests = step.get("guests",[])
            if not isinstance(guests,list) or not 1 <= len(guests) <= 10 or len(set(guests)) != len(guests) or any(g not in self.agents or g in (aid,"visitor") for g in guests):
                raise CommandError("Invite 1-10 distinct named residents")
            if type(step.get("at")) is not int or not self.time+60 <= step["at"] <= self.time+86400:
                raise CommandError("Choose a meeting time between one minute and 24 hours from now")

    def create_task(self, agent_id, text, spec):
        from .world import CommandError
        if agent_id not in self.agents:
            raise CommandError("Unknown resident")
        steps = spec.get("steps") if spec.get("kind") == "sequence" else [spec]
        if not isinstance(steps,list) or not 1 <= len(steps) <= 6:
            raise CommandError("A plan needs 1-6 ordered steps")
        for step in steps:
            self.validate_step(agent_id, step)
        first = steps[0]
        proxy = first if first["kind"] in ("deliver","visit","meet","wait") else {"kind":"visit","place":"park"}
        task = super().create_task(agent_id,text,proxy)
        task["plan"] = copy.deepcopy(steps)
        task["plan_index"] = 0
        task["step_results"] = []
        task["dependencies"] = [{"step":i,"after":i-1 if i else None} for i in range(len(steps))]
        self.activate_step(task,first)
        return task

    def activate_step(self, task, spec):
        for key in ("until","collect_until","item_id","appointment","object_until","conversation"):
            task.pop(key,None)
        task.update({k:copy.deepcopy(spec.get(k,"" if k not in ("minutes","at","guests") else [] if k=="guests" else 0)) for k in ("kind","recipient","place","item","minutes","guests","at")})
        if task["kind"] == "report":
            task["recipient"] = "visitor"
        labels = {"deliver":["Collect the item","Find the recipient","Hand over the item"],"visit":["Walk to the destination"],
            "meet":["Find the resident","Have a conversation"],"wait":["Wait for the requested duration"],
            "report":["Find Alex","Report verified results"],"use":["Enter the room","Reserve and use the object"],
            "inspect":["Enter the room","Inspect the object"],"invite":["Deliver invitations","Wait for the appointment","Verify attendance"]}
        task.update(steps=labels[task["kind"]],step=0,status="accepted",blocker="",retry_at=0,search=0,next_repath=0,
                    deadline=max(self.time+3600,task.get("at",0)+900))

    def complete_task(self, a, task, description):
        plan = task.get("plan",[])
        index = task.get("plan_index",0)
        if plan:
            task["step_results"].append({"step":index,"kind":task["kind"],"description":description,"time":self.time,"evidence":list(task["evidence"])})
        if index+1 < len(plan):
            self.event(a["id"],"plan_step_completed",description,{"task":task["id"],"step":index,"evidence":list(task["evidence"])})
            task["plan_index"] += 1
            self.activate_step(task,plan[index+1])
            a["path"] = []
            return
        super().complete_task(a,task,description)

    def object_for(self, oid, room):
        return next((o for o in self.layout.get("interiors",{}).get(room,{}).get("objects",[]) if o["id"] == oid),None)

    def _task(self, a):
        task = self.tasks[a["task"]]
        if task["kind"] in ("deliver","visit","meet","wait"):
            return super()._task(a)
        if self.time > task["deadline"]:
            task.update(status="failed",blocker="The action deadline elapsed")
            self.event(a["id"],"task_failed",task["blocker"],{"task":task["id"]})
            a["task"],a["path"] = None,[]
            return
        if task["status"] == "blocked" and self.time < task["retry_at"]:
            return
        task.update(status="running",blocker="")
        if task["kind"] == "report":
            target = self.find_resident(a,task)
            if target:
                description = "; ".join(r["description"] for r in task.get("step_results",[])) or "I have no earlier completed steps to report."
                seq = self.speak(a["id"],description[:360],["visitor"])
                task["evidence"].append(seq)
                self.complete_task(a,task,"I returned to Alex and reported the recorded results.")
        elif task["kind"] in ("use","inspect"):
            obj = self.object_for(task["item"],task["place"])
            goal = {"x":obj["x"],"y":obj["y"]+1,"room":task["place"]}
            arrived = self.go(a,goal,"Walking to "+obj["name"])
            if arrived is None:
                return self.block_task(a,task,"The object cannot be reached")
            if not arrived:
                return
            task["step"] = 1
            lease = self.leases.get(obj["id"])
            if lease and lease["until"] > self.time and lease["agent"] != a["id"]:
                return self.block_task(a,task,"Someone else is using that object")
            duration = 6 if task["kind"] == "inspect" else 60
            task.setdefault("object_until",self.time+duration)
            self.leases[obj["id"]] = {"agent":a["id"],"until":task["object_until"]+6}
            a["status"] = ("Inspecting " if task["kind"]=="inspect" else "Using ")+obj["name"]
            if self.time >= task["object_until"]:
                if task["kind"] == "use":
                    a["needs"][obj["need"]] = min(100,a["needs"][obj["need"]]+15)
                seq = self.event(a["id"],"object_"+task["kind"],a["status"],{"task":task["id"],"object":obj["id"],"room":task["place"],"duration":duration})
                task["evidence"].append(seq)
                self.leases.pop(obj["id"],None)
                self.complete_task(a,task,"I finished with the "+obj["name"].lower()+".")
        elif task["kind"] == "invite":
            self.invite_step(a,task)

    def invite_step(self, a, task):
        ap = self.appointments.get(task.get("appointment"))
        if not ap:
            ap = {"id":uuid.uuid4().hex[:12],"host":a["id"],"place":task["place"],"at":task["at"],"guests":task["guests"],
                  "invited":[],"accepted":[a["id"]],"declined":[],"attended":[],"status":"scheduled","task":task["id"]}
            self.appointments[ap["id"]] = ap
            task["appointment"] = ap["id"]
        remaining = [g for g in ap["guests"] if g not in ap["invited"]]
        if remaining and self.time < ap["at"]:
            task["recipient"] = remaining[0]
            target = self.find_resident(a,task)
            if not target or target["conversation"] or target["thinking"]:
                return
            seq = self.speak(a["id"],f"Would you join me at the {ap['place']} at {int(ap['at']//3600)%24:02}:{int(ap['at']//60)%60:02}?",[target["id"]])
            task["evidence"].append(seq)
            ap["invited"].append(target["id"])
            conflict = bool(target["task"]) or any(other["id"] != ap["id"] and other["status"]=="scheduled" and target["id"] in other["accepted"] and abs(other["at"]-ap["at"]) < 900 for other in self.appointments.values())
            bucket = "declined" if conflict else "accepted"
            ap[bucket].append(target["id"])
            self.speak(target["id"],"I have another commitment, so I cannot promise to attend." if conflict else "Yes, I accept. I'll plan to be there.",[a["id"]])
            task["evidence"].append(self.event(target["id"],"invitation_"+bucket,"Invitation "+bucket,{"appointment":ap["id"],"task":task["id"]}))
            self.storage.memory(target["id"],"commitment",f"Meeting at {ap['place']} at {ap['at']}: {bucket}.",self.time,8,[seq])
            task["search"],task["next_repath"] = 0,0
            return
        task["step"] = 1
        x,y = self.layout["places"][ap["place"]]
        self.go(a,{"x":x,"y":y},"Heading to the meeting")
        if ap["status"] == "finished":
            missed = [g for g in ap["guests"] if g not in ap["attended"]]
            if missed:
                task.update(status="failed",blocker=f"Meeting ended: {len(ap['invited'])} invited, {len(ap['accepted'])-1} accepted, {len(ap['attended'])-(a['id'] in ap['attended'])} guests attended.")
                self.event(a["id"],"task_failed",task["blocker"],{"task":task["id"],"appointment":ap["id"]})
                a["task"],a["path"] = None,[]
            else:
                task["evidence"].append(self.event(a["id"],"attendance_verified","All requested guests attended.",{"appointment":ap["id"],"task":task["id"]}))
                self.complete_task(a,task,"All invited residents attended the meeting.")

    def appointment_tick(self):
        from .world import distance
        for ap in self.appointments.values():
            task = self.tasks.get(ap["task"])
            if task and task["status"] in ("cancelled","failed") and ap["status"]=="scheduled":
                ap["status"] = "cancelled"
            if ap["status"] != "scheduled":
                continue
            x,y = self.layout["places"][ap["place"]]
            goal = {"x":x,"y":y}
            for aid in ap["accepted"]:
                a = self.agents[aid]
                if ap["at"] <= self.time <= ap["at"]+600 and distance(a,goal) <= 2:
                    if aid not in ap["attended"]:
                        ap["attended"].append(aid)
                        self.event(aid,"attendance",a["name"]+" attended the meeting.",{"appointment":ap["id"]})
                if aid != ap["host"] and not a["task"] and self.time >= ap["at"]-600:
                    if a["conversation"] or a["thinking"]:
                        self._interrupt(a)
                    a["routine"] = None
                    a["next_decision"] = ap["at"]+660
                    a["cooldown"] = ap["at"]+660
                    self.go(a,goal,"Attending a scheduled meeting")
            if self.time >= ap["at"]+600:
                ap["status"] = "finished"

    def pathfind(self, actor, goal, extra=()):
        room = actor.get("room", "")
        if not room:
            return super().pathfind(actor,goal,extra)
        interior = self.layout["interiors"][room]
        old_blocked, old_size = self.blocked, self.layout["size"]
        self.blocked = {(o["x"],o["y"]) for o in interior["objects"]}
        self.layout["size"] = interior["size"]
        try:
            return super().pathfind(actor,{**goal,"room":room},extra)
        finally:
            self.blocked,self.layout["size"] = old_blocked,old_size

    def go(self, a, goal, label):
        from .world import distance
        room, target_room = a.get("room", ""), goal.get("room", "")
        if room != target_room:
            portal_room = room or target_room
            inside = self.layout["interiors"][portal_room]
            p = inside["door"] if room else self.layout["places"][portal_room]
            portal = {"x":p[0],"y":p[1],"room":room}
            arrived = super().go(a,portal,label)
            if not arrived:
                return arrived
            destination = self.layout["places"][room] if room else inside["door"]
            destination_room = "" if room else target_room
            dest = {"x":destination[0],"y":destination[1],"room":destination_room}
            if any(b is not a and distance(b,dest)<.55 for b in self.agents.values()):
                a["status"] = "Waiting for the doorway"
                return False
            a.update(dest,path=[])
            self.event(a["id"],"room_entered",a["name"]+(" entered "+destination_room if destination_room else " stepped outside"),{"room":destination_room})
            return False
        return super().go(a,goal,label)

    def visible(self, a, b, radius=4):
        from .world import distance
        if a.get("room", "") != b.get("room", ""):
            return False
        if a.get("room"):
            return distance(a,b) <= radius
        return super().visible(a,b,radius)

    def move(self, a, dt):
        if a["id"]=="visitor" and a.get("destination"):
            if self.go(a,a["destination"],"Exploring"):
                a.pop("destination",None)
        super().move(a,dt)

    def find_resident(self, a, task):
        # Last observations include room identity. Search includes every accessible interior.
        target = self.agents[task["recipient"]]
        known = a["known_positions"].get(target["id"])
        if known and known.get("room") and not self.visible(a,target,1.5):
            if self.time >= task["next_repath"]:
                a["path"] = []
                task["next_repath"] = self.time+12
            arrived = self.go(a,known,"Looking for "+target["name"])
            if arrived:
                a["known_positions"].pop(target["id"],None)
            return None
        if not known and task["search"] >= len(self.layout["places"]):
            rooms = list(self.layout["interiors"])
            room = rooms[(task["search"]-len(self.layout["places"]))%len(rooms)]
            if self.go(a,{"x":2,"y":4,"room":room},"Searching inside "+room):
                task["search"] += 1
            if self.visible(a,target,1.5):
                return target
            return None
        return super().find_resident(a,task)

    def speak(self, actor, text, recipients=()):
        a = self.agents[actor]
        intended = [r for r in recipients if r in self.agents and self.visible(a,self.agents[r],3)]
        heard = [b["id"] for b in self.agents.values() if b["id"] not in (actor,*intended) and self.visible(a,b,2)]
        seq = super().speak(actor,text,intended)
        for aid in heard:
            self.storage.memory(aid,"reported",a["name"]+" said: "+text,self.time,3,[seq])
        return seq

    @contextmanager
    def atomic(self):
        fields = ("agents","tasks","stock","time","conversations","pending_interaction","appointments","leases","proposals","paused","speed","cafe_open","last_saved","last_frame","next_social","next_archive","community")
        with self.lock, self.storage.transaction():
            # Pickling the plain-data state is an exact deep copy and much faster than copy.deepcopy.
            saved = pickle.dumps({key:getattr(self,key) for key in fields}, pickle.HIGHEST_PROTOCOL)
            previous_jobs = list(self.jobs)
            try:
                yield
            except BaseException:
                before = pickle.loads(saved)
                changed = any(getattr(self,key) != value for key,value in before.items()) or self.jobs != previous_jobs
                if changed:
                    for key,value in before.items():
                        setattr(self,key,value)
                    for job in self.jobs:
                        job["future"].cancel()
                    for a in self.agents.values():
                        a["revision"] += 1
                        a["thinking"] = False
                    for conv in self.conversations.values():
                        conv["waiting"] = False
                    self.jobs = []
                raise

    def archive_tasks(self):
        """Move long-finished tasks to SQLite so per-tick copies and saves stay bounded."""
        if self.time < self.next_archive:
            return
        self.next_archive = self.time + 60
        recent = set(list(self.tasks)[-KEEP_RECENT_TASKS:])
        held = {a["task"] for a in self.agents.values()}
        old = []
        for tid, task in self.tasks.items():
            if task["status"] not in FINISHED:
                continue
            task.setdefault("finished_at", self.time)
            parent = self.tasks.get(task.get("parent"))
            if (tid in recent or tid in held or self.time - task["finished_at"] < ARCHIVE_AFTER
                    or (parent and parent["status"] not in FINISHED)
                    or (task.get("picnic") and task["status"] in ("failed","cancelled") and not task["picnic"].get("cleaned"))):
                continue
            old.append(task)
        if old:
            self.storage.archive_tasks(old)
            for task in old:
                del self.tasks[task["id"]]

    def tick(self, dt):
        with self.atomic():
            if self.paused:
                return
            for task in self.tasks.values():
                if task["status"] in ("failed","cancelled") and task.get("picnic") and not task["picnic"].get("cleaned"):
                    self.cleanup_picnic(task)
            self.appointment_tick()
            super().tick(dt)
            self.archive_tasks()
            self.save()
            if self.time-self.last_frame >= 6:
                self.record()

    def command(self, data):
        from .world import CommandError
        with self.atomic():
            cid = data.get("id")
            if not isinstance(cid,str) or not 1 <= len(cid) <= 100:
                raise CommandError("A command ID is required")
            prior = self.storage.command_result(cid)
            if prior is not None:
                return prior
            kind = data.get("kind")
            result = {"ok":True}
            if kind == "weather":
                if data.get("weather") not in ("clear","rain"):
                    raise CommandError("Choose clear or rain")
                self.community["weather"] = data["weather"]
                self.event("visitor","weather_changed","Weather changed to "+data["weather"])
            elif kind in ("suspend_task","resume_task"):
                task = self.tasks.get(data.get("task"))
                if not task or task["status"] in FINISHED:
                    raise CommandError("That task is no longer active")
                a = self.agents[task["agent"]]
                if kind == "suspend_task":
                    if task["status"]=="paused" or a["task"] != task["id"]:
                        raise CommandError("That task is already paused")
                    if task["kind"] in ("invite","picnic"):
                        raise CommandError("Meetings have a fixed appointment time; cancel this request to release the commitment")
                    if task.get("parent"):
                        raise CommandError("This errand supports a picnic; cancel it or the picnic instead of pausing")
                    if a["conversation"]:
                        self.conversations[a["conversation"]]["task"] = None
                    self._interrupt(a)
                    a["task"] = None
                    task.update(status="paused",paused_at=self.time)
                    for oid,lease in list(self.leases.items()):
                        if lease["agent"] == a["id"]:
                            self.leases.pop(oid,None)
                else:
                    if task["status"] != "paused" or a["task"]:
                        raise CommandError("Finish or pause the current task before resuming this one")
                    self._interrupt(a)
                    elapsed = self.time-task.pop("paused_at",self.time)
                    for key in ("deadline","until","object_until","collect_until","work_until"):
                        if key in task:
                            task[key] += elapsed
                    task.update(status="accepted",next_repath=0)
                    a["task"] = task["id"]
                self.event(a["id"],kind,"Task "+("paused" if kind=="suspend_task" else "resumed"),{"task":task["id"]})
            elif kind == "accept_proposal":
                proposal = self.proposals.get(data.get("proposal"))
                if not proposal or proposal["status"] != "proposed":
                    raise CommandError("That proposal is no longer available")
                result = super().command({"id":hashlib.sha256((cid+":accepted").encode()).hexdigest(),"kind":"task","agent":proposal["agent"],"text":proposal["request"]})
                proposal["status"] = "accepted"
            elif kind == "decline_proposal":
                proposal = self.proposals.get(data.get("proposal"))
                if not proposal or proposal["status"] != "proposed":
                    raise CommandError("That proposal is no longer available")
                proposal["status"] = "declined"
                self.event(proposal["agent"],"proposal_declined","The proposed task was declined.",{"proposal":proposal["id"]})
            elif kind == "travel":
                place = data.get("place")
                if place not in self.layout["places"]:
                    raise CommandError("Choose a known destination")
                visitor = self.agents["visitor"]
                self._interrupt(visitor)
                x,y = self.layout["places"][place]
                visitor["destination"] = {"x":x,"y":y,"room":""}
                self.pending_interaction = None
                result["message"] = "Alex is walking to the "+place
            elif kind == "enter":
                room = data.get("room", "")
                if room and room not in self.layout["interiors"]:
                    raise CommandError("Unknown room")
                visitor = self.agents["visitor"]
                self._interrupt(visitor)
                p = self.layout["interiors"][room]["door"] if room else self.layout["places"].get(visitor.get("room"),[8,11])
                visitor["destination"] = {"x":p[0],"y":max(0,p[1]-1) if room else p[1],"room":room}
                self.pending_interaction = None
            elif kind == "move" and self.agents["visitor"].get("room"):
                a = self.agents["visitor"]
                x,y = data.get("x"),data.get("y")
                if type(x) is not int or type(y) is not int:
                    raise CommandError("Choose an interior tile")
                path = self.pathfind(a,{"x":x,"y":y,"room":a["room"]})
                if path is None:
                    raise CommandError("No path to that interior tile")
                self._interrupt(a)
                a.pop("destination",None)
                a["path"] = path
                self.pending_interaction = None
            elif kind == "object":
                aid = data.get("agent")
                if aid not in self.agents or aid=="visitor":
                    raise CommandError("Select a resident")
                self.create_task(aid,"Use "+str(data.get("object")),{"kind":"use","item":data.get("object"),"place":data.get("room")})
            elif kind == "cancel" and self.tasks.get(data.get("task"),{}).get("status") == "paused":
                task = self.tasks[data["task"]]
                task["status"] = "cancelled"
                self.event(task["agent"],"task_cancelled","Paused task cancelled",{"task":task["id"]})
            else:
                if kind in ("move","chat","task"):
                    self.agents["visitor"].pop("destination",None)
                result = super().command(data)
            if kind == "cancel" and self.agents[self.tasks[data["task"]]["agent"]]["task"] is None:
                for oid,lease in list(self.leases.items()):
                    if lease["agent"] == self.tasks[data["task"]]["agent"]:
                        self.leases.pop(oid,None)
            if kind == "cancel":
                self.cleanup_picnic(self.tasks[data["task"]])
            self.storage.decision(self.time,"visitor","command",data)
            self.storage.remember_command(cid,result)
            self.save()
            self.record()
            return result

    def propose(self, aid, request):
        for prior in self.proposals.values():
            if prior["agent"]==aid and prior["status"]=="proposed":
                prior["status"] = "superseded"
        pid = uuid.uuid4().hex[:12]
        self.proposals[pid] = {"id":pid,"agent":aid,"request":request,"status":"proposed","created":self.time}
        self.event(aid,"task_proposed","A task suggestion is waiting for your acceptance.",{"proposal":pid})

    def record(self):
        state = self.snapshot()
        state["layout"] = copy.deepcopy(self.layout)
        self.storage.record_frame(state)
        self.last_frame = self.time

    def snapshot(self):
        state = super().snapshot()
        for a in state["agents"]:
            a.update(room=self.agents[a["id"]].get("room",""),skin=self.agents[a["id"]].get("skin",a["id"]))
        state["community"] = copy.deepcopy(self.community)
        for a in state["agents"]:
            original = self.agents[a["id"]]
            a["credits"] = original.get("credits",25)
            a["working"] = copy.deepcopy(original.get("working"))
            job = next((j for j in self.jobs if j["agent"]==a["id"] and j["revision"]==original["revision"] and not j["future"].done()),None)
            a["waiting_seconds"] = round(time.monotonic()-job.get("queued_at",time.monotonic())) if job else 0
            a["cognition_stage"] = ("Generating reply" if job["future"].running() else "Queued for model") if job else ""
        state.update(proposals=copy.deepcopy(list(self.proposals.values())[-20:]),appointments=copy.deepcopy(list(self.appointments.values())),objects=copy.deepcopy(self.leases),
            memory=self.semantic.status(),metrics=copy.deepcopy(self.metrics),queue=sum(not j["future"].done() for j in self.jobs))
        return state

    def inspect(self, aid):
        detail = super().inspect(aid)
        a = self.agents[aid]
        detail["current_action"] = copy.deepcopy(a.get("routine"))
        detail["commitments"] = [copy.deepcopy(ap) for ap in self.appointments.values() if aid in ap["accepted"]]
        detail["memory_mode"] = self.semantic.status()
        for m in detail["memories"]:
            m["confidence"] = "inference" if m["kind"]=="reflection" else "reported statement" if m["kind"] in ("conversation","reported") else "direct record"
        return detail

    def save_state(self):
        return {**super().save_state(),"community":self.community,"appointments":self.appointments,"layout":self.layout,"leases":self.leases,"proposals":self.proposals}
