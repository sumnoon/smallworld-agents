"""Finite resources and cooperative picnics with physical, recorded actions."""
import copy
import uuid

ACTIONS = {"plant":"garden", "water":"garden", "harvest":"garden", "buy":"market", "prepare":"cafe"}
DONE = {"completed", "failed", "cancelled", "declined"}
# A cancelled self-directed errand is not retried for ten simulated minutes.
AUTONOMY_DEFERRAL = 600


def initial_community():
    return {"beds":{}, "seeds":12, "supplies":12, "price":3, "weather":"clear"}


class CommunityMixin:
    def validate_step(self, aid, step):
        from .world import CommandError
        if isinstance(step, dict) and step.get("kind") in (*ACTIONS, "share", "picnic"):
            kind = step["kind"]
            places = ("garden", "market", "cafe", "plaza") if kind == "picnic" else (ACTIONS[kind],) if kind in ACTIONS else ()
            if any(p not in self.layout["places"] for p in places):
                raise CommandError("This activity needs the expanded garden, market and plaza map")
            if kind == "share" and (step.get("recipient") not in self.agents or step["recipient"]==aid or step.get("item") not in ("supplies", "vegetables")):
                raise CommandError("Share supplies or vegetables with another known resident")
            return
        return super().validate_step(aid, step)

    def activate_step(self, task, spec):
        kind = spec["kind"]
        if kind not in (*ACTIONS, "share", "picnic"):
            return super().activate_step(task, spec)
        super().activate_step(task, {"kind":"visit", "place":ACTIONS.get(kind, "plaza")})
        for key in ("work_until", "picnic", "appointment"):
            task.pop(key, None)
        task.update(kind=kind, recipient=spec.get("recipient", ""), item=spec.get("item", ""),
                    steps=["Walk to the work site", "Perform and verify the action"], deadline=self.time+14400)
        if kind == "picnic":
            task["steps"] = ["Recruit a helper", "Grow vegetables", "Receive market supplies", "Prepare food", "Invite neighbors", "Serve the picnic"]
            task["picnic"] = {"phase":"recruit", "declined":[], "helper":None, "helper_task":None, "guests":[], "served":[]}

    def bed_goal(self, aid):
        x,y = self.layout["places"]["garden"]
        candidates = [(x+dx,y+dy) for dy in (-2,-1,0,1,2,3) for dx in (1,2,3,4,5) if self.valid(x+dx,y+dy)]
        index = list(self.agents).index(aid) % len(candidates)
        x,y = candidates[index]
        return {"x":x,"y":y,"room":""}

    def action_site(self, a, kind):
        if kind in ("plant","water","harvest"):
            return self.bed_goal(a["id"])
        x,y = self.layout["places"][ACTIONS[kind]]
        return {"x":x,"y":y,"room":""}

    def work_action(self, a, task, kind):
        arrived = self.go(a,self.action_site(a,kind),"Walking to "+ACTIONS[kind])
        if arrived is None:
            self.block_task(a,task,"The work site is blocked; retrying")
            return False
        if not arrived:
            a.pop("working",None)
            return False
        bed = self.community["beds"].get(a["id"])
        inventory = a["inventory"]
        missing = None
        if kind == "plant" and (bed or self.community["seeds"] <= 0):
            missing = "Harvest the existing bed first" if bed else "No seeds remain"
        elif kind in ("water","harvest") and not bed:
            missing = "Plant vegetables first"
        elif kind == "harvest" and (not bed.get("ready_at") or self.time < bed["ready_at"]):
            missing = "Water the vegetables first" if not bed.get("ready_at") else "Waiting for the watered vegetables to ripen"
        elif kind == "buy" and (self.community["supplies"] <= 0 or a.get("credits",25) < self.community["price"]):
            missing = "Market supplies are sold out" if self.community["supplies"] <= 0 else "Not enough credits for market supplies"
        elif kind == "prepare" and (not self.cafe_open or any(not any(i["kind"]==k for i in inventory) for k in ("supplies","vegetables"))):
            missing = "Cafe is closed" if not self.cafe_open else "Need both vegetables and market supplies to prepare food"
        if missing:
            a.pop("working",None)
            self.block_task(a,task,missing)
            return False
        if task["kind"] != "picnic":
            task["step"] = 1
        task.setdefault("work_until",self.time+30)
        a["working"] = {"kind":kind,"until":task["work_until"]}
        a["status"] = {"plant":"Planting vegetables", "water":"Watering vegetables", "harvest":"Harvesting vegetables", "buy":"Buying picnic supplies", "prepare":"Preparing picnic food"}[kind]
        if self.time < task["work_until"]:
            return False
        item = None
        if kind == "plant":
            self.community["seeds"] -= 1
            self.community["beds"][a["id"]] = {**self.bed_goal(a["id"]), "planted":self.time,"ready_at":None}
        elif kind == "water":
            if not bed["ready_at"]:
                bed["ready_at"] = self.time+180
        elif kind == "harvest":
            self.community["beds"].pop(a["id"])
            item = {"id":uuid.uuid4().hex,"kind":"vegetables"}
        elif kind == "buy":
            self.community["supplies"] -= 1
            a["credits"] = a.get("credits",25)-self.community["price"]
            item = {"id":uuid.uuid4().hex,"kind":"supplies"}
        elif kind == "prepare":
            consumed = []
            for k in ("vegetables","supplies"):
                selected = next(i for i in inventory if i["kind"]==k)
                consumed.append(selected["id"])
                inventory.remove(selected)
            item = {"id":uuid.uuid4().hex,"kind":"picnic_food","ingredients":consumed,"servings":4}
        if item:
            inventory.append(item)
        task["evidence"].append(self.event(a["id"],"community_"+kind,a["status"]+": finished.",{"task":task["id"],"item":copy.deepcopy(item),"site":self.action_site(a,kind)}))
        a.pop("working",None)
        task.pop("work_until",None)
        return True

    def _task(self, a):
        task = self.tasks[a["task"]]
        kind = task["kind"]
        if kind not in (*ACTIONS,"share","picnic"):
            return super()._task(a)
        if self.time > task["deadline"]:
            return self.fail_community(a,task,"Community task deadline elapsed")
        # A self-directed planting cannot finish once the shared seeds are gone, so it releases the resident instead of waiting.
        if (kind == "plant" and task.get("origin") == "autonomous" and self.community["seeds"] <= 0
                and a["id"] not in self.community["beds"]):
            return self.fail_community(a,task,"No seeds remain")
        if task["status"] == "blocked" and self.time < task["retry_at"]:
            return
        task.update(status="running",blocker="")
        if kind in ACTIONS:
            if self.work_action(a,task,kind):
                self.complete_task(a,task,"Finished "+kind+" with verified world effects.")
        elif kind == "share":
            item = next((i for i in a["inventory"] if i["kind"]==task["item"]),None)
            if not item:
                return self.block_task(a,task,"I do not have the requested item to share")
            target = self.find_resident(a,task)
            if target:
                a["inventory"].remove(item)
                target["inventory"].append(item)
                task["evidence"].append(self.event(a["id"],"community_handoff",a["name"]+" handed supplies to "+target["name"],{"task":task["id"],"item":item["id"],"recipient":target["id"]}))
                target["relationships"][a["id"]] = min(100,target["relationships"].get(a["id"],0)+5)
                self.speak(a["id"],"Here are the supplies for our picnic.",[target["id"]])
                self.complete_task(a,task,"Handed over the item in person.")
        else:
            self.picnic_step(a,task)

    def start_autonomous_task(self, a):
        """Plant when vegetables are needed, water an unwatered bed, or harvest a ripe one, when nothing else claims the resident."""
        bed = self.community["beds"].get(a["id"])
        if bed:
            # A watered crop that is still growing leaves the resident to their routine.
            action = None if bed.get("ready_at") and self.time < bed["ready_at"] else "harvest" if bed.get("ready_at") else "water"
        else:
            # Seeds are only checked here; planting rechecks them on every work tick.
            action = "plant" if self.community["seeds"] > 0 and not any(i["kind"] == "vegetables" for i in a["inventory"]) else None
        if not action or "garden" not in self.layout["places"]:
            return super().start_autonomous_task(a)
        if (a["task"] or a["conversation"] or a["thinking"] or a["routine"]
                or self.time < a.get("autonomy_deferred_until", 0)
                or (self.pending_interaction and self.pending_interaction["agent"] == a["id"])
                or a["needs"]["energy"] < 30 or a["needs"]["hunger"] > 70
                or any(t["agent"] == a["id"] and t["status"] not in DONE for t in self.tasks.values())
                or any(ap["status"] == "scheduled" and a["id"] in ap["accepted"] and ap["at"]-600 <= self.time <= ap["at"]+600
                       for ap in self.appointments.values())):
            return super().start_autonomous_task(a)
        self.create_task(a["id"],action.capitalize()+" my garden bed",{"kind":action},origin="autonomous")
        return True

    def defer_autonomy(self, task):
        if task.get("origin") == "autonomous" and task["status"] == "cancelled":
            a = self.agents[task["agent"]]
            a["autonomy_deferred_until"] = max(a.get("autonomy_deferred_until", 0), self.time+AUTONOMY_DEFERRAL)

    def fail_community(self, a, task, reason):
        task.update(status="failed",blocker=reason)
        self.event(a["id"],"task_failed",reason,{"task":task["id"]})
        self._interrupt(a)
        a["task"] = None
        self.cleanup_picnic(task)

    def cleanup_picnic(self, task):
        p = task.get("picnic")
        if not p:
            return
        child = self.tasks.get(p.get("helper_task"))
        if child and child["status"] not in DONE:
            child["status"] = "cancelled"
            helper = self.agents[child["agent"]]
            if helper["task"] == child["id"]:
                self._interrupt(helper)
                helper["task"] = None
            self.event(child["agent"],"task_cancelled","The picnic was stopped; its supply errand was cancelled.",{"task":child["id"]})
        ap = self.appointments.get(task.get("appointment"))
        if ap and ap["status"] == "scheduled":
            ap["status"] = "cancelled"
        if task["status"] in ("failed", "cancelled"):
            p["cleaned"] = True

    def picnic_step(self, a, task):
        from .world import distance
        p = task["picnic"]
        phase = p["phase"]
        if phase == "recruit":
            choices = [b for b in self.agents.values() if b["id"] not in (a["id"],"visitor",*p["declined"])]
            if not choices:
                return self.fail_community(a,task,"Nobody could accept the supply errand. Try again when residents are free.")
            helper = next((b for b in choices if b["id"]==p.get("candidate")),choices[0])
            p["candidate"] = helper["id"]
            task["recipient"] = helper["id"]
            target = self.find_resident(a,task)
            if not target:
                return
            self.speak(a["id"],"Will you buy supplies at the market and bring them to me for a picnic?",[helper["id"]])
            if helper["task"] or any(ap["status"]=="scheduled" and helper["id"] in ap["accepted"] for ap in self.appointments.values()):
                self.speak(helper["id"],"I have another commitment. Please ask someone else.",[a["id"]])
                p["declined"].append(helper["id"])
                p.pop("candidate",None)
                task.update(search=0,next_repath=0)
                return
            self.speak(helper["id"],"Yes. I'll buy supplies and bring them back to you.",[a["id"]])
            child = self.create_task(helper["id"],"Buy and bring picnic supplies",{"kind":"sequence","steps":[{"kind":"buy"},{"kind":"share","item":"supplies","recipient":a["id"]}]})
            child["parent"] = task["id"]
            p.update(helper=helper["id"],helper_task=child["id"],phase="plant")
            task["evidence"].append(self.event(a["id"],"picnic_help_accepted","Supply help accepted in person",{"task":task["id"],"helper":helper["id"]}))
            task["step"] = 1
            return
        child = self.tasks.get(p.get("helper_task"))
        if child and child["status"] in ("failed","cancelled","declined"):
            return self.fail_community(a,task,"The supply errand stopped. Start a new picnic or finish the supplies separately.")
        if phase in ("plant","water","harvest","prepare"):
            # An existing personal crop can be used without consuming another seed.
            if phase == "plant" and a["id"] in self.community["beds"]:
                p["phase"] = "water"
                return
            if self.work_action(a,task,phase):
                p["phase"] = {"plant":"water","water":"harvest","harvest":"supplies","prepare":"invite"}[phase]
                task["step"] = {"plant":1,"water":1,"harvest":2,"prepare":4}[phase]
            return
        if phase == "supplies":
            if not child or child["status"] != "completed":
                a["status"] = "Waiting at the garden for market supplies"
                return
            p["phase"] = "prepare"
            task["step"] = 3
            return
        if phase == "invite":
            ap = self.appointments.get(task.get("appointment"))
            if not ap:
                guests = [p["helper"]]
                guests += [b["id"] for b in self.agents.values() if b["id"] not in (a["id"],"visitor",p["helper"]) and not b["task"]][:1]
                p["guests"] = guests
                task.update(guests=guests,place="plaza",at=int(self.time+1200),search=0,next_repath=0)
            if ap and ap["status"] == "finished":
                return self.fail_community(a,task,"The picnic meeting ended before everyone could be served")
            self.invite_step(a,task)
            ap = self.appointments.get(task.get("appointment"))
            if ap and ap["declined"]:
                return self.fail_community(a,task,"A picnic guest declined because of another commitment")
            if not ap or self.time < ap["at"] or any(g not in ap["attended"] for g in (a["id"],*p["guests"])):
                return
            task["step"] = 5
            if self.community["weather"] == "rain":
                return self.block_task(a,task,"Rain is delaying the outdoor picnic; waiting for clear weather")
            food = next((i for i in a["inventory"] if i["kind"]=="picnic_food"),None)
            if not food:
                return self.fail_community(a,task,"The prepared picnic food is missing")
            people = [a["id"],*p["guests"]]
            if any(distance(a,self.agents[g])>3 for g in people):
                return
            if food["servings"] < len(people):
                return self.fail_community(a,task,"There is not enough prepared food for the guests")
            food["servings"] -= len(people)
            for aid in people:
                b = self.agents[aid]
                b["needs"]["hunger"] = max(0,b["needs"]["hunger"]-30)
                if aid != a["id"]:
                    b["relationships"][a["id"]] = min(100,b["relationships"].get(a["id"],0)+8)
            p.update(phase="completed",served=people)
            ap["status"] = "finished"
            seq = self.event(a["id"],"picnic_served","Picnic food served to everyone present.",{"task":task["id"],"item":food["id"],"residents":people,"remaining_servings":food["servings"]})
            task["evidence"].append(seq)
            for aid in people:
                self.storage.memory(aid,"experience","We ate the picnic together at the plaza.",self.time,8,[seq])
            self.speak(a["id"],"We made this together. Thank you for joining the picnic!",p["guests"])
            self.complete_task(a,task,"Grew vegetables, received supplies, prepared food and served the guests in person.")

    def _interrupt(self, a):
        a.pop("working",None)
        return super()._interrupt(a)
