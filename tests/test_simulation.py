import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

from server.app import SimulationHTTPServer
from server.model import Cognition, ModelError, CHAT_SCHEMA
from server.world import World, CommandError, distance


def quiet(world):
    world.next_social = 10**10
    for agent in world.agents.values():
        agent["next_decision"] = agent["next_reflect"] = 10**10
        agent["path"] = []
        agent["routine"] = None


def advance(world, predicate, maximum=600):
    for _ in range(maximum):
        world.tick(.5)
        if predicate():
            return
        if world.jobs:
            time.sleep(.001)
    raise AssertionError("Simulation did not reach the expected condition")


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.world = World(cognition=Cognition("demo"), restore=False)
        quiet(self.world)

    def tearDown(self):
        self.world.close()

    def task(self, **kwargs):
        spec = {"kind": "deliver", "recipient": "noah", "place": "", "item": "coffee", "minutes": 0, "reply": ""}
        spec.update(kwargs)
        return self.world.create_task("maya", "Bring coffee to Noah", spec)

    def test_delivery_requires_real_transfer_and_preserves_stock(self):
        task = self.task()
        self.assertEqual(len(self.world.agents["noah"]["inventory"]), 0)
        advance(self.world, lambda: task["status"] == "completed")
        self.assertEqual(self.world.stock["coffee"], 11)
        self.assertEqual(self.world.agents["noah"]["inventory"][0]["kind"], "coffee")
        self.assertEqual(self.world.agents["maya"]["inventory"], [])
        events = self.world.storage.events(200)
        transfer = [e for e in events if e["kind"] == "transfer"]
        self.assertEqual(len(transfer), 1)
        self.assertIn(transfer[0]["id"], task["evidence"])
        self.assertLessEqual(distance(self.world.agents["maya"], self.world.agents["noah"]), 1.5)

    def test_closed_cafe_blocks_then_retries(self):
        self.world.cafe_open = False
        task = self.task()
        self.world.tick(.5)
        self.assertEqual(task["status"], "blocked")
        self.assertEqual(self.world.stock["coffee"], 12)
        self.world.command({"id": "open-cafe", "kind": "cafe", "open": True})
        advance(self.world, lambda: task["status"] == "completed")

    def test_cancellation_while_carrying_does_not_transfer_or_destroy_item(self):
        task = self.task()
        advance(self.world, lambda: task["step"] == 1)
        item = self.world.agents["maya"]["inventory"][0]["id"]
        self.world.command({"id": "cancel-1", "kind": "cancel", "task": task["id"]})
        quiet(self.world)
        for _ in range(20):
            self.world.tick(.5)
        self.assertEqual(task["status"], "cancelled")
        self.assertEqual(self.world.agents["maya"]["inventory"][0]["id"], item)
        self.assertFalse(self.world.agents["noah"]["inventory"])

    def test_pause_stops_clock_and_movement(self):
        self.world.command({"id": "move-1", "kind": "move", "x": 7, "y": 13})
        self.world.command({"id": "pause-1", "kind": "pause", "paused": True})
        before = self.world.snapshot()
        self.world.tick(1)
        after = self.world.snapshot()
        self.assertEqual(before["time"], after["time"])
        self.assertEqual(before["agents"], after["agents"])

    def test_paths_avoid_walls_and_diagonal_corner_cutting(self):
        actor = self.world.agents["visitor"]
        for goal in self.world.layout["places"].values():
            route = self.world.pathfind(actor, {"x": goal[0], "y": goal[1]})
            self.assertIsNotNone(route)
            previous = (round(actor["x"]), round(actor["y"]))
            for point in route:
                cell = (point["x"], point["y"])
                self.assertNotIn(cell, self.world.blocked)
                if cell[0] != previous[0] and cell[1] != previous[1]:
                    self.assertNotIn((cell[0], previous[1]), self.world.blocked)
                    self.assertNotIn((previous[0], cell[1]), self.world.blocked)
                previous = cell
        self.assertIsNone(self.world.pathfind(actor, {"x": 3, "y": 4}))

    def test_memories_stay_personal(self):
        self.world.storage.memory("jun", "observation", "Secret violet elephant", self.world.time, 10)
        self.assertFalse(any("violet" in m["text"] for m in self.world.storage.retrieve("maya", "violet elephant", self.world.time)))
        self.assertTrue(any("violet" in m["text"] for m in self.world.storage.retrieve("jun", "violet elephant", self.world.time)))

    def test_replanning_between_tiles_does_not_trap_player_behind_resident(self):
        world = self.world
        world.agents['visitor'].update(x=7.54, y=8.)
        world.agents['maya'].update(x=8., y=8.)
        world.agents['samir'].update(x=11.44, y=6.)
        world.agents['noah'].update(x=6., y=6.)
        world.command({'id': 'crowded-request', 'kind': 'task', 'agent': 'samir', 'text': 'Bring coffee to Elena'})
        advance(world, lambda: bool(world.tasks), maximum=180)
        self.assertEqual(next(iter(world.tasks.values()))['agent'], 'samir')
        self.assertGreaterEqual(distance(world.agents['visitor'], world.agents['maya']), .42)
        advance(world, lambda: next(iter(world.tasks.values()))['status'] == 'completed')
        self.assertTrue(world.agents['elena']['inventory'])

    def test_chat_errand_explains_that_no_task_was_started(self):
        self.world.agents['visitor'].update(x=12., y=7.)
        self.world.command({'id': 'chat-errand', 'kind': 'chat', 'agent': 'samir', 'text': 'Bring coffee to Elena'})
        advance(self.world, lambda: any('sent as chat' in e['text'] for e in self.world.storage.dialogue('samir')))
        self.assertFalse(self.world.tasks)

    def test_ollama_player_request_preempts_queued_background_work(self):
        world = self.world
        world.cognition.mode = 'ollama'
        owner = world.agents['maya']
        owner['thinking'] = True
        queued = Future()
        world.jobs.append({'future': queued, 'method': 'decide', 'agent': 'maya', 'revision': owner['revision'], 'context': {}})
        current = Future()
        current.set_running_or_notify_cancel()
        world.jobs.append({'future': current, 'method': 'reflect', 'agent': 'jun', 'revision': world.agents['jun']['revision'], 'context': {}})
        with patch.object(world.pool, 'submit', return_value=Future()):
            world.submit('task', world.agents['samir'], {'request': 'Bring coffee to Elena'})
        self.assertTrue(queued.cancelled())
        self.assertFalse(current.cancelled())
        self.assertFalse(owner['thinking'])
        world._jobs()
        self.assertFalse(any(e['kind'] == 'model_fallback' for e in world.storage.events()))
        self.assertEqual(len(world.jobs), 2)

    def test_duplicate_command_creates_one_task(self):
        self.world.agents["visitor"].update(x=6., y=7.)
        command = {"id": "same-request", "kind": "task", "agent": "maya", "text": "Bring coffee to Noah"}
        first = self.world.command(command)
        self.assertEqual(first, self.world.command(command))
        advance(self.world, lambda: len(self.world.tasks) == 1)
        self.assertEqual(len(self.world.tasks), 1)

    def test_conversation_history_survives_busy_world_events(self):
        self.world.speak("visitor", "My favorite color is blue.", ["maya"])
        for i in range(60):
            self.world.event("system", "activity", "Other activity " + str(i))
        self.assertFalse(any(e["kind"] == "dialogue" for e in self.world.storage.events(35)))
        self.assertTrue(any("favorite color" in e["text"] for e in self.world.inspect("maya")["dialogue"]))
        self.assertFalse(any("favorite color" in e["text"] for e in self.world.inspect("jun")["dialogue"]))

    def test_stale_model_result_cannot_replace_new_plan(self):
        a = self.world.agents["maya"]
        future = Future()
        future.set_result({"place": "studio", "activity": "Old intention", "minutes": 10})
        self.world.jobs.append({"future": future, "agent": "maya", "revision": a["revision"], "method": "decide", "context": {}})
        self.task(kind="wait", minutes=1)
        self.world.tick(.5)
        self.assertIsNone(a["routine"])
        self.assertIsNotNone(a["task"])

    def test_meeting_finishes_after_dialogue(self):
        self.world.agents["noah"].update(x=7., y=7.)
        task = self.task(kind="meet", item="")
        advance(self.world, lambda: task["status"] == "completed")
        dialogues = [e for e in self.world.storage.events(200) if e["kind"] == "dialogue"]
        self.assertTrue(any(e["actor"] == "noah" for e in dialogues))
        self.assertTrue(task["evidence"])

    def test_wait_uses_simulated_minutes(self):
        task = self.task(kind="wait", minutes=1)
        self.world.tick(.5)
        until = task["until"]
        advance(self.world, lambda: task["status"] == "completed")
        self.assertGreaterEqual(self.world.time, until)

    def test_save_resume_preserves_active_delivery_and_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "world.sqlite3"
            world = World(filename, Cognition("demo"), restore=False)
            quiet(world)
            task = world.create_task("maya", "Bring coffee to Noah", {"kind": "deliver", "recipient": "noah", "item": "coffee", "place": "", "minutes": 0})
            advance(world, lambda: task["step"] == 1)
            item_id = task["item_id"]
            world.close()
            restored = World(filename, Cognition("demo"))
            quiet(restored)
            self.assertEqual(restored.agents["maya"]["inventory"][0]["id"], item_id)
            self.assertTrue(restored.storage.memories("maya"))
            loaded = restored.tasks[task["id"]]
            advance(restored, lambda: loaded["status"] == "completed")
            self.assertEqual(restored.stock["coffee"], 11)
            restored.close()

    def test_unsupported_task_and_invalid_input_do_not_change_world(self):
        with self.assertRaises(CommandError):
            self.task(kind="teleport")
        with self.assertRaises(CommandError):
            self.world.command({"id": "bad-speed", "kind": "speed", "speed": True})
        self.assertFalse(self.world.tasks)


class ProviderTests(unittest.TestCase):
    def provider(self):
        provider = Cognition("demo")
        provider.mode, provider.model, provider.key = "openai", "test-model", "test-only-not-a-real-key"
        return provider

    def test_structured_response_and_token_accounting(self):
        provider = self.provider()
        response = {"status": "completed", "usage": {"total_tokens": 24}, "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"utterance":"Hello"}'}]}]}
        import io
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as call:
            result = provider._call("Say hello", {}, CHAT_SCHEMA)
        self.assertEqual(result, {"utterance": "Hello"})
        self.assertEqual(provider.tokens, 24)
        sent = json.loads(call.call_args.args[0].data)
        self.assertEqual(sent["text"]["format"]["type"], "json_schema")
        self.assertFalse(sent["store"])

    def test_refusal_is_handled_without_exposing_headers(self):
        import io
        provider = self.provider()
        response = {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]}
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaises(ModelError):
                provider._call("Say hello", {}, CHAT_SCHEMA)
        self.assertEqual(provider.failures, 1)
        self.assertNotIn(provider.key, json.dumps(provider.status()))

    def test_budget_blocks_extra_requests(self):
        provider = self.provider()
        provider.calls = provider.limit
        with patch("urllib.request.urlopen") as call:
            with self.assertRaises(ModelError):
                provider._call("Say hello", {}, CHAT_SCHEMA)
            call.assert_not_called()


class OllamaTests(unittest.TestCase):
    def provider(self):
        with patch.dict('os.environ', {'AGENT_MODEL': 'gemma4:31b', 'OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'AGENT_MODEL_TIMEOUT': '120'}):
            return Cognition('ollama')

    def response(self, content, **extra):
        import io
        return io.BytesIO(json.dumps({'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps(content)},
                                     'prompt_eval_count': 120, 'eval_count': 18, **extra}).encode())

    def test_all_cognition_methods_use_local_structured_api(self):
        provider = self.provider()
        cases = [('chat', {'utterance': 'Welcome to my shop.'}),
                 ('task', {'kind': 'deliver', 'recipient': 'elena', 'place': '', 'item': 'coffee', 'minutes': 0, 'reply': ''}),
                 ('decide', {'place': 'shop', 'activity': 'Organizing the shop', 'minutes': 5}),
                 ('reflect', {'insight': 'Elena appreciates a thoughtful errand.', 'memory_ids': [4]})]
        for method, answer in cases:
            with self.subTest(method=method), patch('urllib.request.urlopen', return_value=self.response(answer)) as call:
                result = getattr(provider, method)({})
                self.assertEqual(result, answer['utterance'] if method == 'chat' else answer)
                request = call.call_args.args[0]
                payload = json.loads(request.data)
                self.assertEqual(request.full_url, 'http://127.0.0.1:11434/api/chat')
                self.assertIsNone(request.get_header('Authorization'))
                self.assertEqual(payload['model'], 'gemma4:31b')
                self.assertEqual(payload['format']['type'], 'object')
                self.assertFalse(payload['stream'])
                self.assertFalse(payload['think'])
                self.assertEqual(call.call_args.kwargs['timeout'], 120)
        self.assertEqual(provider.tokens, 4 * 138)
        self.assertEqual(provider.status()['model'], 'gemma4:31b')

    def test_incomplete_or_invalid_answer_is_rejected(self):
        for content, extra in [({'utterance': 'cut short'}, {'done_reason': 'length'}),
                               ({'utterance': 42}, {}), ({'utterance': 'hi'}, {'done': False})]:
            with self.subTest(content=content, extra=extra):
                provider = self.provider()
                with patch('urllib.request.urlopen', return_value=self.response(content, **extra)):
                    with self.assertRaises(ModelError): provider.chat({})
                self.assertEqual(provider.failures, 1)

    def test_unavailable_ollama_reports_local_error_without_cloud_retry(self):
        provider = self.provider()
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('private detail')) as call:
            with self.assertRaisesRegex(ModelError, 'Ollama unavailable'): provider.chat({})
            with self.assertRaisesRegex(ModelError, 'Ollama unavailable'): provider.chat({})
        self.assertEqual(call.call_count, 1)
        self.assertEqual(provider.calls, 1)
        self.assertNotIn('private detail', provider.last_error)

    def test_invalid_reflection_references_are_rejected(self):
        provider = self.provider()
        with patch('urllib.request.urlopen', return_value=self.response({'insight': 'A thought', 'memory_ids': ['4']})):
            with self.assertRaisesRegex(ModelError, 'memory references'): provider.reflect({})

    def test_local_budget_stops_network_calls(self):
        provider = self.provider()
        provider.calls = provider.limit
        with patch('urllib.request.urlopen') as call:
            with self.assertRaises(ModelError): provider.chat({})
        call.assert_not_called()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.world = World(cognition=Cognition("demo"), restore=False)
        self.server = SimulationHTTPServer(("127.0.0.1", 0), self.world)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.world.close()

    def test_api_and_private_file_boundaries(self):
        with urllib.request.urlopen(self.base + "/api/state") as response:
            self.assertEqual(len(json.load(response)["agents"]), 6)
        for path in ("/.env", "/data/neighborhood.sqlite3", "/assets/../.env"):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(self.base + path)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()

    def test_cross_origin_command_is_rejected(self):
        request = urllib.request.Request(self.base + "/api/command", b'{"id":"p","kind":"pause","paused":true}', {"Origin": "https://example.com", "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        self.assertFalse(self.world.paused)


if __name__ == "__main__":
    unittest.main()
