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
