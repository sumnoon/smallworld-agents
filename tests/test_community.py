import json
import tempfile
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch
from server.world import World, CommandError, distance
from server.model import Cognition
from server.performance import fast_task
from test_simulation import quiet, advance


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.world = World(cognition=Cognition("demo"),restore=False)
        quiet(self.world)

    def tearDown(self):
        self.world.close()

    def test_fast_parser_rejects_qualifiers_and_unknown_actions(self):
        context = self.world._context(self.world.agents["samir"])
        for request in ("Bring coffee to Elena if she wants it", "Bring coffee to Elena and steal money", "Do not bring coffee to Elena", "Wait for 300 minutes", "Visit the park unless it rains"):
            self.assertIsNone(fast_task({**context,"request":request}),request)
        result = fast_task({**context,"request":"Bring coffee to Elena then report back"})
        self.assertEqual([s["kind"] for s in result["steps"]],["deliver","report"])

    def test_fast_task_does_not_wait_for_busy_model_worker(self):
        w = self.world
        a = w.agents["samir"]
        with patch.object(w.pool,"submit",side_effect=AssertionError("Should not need model worker")):
            w.submit("task",a,w._context(a,request="Bring coffee to Elena"))
        w._jobs()
        self.assertIsNotNone(a["task"])
        self.assertEqual(w.metrics["samir:task"]["last_source"],"local_rules")

    def test_garden_requires_water_and_harvests_once(self):
        w = self.world
        a = w.agents["elena"]
        task = w.create_task(a["id"],"Grow vegetables",{"kind":"sequence","steps":[{"kind":"plant"},{"kind":"water"},{"kind":"harvest"}]})
        advance(w,lambda:task["status"]=="completed",1800)
        self.assertEqual(task["status"],"completed")
        self.assertEqual(w.community["seeds"],11)
        self.assertEqual([i["kind"] for i in a["inventory"]],["vegetables"])
        self.assertNotIn(a["id"],w.community["beds"])
        task = w.create_task(a["id"],"Harvest again",{"kind":"harvest"})
        advance(w,lambda:task["status"]=="blocked")
        self.assertEqual(len(a["inventory"]),1)

    def test_market_deducts_once_and_refuses_unaffordable_purchase(self):
        w = self.world
        a = w.agents["samir"]
        task = w.create_task(a["id"],"Buy supplies",{"kind":"buy"})
        advance(w,lambda:task["status"]=="completed",1500)
        self.assertEqual(task["status"],"completed")
        self.assertEqual(a["credits"],22)
        self.assertEqual(w.community["supplies"],11)
        a["credits"] = 0
        task = w.create_task(a["id"],"Buy more",{"kind":"buy"})
        advance(w,lambda:task["status"]=="blocked")
        self.assertEqual(w.community["supplies"],11)
        self.assertEqual(len(a["inventory"]),1)

    def test_cooperative_picnic_runs_to_real_serving(self):
        w = self.world
        task = w.create_task("maya","Organize a picnic",{"kind":"picnic"})
        advance(w,lambda:task["status"] in ("completed","failed"),6000)
        self.assertEqual(task["status"],"completed",json.dumps(task))
        p = task["picnic"]
        self.assertEqual(w.tasks[p["helper_task"]]["status"],"completed")
        self.assertGreaterEqual(len(p["served"]),2)
        host = w.agents["maya"]
        self.assertTrue(all(distance(host,w.agents[g])<=3 for g in p["served"]))
        self.assertEqual(w.community["supplies"],11)
        self.assertEqual(w.community["seeds"],11)
        food = next(i for i in host["inventory"] if i["kind"]=="picnic_food")
        self.assertEqual(food["servings"],4-len(p["served"]))
        self.assertEqual(len(food["ingredients"]),2)

    def test_cancel_picnic_stops_helper_and_preserves_owned_items(self):
        w = self.world
        task = w.create_task("maya","Organize a picnic",{"kind":"picnic"})
        advance(w,lambda:bool(task["picnic"]["helper_task"]),1000)
        child = w.tasks[task["picnic"]["helper_task"]]
        command = {"id":"stop-picnic","kind":"cancel","task":task["id"]}
        w.command(command)
        self.assertEqual(w.command(command),{"ok":True})
        self.assertEqual(child["status"],"cancelled")
        self.assertIsNone(w.agents[child["agent"]]["task"])

    def test_picnic_helper_errand_cannot_be_paused(self):
        w = self.world
        task = w.create_task("maya","Organize a picnic",{"kind":"picnic"})
        advance(w,lambda:bool(task["picnic"]["helper_task"]),1000)
        child = w.tasks[task["picnic"]["helper_task"]]
        with self.assertRaisesRegex(CommandError,"supports a picnic"):
            w.command({"id":"pause-helper","kind":"suspend_task","task":child["id"]})
        self.assertNotEqual(child["status"],"paused")

    def test_failed_picnic_is_cleaned_up_once(self):
        w = self.world
        task = w.create_task("maya","Organize a picnic",{"kind":"picnic"})
        advance(w,lambda:bool(task["picnic"]["helper_task"]),1000)
        w.fail_community(w.agents["maya"],task,"Stopped for test")
        self.assertTrue(task["picnic"]["cleaned"])
        with patch.object(w,"cleanup_picnic",side_effect=AssertionError("Cleanup should not repeat")):
            w.tick(.5)

    def test_save_writes_one_complete_snapshot(self):
        w = self.world
        with patch.object(w.storage,"save",wraps=w.storage.save) as save:
            w.save()
        self.assertEqual(save.call_count,1)
        saved = w.storage.load()
        for key in ("agents","tasks","community","appointments","layout","leases","proposals"):
            self.assertIn(key,saved)

    def test_player_request_frees_full_queue_in_ollama_mode(self):
        w = self.world
        w.cognition.mode = "ollama"
        for _ in range(8):
            w.jobs.append({"future":Future(),"method":"decide","agent":"jun","revision":w.agents["jun"]["revision"],"context":{}})
        a = w.agents["samir"]
        with patch.object(w.pool,"submit",return_value=Future()):
            self.assertTrue(w.submit("task",a,{"request":"Please help with something unusual"}))
        self.assertTrue(all(j["future"].cancelled() for j in w.jobs[:8]))

    def test_failed_transaction_restores_community_resources(self):
        w = self.world
        with self.assertRaises(RuntimeError):
            with w.atomic():
                w.community["seeds"] = 0
                raise RuntimeError("rollback")
        self.assertEqual(w.community["seeds"],12)

    def test_resources_and_crop_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/"town.db")
            w = World(path,cognition=Cognition("demo"),restore=False)
            w.community["seeds"] = 7
            w.community["beds"]["elena"] = {"x":7,"y":19,"ready_at":w.time+180}
            w.agents["elena"]["credits"] = 9
            w.close()
            restored = World(path,cognition=Cognition("demo"))
            try:
                self.assertEqual(restored.community["seeds"],7)
                self.assertEqual(restored.agents["elena"]["credits"],9)
                self.assertIn("elena",restored.community["beds"])
            finally:
                restored.close()

    def test_rain_delays_serving_until_weather_clears(self):
        w = self.world
        w.community["weather"] = "rain"
        task = w.create_task("maya","Picnic",{"kind":"picnic"})
        advance(w,lambda:task["step"]==5 or task["status"]=="failed",5000)
        self.assertEqual(task["status"],"blocked",json.dumps(task))
        self.assertEqual(task["picnic"]["served"],[])
        w.command({"id":"clear-sky","kind":"weather","weather":"clear"})
        advance(w,lambda:task["status"]=="completed",1000)
        self.assertEqual(task["status"],"completed")

    def test_busy_helper_declines_without_losing_existing_task(self):
        w = self.world
        prior = w.create_task("noah","Wait",{"kind":"wait","minutes":30})
        task = w.create_task("maya","Picnic",{"kind":"picnic"})
        advance(w,lambda:bool(task["picnic"]["helper_task"]),1200)
        self.assertIn("noah",task["picnic"]["declined"])
        self.assertEqual(w.agents["noah"]["task"],prior["id"])
        self.assertNotEqual(task["picnic"]["helper"],"noah")

    def test_cache_only_retrieval_never_loads_embedding_model(self):
        w = self.world
        w.semantic.model = "embeddinggemma"
        context = w._context(w.agents["maya"],"A new memory query")
        with patch("urllib.request.urlopen",side_effect=AssertionError("No network in cache-only mode")):
            result = w.semantic.rank(context,allow_network=False)
        self.assertTrue(result["memories"])
        self.assertEqual(w.semantic.calls,0)
        self.assertEqual(w.semantic.last_retrieval,"lexical")

    def test_obsolete_location_is_discarded_after_searching_it(self):
        w = self.world
        a = w.agents["samir"]
        a.update(x=12.,y=6.)
        w.agents["elena"].update(x=7.,y=19.)
        a["known_positions"]["elena"] = {"x":12,"y":6,"room":"","time":w.time-100}
        task = w.create_task("samir","Meet Elena",{"kind":"meet","recipient":"elena"})
        w.find_resident(a,task)
        self.assertNotIn("elena",a["known_positions"])


def plant(world, aid):
    world.community["beds"][aid] = {**world.bed_goal(aid),"planted":world.time,"ready_at":None}


def autonomous(world, aid):
    return [t for t in world.tasks.values() if t["agent"]==aid and t.get("origin")=="autonomous"]


def event_row(world, seq):
    row = world.storage.db.execute("SELECT * FROM events WHERE id=?",(seq,)).fetchone()
    return {**dict(row),"payload":json.loads(row["payload"])}


class AutonomousWateringTests(unittest.TestCase):
    def setUp(self):
        self.world = World(cognition=Cognition("demo"),restore=False)
        quiet(self.world)

    def tearDown(self):
        self.world.close()

    def test_idle_resident_walks_to_own_bed_and_waters_it(self):
        w = self.world
        a = w.agents["elena"]
        plant(w,"elena")
        a["next_decision"] = w.time
        w.tick(.5)
        tasks = autonomous(w,"elena")
        self.assertEqual(len(tasks),1)
        task = tasks[0]
        self.assertEqual((task["kind"],a["task"]),("water",task["id"]))
        # Scheduling alone has no physical effect.
        self.assertIsNone(w.community["beds"]["elena"]["ready_at"])
        self.assertEqual((w.community["seeds"],a["inventory"]),(12,[]))
        accepted = w.storage.db.execute("SELECT * FROM events WHERE kind='task_accepted' AND json_extract(payload,'$.task')=?",(task["id"],)).fetchone()
        self.assertEqual(json.loads(accepted["payload"])["origin"],"autonomous")
        self.assertNotIn("Alex",accepted["text"])
        self.assertFalse(any("Alex" in m["text"] for m in w.storage.memories("elena") if m["kind"]=="task"))
        advance(w,lambda:task["status"]=="completed",600)
        evidence = [event_row(w,seq) for seq in task["evidence"]]
        self.assertEqual([e["kind"] for e in evidence],["community_water"])
        self.assertLessEqual(distance(a,w.bed_goal("elena")),.8)
        bed = w.community["beds"]["elena"]
        self.assertEqual(bed["ready_at"],evidence[0]["time"]+180)
        self.assertGreaterEqual(evidence[0]["time"]-task["created"],30)
        self.assertEqual((w.community["seeds"],a["inventory"]),(12,[]))

    def test_player_work_interactions_and_appointments_take_precedence(self):
        w = self.world
        for aid in ("samir","noah","maya","jun","elena"):
            plant(w,aid)
        player = w.create_task("samir","Wait",{"kind":"wait","minutes":30})
        self.assertFalse(w.start_autonomous_task(w.agents["samir"]))
        w.command({"id":"pause-samir","kind":"suspend_task","task":player["id"]})
        self.assertFalse(w.start_autonomous_task(w.agents["samir"]))
        w.pending_interaction = {"kind":"task","agent":"noah","text":"Visit the park","repath":0,"expires":w.time+600}
        self.assertFalse(w.start_autonomous_task(w.agents["noah"]))
        w.pending_interaction = None
        a = w.agents["maya"]
        for key,value,restore in (("thinking",True,False),("conversation","chat_x",None),("routine",{"place":"park"},None)):
            a[key] = value
            self.assertFalse(w.start_autonomous_task(a),key)
            a[key] = restore
        for need,value in (("energy",25.0),("hunger",75.0)):
            previous = a["needs"][need]
            a["needs"][need] = value
            self.assertFalse(w.start_autonomous_task(a),need)
            a["needs"][need] = previous
        for offset in (500,-300):
            w.appointments = {"ap":{"id":"ap","host":"noah","place":"plaza","at":w.time+offset,"guests":["maya"],"invited":["maya"],
                                    "accepted":["noah","maya"],"declined":[],"attended":[],"status":"scheduled","task":""}}
            self.assertFalse(w.start_autonomous_task(a),offset)
        w.appointments = {}
        self.assertEqual(autonomous(w,"samir")+autonomous(w,"noah")+autonomous(w,"maya"),[])
        # A running player task is never replaced by a routine-time errand.
        jun = w.create_task("jun","Wait",{"kind":"wait","minutes":30})
        w.agents["jun"]["next_decision"] = w.time
        for _ in range(20):
            w.tick(.5)
        self.assertEqual((w.agents["jun"]["task"],jun["status"]),(jun["id"],"running"))
        self.assertEqual(autonomous(w,"jun"),[])
        # Scheduled appointments outside the window do not block tending the crop.
        w.appointments = {"ap":{"id":"ap","host":"noah","place":"plaza","at":w.time+1200,"guests":["elena"],"invited":["elena"],
                                "accepted":["noah","elena"],"declined":[],"attended":[],"status":"scheduled","task":""}}
        self.assertTrue(w.start_autonomous_task(w.agents["elena"]))

    def test_residents_without_unwatered_beds_keep_routine_decisions(self):
        w = self.world
        plant(w,"maya")
        w.community["beds"]["maya"]["ready_at"] = w.time+100
        for aid in ("maya","jun"):
            w.agents[aid]["next_decision"] = w.time
        w.tick(.5)
        self.assertEqual(autonomous(w,"maya")+autonomous(w,"jun"),[])
        self.assertEqual({j["agent"] for j in w.jobs if j["method"]=="decide"},{"maya","jun"})
        w.tick(.5)
        self.assertTrue(all(w.agents[aid]["routine"] for aid in ("maya","jun")))
        self.assertEqual((w.community["seeds"],len(w.community["beds"])),(12,1))

    def test_repeated_ticks_and_resume_do_not_duplicate_watering(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/"town.db")
            w = World(path,cognition=Cognition("demo"),restore=False)
            quiet(w)
            plant(w,"elena")
            w.agents["elena"]["next_decision"] = w.time
            for _ in range(5):
                w.tick(.5)
                w.agents["elena"]["next_decision"] = w.time
            self.assertEqual(len(autonomous(w,"elena")),1)
            w.close()
            restored = World(path,cognition=Cognition("demo"))
            try:
                quiet(restored)
                a = restored.agents["elena"]
                task = autonomous(restored,"elena")[0]
                self.assertEqual(a["task"],task["id"])
                def done():
                    a["next_decision"] = min(a["next_decision"],restored.time)
                    return task["status"]=="completed"
                advance(restored,done,600)
                for _ in range(20):
                    restored.tick(.5)
                    a["next_decision"] = min(a["next_decision"],restored.time)
                self.assertEqual(len(autonomous(restored,"elena")),1)
                self.assertIsNotNone(restored.community["beds"]["elena"]["ready_at"])
            finally:
                restored.close()

    def test_cancelled_watering_stays_cancelled_and_defers_across_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/"town.db")
            w = World(path,cognition=Cognition("demo"),restore=False)
            quiet(w)
            plant(w,"elena")
            w.agents["elena"]["next_decision"] = w.time
            w.tick(.5)
            first = autonomous(w,"elena")[0]
            w.command({"id":"cancel-water","kind":"cancel","task":first["id"]})
            cancelled_at = w.time
            self.assertEqual(w.agents["elena"]["autonomy_deferred_until"],cancelled_at+600)
            w.agents["elena"]["next_decision"] = w.time
            w.tick(.5)
            self.assertEqual(len(autonomous(w,"elena")),1)
            w.close()
            restored = World(path,cognition=Cognition("demo"))
            try:
                quiet(restored)
                a = restored.agents["elena"]
                self.assertEqual(a["autonomy_deferred_until"],cancelled_at+600)
                while restored.time < cancelled_at+590:
                    a["next_decision"] = restored.time
                    restored.tick(.5)
                    a["routine"] = None
                    self.assertEqual(len(autonomous(restored,"elena")),1)
                def retried():
                    a["next_decision"] = min(a["next_decision"],restored.time)
                    a["routine"] = None
                    return len(autonomous(restored,"elena")) == 2
                advance(restored,retried,20)
                self.assertGreaterEqual(restored.time,cancelled_at+600)
                self.assertEqual(restored.tasks[first["id"]]["status"],"cancelled")
                self.assertIsNone(restored.community["beds"]["elena"]["ready_at"])
            finally:
                restored.close()

    def test_player_can_request_watering_during_deferral(self):
        w = self.world
        plant(w,"elena")
        w.agents["elena"]["next_decision"] = w.time
        w.tick(.5)
        w.command({"id":"cancel-water","kind":"cancel","task":autonomous(w,"elena")[0]["id"]})
        w.command({"id":"player-water","kind":"task","agent":"elena","text":"Water vegetables"})
        advance(w,lambda:bool(w.agents["elena"]["task"]),400)
        task = w.tasks[w.agents["elena"]["task"]]
        self.assertLess(w.time,w.agents["elena"]["autonomy_deferred_until"])
        self.assertEqual((task["kind"],task["origin"]),("water","player"))
        advance(w,lambda:task["status"]=="completed",600)
        self.assertEqual(event_row(w,task["evidence"][0])["kind"],"community_water")


def ripe(world, aid, offset=0):
    plant(world,aid)
    world.community["beds"][aid]["ready_at"] = world.time+offset


def harvest_events(world, aid=None):
    rows = world.storage.db.execute("SELECT id FROM events WHERE kind='community_harvest'").fetchall()
    return [e for e in (event_row(world,r["id"]) for r in rows) if aid is None or e["actor"]==aid]


def dispatch(world, aid):
    world.agents[aid]["next_decision"] = world.time
    world.tick(.5)
    return world.tasks[world.agents[aid]["task"]]


class AutonomousHarvestTests(unittest.TestCase):
    def setUp(self):
        self.world = World(cognition=Cognition("demo"),restore=False)
        quiet(self.world)

    def tearDown(self):
        self.world.close()

    def test_due_decision_harvests_ripe_bed_on_foot_without_decide(self):
        w = self.world
        a = w.agents["elena"]
        ripe(w,"elena")
        plant(w,"noah")
        w.community["beds"]["noah"]["ready_at"] = w.time+5000
        w.agents["noah"]["inventory"] = [{"id":"noah-veg","kind":"vegetables"}]
        others = json.dumps({"bed":w.community["beds"]["noah"],"inventory":w.agents["noah"]["inventory"]})
        resources = (w.community["seeds"],w.community["supplies"],a.get("credits",25))
        # A future decision does not dispatch early, even though the crop is ripe.
        a["next_decision"] = w.time+30
        w.tick(.5)
        self.assertEqual((a["task"],autonomous(w,"elena")),(None,[]))
        bed_before = dict(w.community["beds"]["elena"])
        a["next_decision"] = w.time
        w.tick(.5)
        tasks = autonomous(w,"elena")
        self.assertEqual(len(tasks),1)
        task = tasks[0]
        self.assertEqual((task["kind"],task["origin"],a["task"]),("harvest","autonomous",task["id"]))
        self.assertFalse(any(j["agent"]=="elena" and j["method"]=="decide" for j in w.jobs))
        # Scheduling alone has no physical effect.
        self.assertEqual((w.community["beds"]["elena"],a["inventory"]),(bed_before,[]))
        accepted = w.storage.db.execute("SELECT * FROM events WHERE kind='task_accepted' AND json_extract(payload,'$.task')=?",(task["id"],)).fetchone()
        self.assertEqual(json.loads(accepted["payload"])["origin"],"autonomous")
        self.assertIn("started their own errand: Harvest my garden bed",accepted["text"])
        self.assertFalse(any("Alex" in m["text"] for m in w.storage.memories("elena") if m["kind"]=="task"))
        self.assertIsNone(w.storage.db.execute("SELECT id FROM events WHERE kind='dialogue' AND actor='elena'").fetchone())
        # A later player assignment uses the existing cancel-or-finish rule.
        with self.assertRaisesRegex(CommandError,"cancel or finish"):
            w.create_task("elena","Wait",{"kind":"wait","minutes":5})
        started = {}
        def finished():
            if a.get("working") and "work" not in started:
                started["work"] = w.time
            return task["status"]=="completed"
        advance(w,finished,600)
        evidence = [event_row(w,seq) for seq in task["evidence"]]
        self.assertEqual([e["kind"] for e in evidence],["community_harvest"])
        self.assertEqual(harvest_events(w),evidence)
        self.assertLessEqual(distance(a,w.bed_goal("elena")),.8)
        self.assertGreaterEqual(evidence[0]["time"]-started["work"],30)
        self.assertEqual([i["kind"] for i in a["inventory"]],["vegetables"])
        payload = evidence[0]["payload"]
        self.assertEqual((evidence[0]["actor"],payload["task"],payload["item"]["id"],payload["site"]),
                         ("elena",task["id"],a["inventory"][0]["id"],w.bed_goal("elena")))
        self.assertNotIn("elena",w.community["beds"])
        self.assertEqual((w.community["seeds"],w.community["supplies"],a.get("credits",25)),resources)
        self.assertEqual(json.dumps({"bed":w.community["beds"]["noah"],"inventory":w.agents["noah"]["inventory"]}),others)
        completion = w.storage.db.execute("SELECT payload FROM events WHERE kind='dialogue' AND actor='elena'").fetchall()
        self.assertEqual([json.loads(r["payload"])["recipients"] for r in completion],[[]])

    def test_bed_state_and_maturity_boundary_choose_action(self):
        w = self.world
        # Each tick advances simulated time by 3 s before the selector runs.
        ripe(w,"maya",3)
        ripe(w,"elena",3.5)
        plant(w,"jun")
        for aid in ("maya","elena","jun","noah"):
            w.agents[aid]["next_decision"] = w.time
        w.tick(.5)
        self.assertEqual(w.time,w.community["beds"]["maya"]["ready_at"])
        self.assertEqual([t["kind"] for t in autonomous(w,"maya")],["harvest"])
        self.assertEqual([t["kind"] for t in autonomous(w,"jun")],["water"])
        self.assertEqual(autonomous(w,"elena")+autonomous(w,"noah"),[])
        self.assertEqual({j["agent"] for j in w.jobs if j["method"]=="decide"},{"elena","noah"})
        self.assertEqual((len(w.community["beds"]),w.community["seeds"]),(3,12))
        # Without a garden on the map, a ripe bed falls back to the routine decision.
        ripe(w,"samir")
        garden = w.layout["places"].pop("garden")
        try:
            self.assertFalse(w.start_autonomous_task(w.agents["samir"]))
        finally:
            w.layout["places"]["garden"] = garden

    def test_ripe_crop_respects_existing_precedence(self):
        w = self.world
        for aid in ("samir","noah","maya","jun","elena"):
            ripe(w,aid)
        player = w.create_task("samir","Wait",{"kind":"wait","minutes":30})
        self.assertFalse(w.start_autonomous_task(w.agents["samir"]))
        w.command({"id":"pause-samir","kind":"suspend_task","task":player["id"]})
        self.assertFalse(w.start_autonomous_task(w.agents["samir"]))
        w.pending_interaction = {"kind":"task","agent":"noah","text":"Visit the park","repath":0,"expires":w.time+600}
        self.assertFalse(w.start_autonomous_task(w.agents["noah"]))
        w.pending_interaction = None
        a = w.agents["maya"]
        for key,value,restore in (("thinking",True,False),("conversation","chat_x",None),("routine",{"place":"park"},None)):
            a[key] = value
            self.assertFalse(w.start_autonomous_task(a),key)
            a[key] = restore
        for need,value in (("energy",29.9),("hunger",70.1)):
            previous = a["needs"][need]
            a["needs"][need] = value
            self.assertFalse(w.start_autonomous_task(a),need)
            a["needs"][need] = previous
        for offset in (600,-600):
            w.appointments = {"ap":{"id":"ap","host":"noah","place":"plaza","at":w.time+offset,"guests":["maya"],"invited":["maya"],
                                    "accepted":["noah","maya"],"declined":[],"attended":[],"status":"scheduled","task":""}}
            self.assertFalse(w.start_autonomous_task(a),offset)
        w.appointments = {}
        a["autonomy_deferred_until"] = w.time+1
        self.assertFalse(w.start_autonomous_task(a))
        a.pop("autonomy_deferred_until")
        self.assertEqual(autonomous(w,"samir")+autonomous(w,"noah")+autonomous(w,"maya"),[])
        # A due reflection is handled before the decision branch.
        a["next_reflect"] = a["next_decision"] = w.time
        with patch.object(w,"reflection_due",return_value=True):
            w.tick(.5)
        self.assertEqual(autonomous(w,"maya"),[])
        self.assertTrue(any(j["agent"]=="maya" and j["method"]=="reflect" for j in w.jobs))
        a["next_reflect"] = a["next_decision"] = 10**10
        advance(w,lambda:not a["thinking"],20)
        # A crop that ripens mid-routine waits for the routine to finish.
        jun = w.agents["jun"]
        w.community["beds"]["jun"]["ready_at"] = w.time+6
        jun["routine"] = {"place":"park","activity":"Relaxing","duration":6000,"arrived":None}
        jun["next_decision"] = w.time
        for _ in range(20):
            w.tick(.5)
        self.assertEqual((autonomous(w,"jun"),jun["routine"]["activity"]),([],"Relaxing"))
        # A running player task is never replaced by a routine-time harvest.
        elena = w.create_task("elena","Wait",{"kind":"wait","minutes":30})
        w.agents["elena"]["next_decision"] = w.time
        for _ in range(20):
            w.tick(.5)
        self.assertEqual((w.agents["elena"]["task"],elena["status"]),(elena["id"],"running"))
        self.assertEqual(autonomous(w,"elena"),[])
        self.assertEqual(harvest_events(w),[])
        self.assertEqual(len(w.community["beds"]),5)
        # Just outside the appointment window and at the need thresholds, harvesting starts.
        a["needs"].update(energy=30.0,hunger=70.0)
        w.appointments = {"ap":{"id":"ap","host":"noah","place":"plaza","at":w.time+601,"guests":["maya"],"invited":["maya"],
                                "accepted":["noah","maya"],"declined":[],"attended":[],"status":"scheduled","task":""}}
        self.assertTrue(w.start_autonomous_task(a))
        self.assertEqual([t["kind"] for t in autonomous(w,"maya")],["harvest"])

    def test_repeated_due_ticks_and_resume_keep_one_harvest(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/"town.db")
            w = World(path,cognition=Cognition("demo"),restore=False)
            quiet(w)
            ripe(w,"elena")
            task = dispatch(w,"elena")
            def working():
                w.agents["elena"]["next_decision"] = w.time
                return bool(w.agents["elena"].get("working"))
            advance(w,working,400)
            self.assertEqual((len(autonomous(w,"elena")),w.agents["elena"]["inventory"]),(1,[]))
            w.close()
            restored = World(path,cognition=Cognition("demo"))
            try:
                quiet(restored)
                a = restored.agents["elena"]
                tasks = autonomous(restored,"elena")
                self.assertEqual([(t["id"],t["kind"],t["origin"]) for t in tasks],[(task["id"],"harvest","autonomous")])
                self.assertEqual(a["task"],task["id"])
                self.assertIn("elena",restored.community["beds"])
                resumed = tasks[0]
                def done():
                    a["next_decision"] = min(a["next_decision"],restored.time)
                    return resumed["status"]=="completed"
                advance(restored,done,600)
                for _ in range(20):
                    restored.tick(.5)
                    a["next_decision"] = min(a["next_decision"],restored.time)
                self.assertEqual(len(autonomous(restored,"elena")),1)
                item = a["inventory"][0]["id"]
                self.assertEqual([i["kind"] for i in a["inventory"]],["vegetables"])
            finally:
                restored.close()
            again = World(path,cognition=Cognition("demo"))
            try:
                quiet(again)
                a = again.agents["elena"]
                self.assertNotIn("elena",again.community["beds"])
                self.assertEqual([i["id"] for i in a["inventory"]],[item])
                evidence = harvest_events(again)
                self.assertEqual([(e["payload"]["task"],e["payload"]["item"]["id"]) for e in evidence],[(task["id"],item)])
                self.assertEqual(again.tasks[task["id"]]["evidence"],[evidence[0]["id"]])
                for _ in range(20):
                    a["next_decision"] = min(a["next_decision"],again.time)
                    again.tick(.5)
                self.assertEqual((len(autonomous(again,"elena")),len(a["inventory"]),len(harvest_events(again))),(1,1,1))
            finally:
                again.close()

    def test_cancelled_active_and_paused_harvests_share_deferral_across_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/"town.db")
            w = World(path,cognition=Cognition("demo"),restore=False)
            quiet(w)
            ripe(w,"elena")
            ripe(w,"jun")
            active = dispatch(w,"elena")
            advance(w,lambda:bool(w.agents["elena"].get("working")),400)
            w.command({"id":"cancel-active","kind":"cancel","task":active["id"]})
            active_at = w.time
            paused = dispatch(w,"jun")
            w.command({"id":"pause-harvest","kind":"suspend_task","task":paused["id"]})
            self.assertEqual(paused["status"],"paused")
            w.command({"id":"cancel-paused","kind":"cancel","task":paused["id"]})
            paused_at = w.time
            self.assertEqual((active["status"],paused["status"]),("cancelled","cancelled"))
            self.assertEqual(w.agents["elena"]["autonomy_deferred_until"],active_at+600)
            self.assertEqual(w.agents["jun"]["autonomy_deferred_until"],paused_at+600)
            # The deferral is resident-wide: an unwatered bed is not watered either.
            w.community["beds"]["jun"]["ready_at"] = None
            self.assertFalse(w.start_autonomous_task(w.agents["jun"]))
            w.community["beds"]["jun"]["ready_at"] = w.time
            w.close()
            restored = World(path,cognition=Cognition("demo"))
            try:
                quiet(restored)
                residents = [restored.agents[aid] for aid in ("elena","jun")]
                self.assertEqual([r["autonomy_deferred_until"] for r in residents],[active_at+600,paused_at+600])
                while restored.time < active_at+590:
                    for r in residents:
                        r["next_decision"] = restored.time
                    restored.tick(.5)
                    for r in residents:
                        r["routine"] = None
                    self.assertEqual(len(autonomous(restored,"elena")+autonomous(restored,"jun")),2)
                self.assertEqual(harvest_events(restored),[])
                self.assertEqual([r["inventory"] for r in residents],[[],[]])
                self.assertTrue(all(aid in restored.community["beds"] for aid in ("elena","jun")))
                def retried():
                    for r in residents:
                        r["next_decision"] = min(r["next_decision"],restored.time)
                        r["routine"] = None
                    return len(autonomous(restored,"elena")) == 2
                advance(restored,retried,20)
                self.assertGreaterEqual(restored.time,active_at+600)
                retry = restored.tasks[restored.agents["elena"]["task"]]
                self.assertEqual((retry["kind"],retry["origin"]),("harvest","autonomous"))
                self.assertEqual(restored.tasks[active["id"]]["status"],"cancelled")
                self.assertEqual(restored.tasks[paused["id"]]["status"],"cancelled")
                advance(restored,lambda:retry["status"]=="completed",600)
                self.assertEqual([e["payload"]["task"] for e in harvest_events(restored,"elena")],[retry["id"]])
            finally:
                restored.close()

    def test_player_can_request_harvest_during_deferral(self):
        w = self.world
        ripe(w,"elena")
        cancelled = dispatch(w,"elena")
        w.command({"id":"cancel-harvest","kind":"cancel","task":cancelled["id"]})
        w.command({"id":"player-harvest","kind":"task","agent":"elena","text":"Harvest vegetables"})
        advance(w,lambda:bool(w.agents["elena"]["task"]),400)
        task = w.tasks[w.agents["elena"]["task"]]
        self.assertLess(w.time,w.agents["elena"]["autonomy_deferred_until"])
        self.assertEqual((task["kind"],task["origin"]),("harvest","player"))
        advance(w,lambda:task["status"]=="completed",600)
        self.assertEqual([e["payload"]["task"] for e in harvest_events(w)],[task["id"]])
        self.assertEqual(len(w.agents["elena"]["inventory"]),1)
        self.assertEqual(cancelled["status"],"cancelled")

    def test_unripe_missing_or_unreachable_crop_blocks_without_harvest(self):
        w = self.world
        for aid in ("elena","maya","jun"):
            ripe(w,aid)
        unripe = dispatch(w,"elena")
        w.community["beds"]["elena"]["ready_at"] = w.time+10000
        missing = dispatch(w,"maya")
        w.community["beds"].pop("maya")
        advance(w,lambda:unripe["status"]=="blocked" and missing["status"]=="blocked",600)
        self.assertEqual(unripe["blocker"],"Waiting for the watered vegetables to ripen")
        self.assertEqual(missing["blocker"],"Plant vegetables first")
        jun = w.agents["jun"]
        self.assertGreater(distance(jun,w.bed_goal("jun")),.8)
        with patch.object(w,"pathfind",return_value=None):
            blocked = dispatch(w,"jun")
            advance(w,lambda:blocked["status"]=="blocked",20)
        self.assertEqual(blocked["blocker"],"The work site is blocked; retrying")
        for _ in range(30):
            w.tick(.5)
        self.assertEqual(harvest_events(w),[])
        self.assertEqual([w.agents[aid]["inventory"] for aid in ("elena","maya","jun")],[[],[],[]])
        self.assertEqual(sorted(w.community["beds"]),["elena","jun"])
        self.assertEqual((unripe["evidence"],missing["evidence"],blocked["evidence"]),([],[],[]))
        # Once the site is reachable again, the existing retry finishes the harvest.
        advance(w,lambda:blocked["status"]=="completed",600)
        self.assertEqual([e["payload"]["task"] for e in harvest_events(w)],[blocked["id"]])
        self.assertNotIn("jun",w.community["beds"])

    def test_resident_waters_then_harvests_crop_without_replanting(self):
        w = self.world
        a = w.agents["elena"]
        plant(w,"elena")
        def harvested():
            a["next_decision"] = min(a["next_decision"],w.time)
            a["routine"] = None
            return any(t["kind"]=="harvest" and t["status"]=="completed" for t in autonomous(w,"elena"))
        advance(w,harvested,1000)
        water,harvest = sorted(autonomous(w,"elena"),key=lambda t:t["created"])
        self.assertEqual([(t["kind"],t["status"]) for t in (water,harvest)],[("water","completed"),("harvest","completed")])
        watered_at = event_row(w,water["evidence"][0])["time"]
        self.assertGreaterEqual(harvest["created"],watered_at+180)
        for _ in range(40):
            w.tick(.5)
            a["next_decision"] = min(a["next_decision"],w.time)
            a["routine"] = None
        self.assertEqual(len(autonomous(w,"elena")),2)
        self.assertEqual([i["kind"] for i in a["inventory"]],["vegetables"])
        self.assertEqual([e["payload"]["item"]["id"] for e in harvest_events(w)],[a["inventory"][0]["id"]])
        self.assertEqual((w.community["beds"],w.community["seeds"]),({},12))
