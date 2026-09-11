import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server.world import World, CommandError, distance
from server.model import Cognition
from server.memory import SemanticMemory
from server.scenario import validate, populate
from test_simulation import quiet, advance


class RoadmapTests(unittest.TestCase):
    def setUp(self):
        self.world = World(cognition=Cognition("demo"),restore=False)
        quiet(self.world)

    def tearDown(self):
        self.world.close()

    def plan(self, text):
        a = self.world.agents["samir"]
        spec = self.world.fallback.task(self.world._context(a,text,request=text))
        return self.world.create_task("samir",text,spec)

    def test_sequence_delivery_then_physical_report(self):
        self.world.agents["visitor"].update(x=14.,y=8.)
        self.world.agents["samir"]["next_observe"] = 0
        self.world.observe()
        task = self.plan("Bring coffee to Elena then report back")
        advance(self.world,lambda:task["status"]=="completed",1500)
        self.assertEqual([r["kind"] for r in task["step_results"]],["deliver","report"])
        self.assertLessEqual(distance(self.world.agents["samir"],self.world.agents["visitor"]),1.5)
        self.assertEqual(len(self.world.agents["elena"]["inventory"]),1)
        self.assertTrue(all(r["evidence"] for r in task["step_results"]))

    def test_invalid_later_step_does_not_start_partial_plan(self):
        with self.assertRaises(CommandError):
            self.world.create_task("maya","bad plan",{"kind":"sequence","steps":[{"kind":"wait","minutes":1},{"kind":"deliver","recipient":"unknown","item":"coffee"}]})
        self.assertFalse(self.world.tasks)
        self.assertIsNone(self.world.agents["maya"]["task"])

    def test_cancel_sequence_does_not_run_dependent_step(self):
        task = self.plan("Wait for 1 minute then bring coffee to Elena")
        self.world.command({"id":"cancel-sequence","kind":"cancel","task":task["id"]})
        for _ in range(30): self.world.tick(.5)
        self.assertEqual(task["status"],"cancelled")
        self.assertFalse(self.world.agents["elena"]["inventory"])

    def test_object_use_enters_room_and_records_duration(self):
        a = self.world.agents["maya"]
        task = self.world.create_task("maya","Use bed",{"kind":"use","item":"bed","place":"home"})
        advance(self.world,lambda:task["status"]=="completed",1500)
        self.assertEqual(a["room"],"home")
        events = [e for e in self.world.storage.events(200) if e["kind"]=="object_use"]
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]["payload"]["duration"],60)
        self.assertIn(events[0]["id"],task["evidence"])

    def test_paused_task_can_be_reprioritized_without_losing_inventory(self):
        a = self.world.agents["samir"]
        a["inventory"] = [{"id":"existing","kind":"coffee"}]
        first = self.world.create_task("samir","Delivery",{"kind":"deliver","recipient":"elena","item":"coffee"})
        self.world.command({"id":"suspend","kind":"suspend_task","task":first["id"]})
        second = self.world.create_task("samir","Wait",{"kind":"wait","minutes":1})
        self.world.command({"id":"cancel-old","kind":"cancel","task":first["id"]})
        self.assertEqual(a["task"],second["id"])
        self.assertEqual(a["inventory"][0]["id"],"existing")
        advance(self.world,lambda:second["status"]=="completed")

    def test_object_reservation_blocks_a_second_user(self):
        for aid,x in (("maya",2),("noah",3)):
            self.world.agents[aid].update(room="home",x=float(x),y=2.)
        first = self.world.create_task("maya","Use bed",{"kind":"use","item":"bed","place":"home"})
        second = self.world.create_task("noah","Use bed",{"kind":"use","item":"bed","place":"home"})
        self.world._task(self.world.agents["noah"])
        self.world.agents["maya"].update(x=2.5,y=2.)
        self.world._task(self.world.agents["maya"])
        self.assertEqual(first["status"],"blocked")
        self.assertEqual(self.world.leases["bed"]["agent"],"noah")
        self.assertNotEqual(second["status"],"completed")

    def test_room_walls_prevent_hearing_and_collision_between_rooms(self):
        maya,noah = self.world.agents["maya"],self.world.agents["noah"]
        maya.update(room="cafe",x=2.,y=3.)
        noah.update(room="home",x=2.,y=3.)
        self.assertFalse(self.world.visible(maya,noah))
        self.assertEqual(distance(maya,noah),float("inf"))
        self.world.speak("maya","The secret is daisies",["noah"])
        self.assertFalse(any("daisies" in m["text"] for m in self.world.storage.memories("noah")))

    def test_nearby_bystander_records_statement_as_reported(self):
        self.world.agents["noah"].update(x=6.,y=7.)
        self.world.speak("maya","A story I heard yesterday",[])
        found = [m for m in self.world.storage.memories("noah") if "A story" in m["text"]]
        self.assertEqual(found[0]["kind"],"reported")

    def test_invitation_acceptance_and_real_attendance(self):
        task = self.world.create_task("maya","Invite Elena",{"kind":"invite","guests":["elena"],"place":"park","at":int(self.world.time+600)})
        advance(self.world,lambda:task["status"] in ("completed","failed"),1500)
        ap = self.world.appointments[task["appointment"]]
        self.assertEqual(ap["invited"],["elena"])
        self.assertIn("elena",ap["accepted"])
        self.assertIn("elena",ap["attended"])
        self.assertEqual(task["status"],"completed")
        self.assertTrue(any(e["kind"]=="attendance" for e in self.world.storage.events(400)))

    def test_busy_guest_declines_and_task_never_claims_full_attendance(self):
        self.world.create_task("elena","Wait",{"kind":"wait","minutes":30})
        task = self.world.create_task("maya","Invite Elena",{"kind":"invite","guests":["elena"],"place":"park","at":int(self.world.time+600)})
        advance(self.world,lambda:task["status"] in ("completed","failed"),1500)
        ap = self.world.appointments[task["appointment"]]
        self.assertIn("elena",ap["declined"])
        self.assertNotIn("elena",ap["accepted"])
        self.assertEqual(task["status"],"failed")

    def test_replay_is_immutable_and_hash_checked(self):
        self.world.tick(.5)
        frame = self.world.storage.replay_index()[0]
        state = self.world.storage.replay_frame(frame["id"])
        old_x = state["agents"][0]["x"]
        self.world.agents["maya"]["x"] += 1
        self.assertEqual(self.world.storage.replay_frame(frame["id"])["agents"][0]["x"],old_x)
        self.world.storage.db.execute("UPDATE replay_frames SET digest='bad' WHERE id=?",(frame["id"],))
        with self.assertRaisesRegex(ValueError,"integrity"):
            self.world.storage.replay_frame(frame["id"])

    def test_atomic_failure_rolls_back_world_events_and_command_receipt(self):
        old = self.world.time
        events = self.world.storage.events()
        with patch.object(self.world.storage,"save",side_effect=RuntimeError("disk fault")):
            with self.assertRaises(RuntimeError): self.world.tick(.5)
        self.assertEqual(self.world.time,old)
        self.assertEqual(self.world.storage.events(),events)
        with patch.object(self.world.storage,"save",side_effect=RuntimeError("disk fault")):
            with self.assertRaises(RuntimeError): self.world.command({"id":"fault","kind":"cafe","open":False})
        self.assertTrue(self.world.cafe_open)
        self.assertIsNone(self.world.storage.command_result("fault"))

    def test_sequence_and_rooms_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"world.db"
            w = World(path,cognition=Cognition("demo"),restore=False)
            quiet(w)
            w.agents["maya"].update(room="home",x=2.,y=3.)
            task = w.create_task("maya","Wait then visit",{"kind":"sequence","steps":[{"kind":"wait","minutes":1},{"kind":"visit","place":"park"}]})
            w.tick(.5)
            tid = task["id"]
            w.close()
            restored = World(path,cognition=Cognition("demo"))
            try:
                self.assertEqual(restored.agents["maya"]["room"],"home")
                self.assertEqual(len(restored.tasks[tid]["plan"]),2)
                quiet(restored)
                advance(restored,lambda:restored.tasks[tid]["status"]=="completed",1500)
                self.assertEqual(restored.agents["maya"]["room"],"")
            finally: restored.close()

    def test_25_residents_have_unique_walkable_spawns_and_supported_skins(self):
        layout = populate(self.world.layout,25)
        self.assertEqual(len(layout["residents"]),26)
        self.assertEqual(len({p["id"] for p in layout["residents"]}),26)
        self.assertEqual(validate(layout),layout)
        broken = copy.deepcopy(layout)
        broken["residents"][1]["id"] = broken["residents"][0]["id"]
        with self.assertRaises(ValueError): validate(broken)

    def test_proposal_requires_acceptance_and_deduplicates_command(self):
        self.world.propose("maya","Visit the park")
        proposal = next(iter(self.world.proposals.values()))
        self.assertFalse(self.world.tasks)
        cmd = {"id":"accept","kind":"accept_proposal","proposal":proposal["id"]}
        first = self.world.command(cmd)
        self.assertEqual(self.world.command(cmd),first)
        self.assertEqual(proposal["status"],"accepted")
        advance(self.world,lambda:len(self.world.tasks)==1)

    def test_repeated_observations_are_deduplicated(self):
        a = self.world.storage.memory("maya","observation","Same view",self.world.time)
        b = self.world.storage.memory("maya","observation","Same view",self.world.time+12)
        self.assertEqual(a,b)

    def test_reflection_requires_accumulated_evidence(self):
        a = self.world.agents["maya"]
        self.assertFalse(self.world.reflection_due(a))
        for i in range(5): self.world.storage.memory("maya","conversation",str(i),self.world.time+1,7)
        self.assertTrue(self.world.reflection_due(a))


class SemanticTests(unittest.TestCase):
    def test_semantic_ranking_cache_and_private_candidate_scope(self):
        memory = SemanticMemory()
        memory.model = "test-embedding"
        candidates = [{"id":1,"owner":"maya","text":"I enjoy gardening","importance":4,"accessed":0},
                      {"id":2,"owner":"maya","text":"I bought a parcel","importance":4,"accessed":0}]
        for text,vector in [("flowers",[1,0]),("I enjoy gardening",[1,0]),("I bought a parcel",[0,1])]:
            memory.cache[memory.key(text)] = vector
        context = {"time":0,"memory_candidates":candidates,"memory_query":"flowers","memories":list(reversed(candidates))}
        with patch("urllib.request.urlopen",side_effect=AssertionError("Cache should avoid network")):
            ranked = memory.rank(context)["memories"]
        self.assertEqual(ranked[0]["id"],1)
        self.assertEqual(ranked[0]["retrieval_method"],"semantic")
        self.assertTrue(all(m["owner"]=="maya" for m in ranked))

    def test_embedding_failure_keeps_lexical_context(self):
        memory = SemanticMemory()
        memory.model = "missing"
        context = {"time":0,"memories":[{"id":1,"text":"known fact"}],"memory_query":"fact"}
        with patch("urllib.request.urlopen",side_effect=TimeoutError):
            result = memory.rank(context)
        self.assertEqual(result["memories"][0]["id"],1)
        self.assertEqual(memory.status()["mode"],"lexical")
