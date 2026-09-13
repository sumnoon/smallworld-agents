import math
import random
import unittest

from server.model import Cognition
from server.world import World, distance
from test_simulation import quiet


def reference_visible(world, a, b, radius=4):
    """The original per-building sight-line check, kept as an oracle for the cached version."""
    if distance(a, b) > radius:
        return False
    steps = max(1, math.ceil(distance(a, b) * 4))
    for i in range(1, steps):
        x = round(a["x"] + (b["x"] - a["x"]) * i / steps)
        y = round(a["y"] + (b["y"] - a["y"]) * i / steps)
        for building in world.layout["buildings"]:
            if building["x"] - 2 <= x <= building["x"] + 1 and building["y"] - 2 <= y <= building["y"] + 1:
                return False
        for landmark in world.layout.get("landmarks", []):
            x0, y0, x1, y1 = landmark["footprint"]
            if landmark.get("blocks_view") and x0 <= x <= x1 and y0 <= y <= y1:
                return False
    return True


class TickPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.world = World(cognition=Cognition("demo"), restore=False)
        quiet(self.world)

    def tearDown(self):
        self.world.close()

    def test_cached_sight_lines_match_original_geometry_check(self):
        w = self.world
        rng = random.Random(7)
        size = w.layout["size"]
        for _ in range(4000):
            a = {"x": rng.uniform(0, size - 1), "y": rng.uniform(0, size - 1), "room": ""}
            b = {"x": a["x"] + rng.uniform(-4, 4), "y": a["y"] + rng.uniform(-4, 4), "room": ""}
            self.assertEqual(w.visible(a, b), reference_visible(w, a, b), (a, b))

    def test_sight_line_cache_follows_replaced_layout(self):
        w = self.world
        a, b = {"x": 1., "y": 1., "room": ""}, {"x": 4., "y": 1., "room": ""}
        w.layout = {**w.layout, "buildings": [], "landmarks": []}
        self.assertTrue(w.visible(a, b))
        w.layout = {**w.layout, "buildings": [{"x": 3, "y": 2, "index": 0}]}
        self.assertFalse(w.visible(a, b))

    def test_rollback_restores_nested_resident_state(self):
        w = self.world
        maya = w.agents["maya"]
        maya["known_positions"]["noah"] = {"x": 1, "y": 2, "time": 0, "room": ""}
        with self.assertRaises(RuntimeError):
            with w.atomic():
                w.agents["maya"]["known_positions"]["noah"]["x"] = 99
                w.agents["maya"]["inventory"].append({"id": "ghost", "kind": "coffee"})
                raise RuntimeError("rollback")
        self.assertEqual(w.agents["maya"]["known_positions"]["noah"]["x"], 1)
        self.assertEqual(w.agents["maya"]["inventory"], [])

    def test_retrieval_decodes_evidence_for_returned_memories(self):
        w = self.world
        mid = w.storage.memory("jun", "observation", "Sketching the violet fountain", w.time, 10, [{"event": 5}])
        found = w.storage.retrieve("jun", "violet fountain", w.time)
        self.assertEqual(found[0]["id"], mid)
        self.assertEqual(found[0]["evidence"], [{"event": 5}])
        self.assertIn("retrieval_score", found[0])

    def test_reflection_importance_sum_matches_python_filter(self):
        w = self.world
        since = w.time - 50
        for i, (kind, offset, importance) in enumerate([("observation", -100, 4), ("conversation", 10, 6), ("reflection", 20, 7),
                                                        ("identity", 30, 9), ("task", 40, 9), ("observation", 60, 3)]):
            w.storage.memory("tester", kind, f"Memory {i}", w.time + offset, importance)
        expected = sum(m["importance"] for m in w.storage.memories("tester", 120)
                       if m["created"] > since and m["kind"] not in ("identity", "reflection"))
        self.assertEqual(w.storage.importance_since("tester", since), expected)
        self.assertEqual(expected, 18)
        self.assertEqual(w.storage.importance_since("nobody", since), 0)

    def test_long_finished_tasks_move_to_archive(self):
        w = self.world
        old = w.time - 8000
        base = {"agent": "maya", "request": "Old errand", "kind": "wait", "steps": [], "step": 0, "evidence": [], "blocker": ""}
        w.tasks["task_child"] = {**base, "id": "task_child", "status": "completed", "finished_at": old, "parent": "task_parent"}
        w.tasks["task_parent"] = {**base, "id": "task_parent", "status": "paused"}
        ids = []
        for i in range(40):
            tid = f"task_old{i:02}"
            w.tasks[tid] = {**base, "id": tid, "status": "completed", "finished_at": old}
            ids.append(tid)
        w.next_archive = 0
        w.tick(.5)
        self.assertEqual(len(w.tasks), 32)
        self.assertIn("task_child", w.tasks)
        self.assertIn("task_parent", w.tasks)
        self.assertTrue(all(tid not in w.tasks for tid in ids[:10]))
        self.assertTrue(all(tid in w.tasks for tid in ids[10:]))
        self.assertEqual(w.storage.archived_task(ids[0])["request"], "Old errand")

    def test_recently_finished_tasks_are_not_archived(self):
        w = self.world
        task = w.create_task("maya", "Wait", {"kind": "wait", "minutes": 1})
        task.update(status="completed")
        w.agents["maya"]["task"] = None
        for i in range(40):
            w.tasks[f"filler{i}"] = {**task, "id": f"filler{i}"}
        w.next_archive = 0
        w.tick(.5)
        self.assertIn(task["id"], w.tasks)
        self.assertEqual(task["finished_at"], w.time)


if __name__ == "__main__":
    unittest.main()
