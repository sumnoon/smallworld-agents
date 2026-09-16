import importlib.util
import io
import json
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from server.model import Cognition
from server.storage import Storage
from server.world import World

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluate_gardening", ROOT / "tools" / "evaluate-gardening.py")
gardening = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gardening)


def quiet_world():
    w = World(cognition=Cognition("demo"), restore=False)
    w.next_social = 10**10
    for a in w.agents.values():
        a["next_decision"] = a["next_reflect"] = 10**10
    return w


def add_task(w, aid, kind, status="accepted", origin="autonomous"):
    tid = "task_" + uuid.uuid4().hex[:10]
    w.tasks[tid] = {"id": tid, "agent": aid, "kind": kind, "origin": origin, "status": status, "created": w.time,
                    "deadline": w.time + 14400, "evidence": [], "blocker": "", "retry_at": 0, "steps": [], "step": 0}
    w.event(aid, "task_accepted", "fixture", {"task": tid, "origin": origin})
    return w.tasks[tid]


def finish_action(w, task):
    """Apply one gardening effect the way the engine does, with its action and outcome events."""
    aid, kind, item = task["agent"], task["kind"], None
    if kind == "plant":
        w.community["seeds"] -= 1
        w.community["beds"][aid] = {**w.bed_goal(aid), "planted": w.time, "ready_at": None}
    elif kind == "water":
        w.community["beds"][aid]["ready_at"] = w.time + 180
    else:
        w.community["beds"].pop(aid)
        item = {"id": uuid.uuid4().hex, "kind": "vegetables"}
        w.agents[aid]["inventory"].append(item)
    task["evidence"].append(w.event(aid, "community_" + kind, "fixture", {"task": task["id"], "item": item, "site": w.bed_goal(aid)}))
    task.update(status="completed", completed=w.time)
    w.event(aid, "task_completed", "fixture", {"task": task["id"], "evidence": task["evidence"]})
    return item


def checks(report):
    return {v["check"] for v in report["invariants"]["violations"]}


class EventAndArchiveTests(unittest.TestCase):
    def setUp(self):
        self.world = quiet_world()

    def tearDown(self):
        self.world.close()

    def test_event_cursor_reads_every_row_beyond_latest_window(self):
        storage = Storage(":memory:")
        try:
            for i in range(250):
                storage.event(i, "maya", "task_blocked", "Maya: No seeds remain", {"task": "t"})
            self.assertEqual(len(storage.events(35)), 35)
            rows = gardening.read_events(storage)
            self.assertEqual([r["id"] for r in rows], list(range(1, 251)))
            self.assertEqual([r["id"] for r in gardening.read_events(storage, 200)], list(range(201, 251)))
            self.assertEqual(rows[0]["payload"], {"task": "t"})
        finally:
            storage.close()

    def test_totals_include_archived_and_unseen_tasks_once_beyond_event_window(self):
        w = self.world
        monitor = gardening.GardeningMonitor(w)
        planted = add_task(w, "elena", "plant")
        monitor.after_tick()
        finish_action(w, planted)
        # A task created, finished and archived between observations is found through its accepted event.
        w.time += 1
        unseen = add_task(w, "maya", "plant")
        finish_action(w, unseen)
        for i in range(300):
            w.event("noah", "activity", "Noah is walking.")
        w.storage.archive_tasks([planted, unseen])
        del w.tasks[planted["id"]], w.tasks[unseen["id"]]
        w.time += 60
        watered = add_task(w, "elena", "water")
        finish_action(w, watered)
        monitor.before_tick()
        monitor.after_tick()
        report = monitor.finish()
        self.assertTrue(report["invariants"]["passed"], report["invariants"])
        self.assertEqual(report["tasks"]["resolved_from"], {"archive": 2, "live": 1})
        self.assertEqual(report["tasks"]["accepted"], {"plant": {"autonomous": 2}, "water": {"autonomous": 1}})
        self.assertEqual(report["tasks"]["terminal"], {"plant": {"autonomous": {"completed": 2}}, "water": {"autonomous": {"completed": 1}}})
        self.assertEqual(report["tasks"]["unique_tasks"], 3)
        self.assertGreater(report["events"]["total"], 300)
        self.assertEqual(report["events"]["by_kind"]["activity"], 300)
        self.assertEqual([(a["task"], a["kind"]) for a in report["successful_actions"]],
                         [(planted["id"], "plant"), (unseen["id"], "plant"), (watered["id"], "water")])
        self.assertEqual([a["event"] for a in report["successful_actions"]], [planted["evidence"][0], unseen["evidence"][0], watered["evidence"][0]])
        self.assertEqual((report["seeds"]["initial"], report["seeds"]["final"], report["seeds"]["plant_events"]), (12, 10, 2))
        self.assertEqual(report["beds"]["final_by_state"], {"growing": 1, "planted_unwatered": 1})
        self.assertEqual((report["residents"]["planting"], report["residents"]["watering_count"]), (["elena", "maya"], 1))
        self.assertEqual(report["autonomous_cycles"]["count"], 0)

    def test_plant_water_harvest_cycle_links_evidence_and_vegetables(self):
        w = self.world
        monitor = gardening.GardeningMonitor(w)
        tasks = []
        for kind in ("plant", "water", "harvest"):
            tasks.append(add_task(w, "jun", kind))
            monitor.after_tick()
            item = finish_action(w, tasks[-1])
            w.time += 200
            monitor.after_tick()
        report = monitor.finish()
        self.assertTrue(report["invariants"]["passed"], report["invariants"])
        cycle = report["autonomous_cycles"]["cycles"]
        self.assertEqual([(c["agent"], c["tasks"], c["vegetables"]) for c in cycle], [("jun", [t["id"] for t in tasks], item["id"])])
        self.assertEqual(report["vegetables"], {"initial": 0, "final": 1, "by_owner": {"jun": 1}})
        self.assertEqual(gardening.exit_code(report), 0)


class BlockingTests(unittest.TestCase):
    def setUp(self):
        self.world = quiet_world()

    def tearDown(self):
        self.world.close()

    def test_unique_blocked_tasks_events_and_sampled_minutes_are_distinct(self):
        w = self.world
        monitor = gardening.GardeningMonitor(w)
        starved = add_task(w, "jun", "plant")
        unreachable = add_task(w, "maya", "plant")
        first_block = None
        for tick in range(10):
            w.time += 3
            starved["status"] = "blocked"
            if tick % 4 == 0:
                seq = w.event("jun", "task_blocked", "Jun: No seeds remain", {"task": starved["id"]})
                first_block = first_block or w.time
            unreachable["status"] = "blocked" if tick < 4 else "running"
            if tick in (0, 2):
                w.event("maya", "task_blocked", "Maya: The work site is blocked; retrying", {"task": unreachable["id"]})
            monitor.before_tick()
            monitor.after_tick()
        report = monitor.finish()
        blocking = report["blocking"]
        self.assertTrue(report["invariants"]["passed"], report["invariants"])
        self.assertEqual((blocking["task_blocked_events_all"], blocking["task_blocked_events_gardening"]), (5, 5))
        self.assertEqual((blocking["unique_blocked_tasks"], blocking["unique_blocked_planting_tasks"]), ({"plant": 2}, 2))
        self.assertEqual(blocking["blockers_by_reason"], {"No seeds remain": {"events": 3, "unique_tasks": 1},
                                                          "The work site is blocked; retrying": {"events": 2, "unique_tasks": 1}})
        # Ten 3 s samples for one task and four for the other: 42 resident-seconds.
        self.assertEqual(blocking["sampled_blocked_resident_minutes"], 0.7)
        self.assertEqual((blocking["peak_concurrently_blocked_tasks"]["count"], len(blocking["peak_concurrently_blocked_tasks"]["tasks"])), (2, 2))
        rows = {r["task"]: r for r in blocking["affected_tasks"]}
        self.assertEqual((rows[starved["id"]]["task_blocked_events"], rows[starved["id"]]["sampled_blocked_minutes"]), (3, 0.5))
        self.assertEqual((rows[unreachable["id"]]["task_blocked_events"], rows[unreachable["id"]]["sampled_blocked_minutes"]), (2, 0.2))
        self.assertEqual((rows[starved["id"]]["first_blocked"], rows[starved["id"]]["seed_starved"], rows[unreachable["id"]]["seed_starved"]), (first_block, True, False))
        self.assertEqual(blocking["seed_contention"]["seed_starved_planting_tasks"], 1)
        self.assertTrue(all(r["censored"] and r["terminal_time"] is None for r in rows.values()))
        self.assertEqual([t["observed_age_minutes"] for t in report["still_open_tasks"]], [0.5, 0.5])

    def test_no_contention_is_reported_explicitly(self):
        report = gardening.GardeningMonitor(self.world).finish()
        self.assertEqual(report["blocking"]["seed_contention"]["observed"], False)
        self.assertIn("No planting task", report["blocking"]["seed_contention"]["note"])
        self.assertEqual(gardening.exit_code(report), gardening.EXIT_NO_CYCLE)
        self.assertEqual(report["blocking"]["peak_concurrently_blocked_tasks"]["count"], 0)

    def test_seed_starved_task_fails_on_first_tick_past_deadline(self):
        w = self.world
        w.community["seeds"] = 0
        a = w.agents["elena"]
        goal = w.bed_goal("elena")
        a.update(x=float(goal["x"]), y=float(goal["y"]))
        # Player planting still waits for seeds; autonomous planting now fails as soon as seeds run out.
        task = w.create_task("elena", "Plant vegetables", {"kind": "plant"})
        task["deadline"] = w.time + 9
        monitor = gardening.GardeningMonitor(w)
        monitor.after_tick()
        for _ in range(6):
            monitor.before_tick()
            w.tick(.5)
            monitor.after_tick()
        report = monitor.finish()
        self.assertTrue(report["invariants"]["passed"], report["invariants"])
        enforcement = report["blocking"]["deadline_enforcement"]
        self.assertEqual((enforcement["seed_starved_tasks_past_deadline"], enforcement["released_on_first_processed_tick"]), (1, 1))
        check = enforcement["checks"][0]
        self.assertEqual((check["task"], check["terminal_status"], check["released"], check["lag_seconds"]), (task["id"], "failed", True, 3.0))
        self.assertEqual(check["blocker"], "Community task deadline elapsed")
        failed = w.storage.db.execute("SELECT id FROM events WHERE kind='task_failed'").fetchone()["id"]
        self.assertEqual((check["enforced"], check["failure_event"], check["outcome_events"]), (True, failed, [failed]))
        self.assertEqual(enforcement["failed_through_deadline"], 1)
        self.assertEqual((a["task"], report["tasks"]["terminal"]), (None, {"plant": {"player": {"failed": 1}}}))

    def test_cancelled_timeout_is_not_deadline_enforcement(self):
        w = self.world
        w.community["seeds"] = 0
        a = w.agents["elena"]
        goal = w.bed_goal("elena")
        a.update(x=float(goal["x"]), y=float(goal["y"]))
        task = w.create_task("elena", "Plant vegetables", {"kind": "plant"})
        task["deadline"] = w.time + 9
        monitor = gardening.GardeningMonitor(w)
        monitor.after_tick()
        def cancel(resident, cancelled, reason):
            # A consistent cancellation with its own event and no effects, but not the deadline failure path.
            cancelled["status"] = "cancelled"
            w.event(resident["id"], "task_cancelled", "Cancelled instead of failing", {"task": cancelled["id"]})
            w._interrupt(resident)
            resident["task"] = None
        with patch.object(w, "fail_community", side_effect=cancel):
            for _ in range(6):
                monitor.before_tick()
                w.tick(.5)
                monitor.after_tick()
        report = monitor.finish()
        self.assertEqual((task["status"], a["task"]), ("cancelled", None))
        cancelled = w.storage.db.execute("SELECT id FROM events WHERE kind='task_cancelled'").fetchone()["id"]
        self.assertEqual(checks(report), {"deadline_wrong_outcome"})
        violation = report["invariants"]["violations"][0]
        self.assertEqual((violation["tasks"], violation["events"]), ([task["id"]], [cancelled]))
        enforcement = report["blocking"]["deadline_enforcement"]
        self.assertEqual((enforcement["seed_starved_tasks_past_deadline"], enforcement["failed_through_deadline"], enforcement["released_on_first_processed_tick"]), (1, 0, 0))
        self.assertEqual((enforcement["checks"][0]["enforced"], enforcement["checks"][0]["failure_event"]), (False, None))
        self.assertEqual(gardening.exit_code(report), gardening.EXIT_VIOLATION)

    def test_deadline_left_unenforced_is_a_violation(self):
        w = self.world
        w.community["seeds"] = 0
        task = w.create_task("elena", "Plant vegetables", {"kind": "plant"})
        task["deadline"] = w.time + 3
        monitor = gardening.GardeningMonitor(w)
        monitor.after_tick()
        with patch.object(w, "fail_community"):
            for _ in range(3):
                monitor.before_tick()
                w.tick(.5)
                monitor.after_tick()
        report = monitor.finish()
        violation = next(v for v in report["invariants"]["violations"] if v["check"] == "deadline_not_enforced")
        self.assertEqual((violation["tasks"], violation["occurrences"]), ([task["id"]], 2))
        self.assertEqual(gardening.exit_code(report), gardening.EXIT_VIOLATION)


class InconsistencyTests(unittest.TestCase):
    def setUp(self):
        self.world = quiet_world()
        self.monitor = gardening.GardeningMonitor(self.world)

    def tearDown(self):
        self.world.close()

    def test_seed_change_without_plant_event_fails(self):
        self.world.community["seeds"] -= 1
        self.monitor.after_tick()
        report = self.monitor.finish()
        self.assertIn("seed_reconciliation", checks(report))
        self.assertEqual(gardening.exit_code(report), gardening.EXIT_VIOLATION)

    def test_transient_unearned_vegetable_stays_a_violation(self):
        w = self.world
        a = w.agents["maya"]
        a["inventory"].append({"id": "unearned-veg", "kind": "vegetables"})
        w.time += 3
        self.monitor.after_tick()
        a["inventory"].pop()
        w.time += 3
        self.monitor.after_tick()
        report = self.monitor.finish()
        self.assertEqual(checks(report), {"vegetable_reconciliation"})
        detail = report["invariants"]["violations"][0]["detail"]
        self.assertIn("unearned-veg", detail)
        self.assertIn("maya", detail)
        self.assertEqual(report["vegetables"]["final"], 0)
        self.assertEqual(gardening.exit_code(report), gardening.EXIT_VIOLATION)

    def test_action_event_before_its_task_completes_stays_a_violation(self):
        w = self.world
        task = add_task(w, "jun", "plant")
        early = w.event("jun", "community_plant", "early", {"task": task["id"], "item": None, "site": w.bed_goal("jun")})
        w.community["seeds"] -= 1
        w.community["beds"]["jun"] = {**w.bed_goal("jun"), "planted": w.time, "ready_at": None}
        self.monitor.after_tick()
        # Repaired afterwards: the same event becomes the completed task's evidence, which passes the end-of-run check.
        task["evidence"].append(early)
        task["status"] = "completed"
        w.event("jun", "task_completed", "fixture", {"task": task["id"], "evidence": [early]})
        self.monitor.after_tick()
        report = self.monitor.finish()
        self.assertEqual(checks(report), {"action_event_unverified"})
        violation = report["invariants"]["violations"][0]
        self.assertEqual((violation["tasks"], violation["events"]), ([task["id"]], [early]))
        self.assertEqual(gardening.exit_code(report), gardening.EXIT_VIOLATION)

    def test_duplicate_action_event_is_reported_with_ids(self):
        w = self.world
        task = add_task(w, "maya", "plant")
        finish_action(w, task)
        extra = w.event("maya", "community_plant", "duplicate", {"task": task["id"], "item": None, "site": w.bed_goal("maya")})
        report = self.monitor.finish()
        violation = next(v for v in report["invariants"]["violations"] if v["check"] == "action_evidence_mismatch")
        self.assertEqual((violation["tasks"], violation["events"]), ([task["id"]], [task["evidence"][0], extra]))
        self.assertIn("seed_reconciliation", checks(report))

    def test_unsuccessful_planting_with_effects_fails(self):
        w = self.world
        task = add_task(w, "noah", "plant")
        finish_action(w, task)
        task["status"] = "failed"
        report = self.monitor.finish()
        self.assertIn("effect_without_completion", checks(report))
        self.assertIn("outcome_event_mismatch", checks(report))

    def test_overlapping_autonomous_tasks_fail(self):
        w = self.world
        first, second = add_task(w, "jun", "plant"), add_task(w, "jun", "water")
        self.monitor.after_tick()
        violation = next(v for v in self.monitor.finish()["invariants"]["violations"] if v["check"] == "overlapping_autonomous_tasks")
        self.assertEqual(sorted(violation["tasks"]), sorted([first["id"], second["id"]]))

    def test_repeated_or_missing_harvest_items_fail(self):
        w = self.world
        tasks = []
        for kind in ("plant", "water", "harvest"):
            tasks.append(add_task(w, "samir", kind))
            item = finish_action(w, tasks[-1])
        w.agents["samir"]["inventory"].append(dict(item))
        report = self.monitor.finish()
        self.assertEqual(checks(report), {"vegetable_reconciliation"})
        w.event("samir", "community_harvest", "forged", {"task": tasks[-1]["id"], "item": item, "site": w.bed_goal("samir")})
        again = gardening.GardeningMonitor(w)
        again.initial["seeds"] = 12
        self.assertTrue({"harvest_item_not_unique", "harvest_without_bed", "action_evidence_mismatch"} <= checks(again.finish()))


class RunTests(unittest.TestCase):
    def test_short_run_reports_workload_and_reconciles(self):
        report = gardening.run(population=5, ticks=300, seeds=2)
        self.assertTrue(report["invariants"]["passed"], report["invariants"])
        workload = report["workload"]
        self.assertEqual((workload["population"], workload["ticks"], workload["simulated_duration_seconds"]), (5, 300, 900.0))
        self.assertEqual((workload["time_step"]["simulated_seconds_per_tick"], workload["initial_resources"]["seeds"]), (3.0, 2))
        self.assertEqual(report["tasks"]["accepted"]["plant"], {"autonomous": 5})
        self.assertEqual((report["seeds"]["final"], report["seeds"]["plant_events"]), (0, 2))
        self.assertEqual((report["beds"]["final"] + report["beds"]["harvest_events"], report["vegetables"]["final"]), (2, report["beds"]["harvest_events"]))
        # The three residents who miss the two seeds fail within 15 minutes, far before their four-hour deadlines,
        # without waiting blocked for seeds. seed_contention only counts blocked tasks, so it is not observed here.
        self.assertEqual(report["tasks"]["terminal"]["plant"]["autonomous"], {"completed": 2, "failed": 3})
        self.assertNotIn("plant", report["tasks"]["open"])
        self.assertEqual(report["blocking"]["deadline_enforcement"]["tasks_observed_past_deadline"], 0)
        self.assertEqual(report["blocking"]["seed_contention"]["seed_starved_planting_tasks"], 0)
        self.assertNotIn("No seeds remain", report["blocking"]["blockers_by_reason"])
        self.assertFalse(any(r["kind"] == "plant" for r in report["still_open_tasks"]))
        self.assertIn("revision", report["source"])
        self.assertEqual(report["events"]["total"], sum(report["events"]["by_kind"].values()))

    def test_world_closes_on_failure_and_main_writes_nonzero_report(self):
        closed = []
        original = World.close
        def close(world):
            closed.append(world)
            original(world)
        with patch.object(gardening.World, "close", autospec=True, side_effect=close):
            with patch.object(gardening.World, "tick", side_effect=RuntimeError("tick failed")):
                with self.assertRaisesRegex(RuntimeError, "tick failed"):
                    gardening.run(population=5, ticks=3)
        self.assertEqual(len(closed), 1)
        failing = {"invariants": {"passed": False, "violation_count": 1, "violations": []}, "autonomous_cycles": {"count": 1}}
        with tempfile.TemporaryDirectory() as folder, patch.object(gardening, "run", return_value=failing) as run:
            path = Path(folder) / "out" / "report.json"
            with redirect_stdout(io.StringIO()) as stdout:
                code = gardening.main(["--population", "5", "--ticks", "10", "--output", str(path)])
            self.assertEqual(code, gardening.EXIT_VIOLATION)
            run.assert_called_once_with(5, 10, 12)
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(written, json.loads(stdout.getvalue()))
            self.assertTrue(written["command"].startswith("python tools/evaluate-gardening.py --population 5"))


if __name__ == "__main__":
    unittest.main()
