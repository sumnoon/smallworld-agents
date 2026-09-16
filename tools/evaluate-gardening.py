"""Offline autonomous gardening evaluation under finite seeds (no network, browser or player save).

The unchanged world runs with demo cognition in an in-memory database. Every gardening task is
followed across ticks, every event is read through a sequence cursor, and the run exits nonzero
when seeds, beds, harvested vegetables or task evidence do not reconcile.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.model import Cognition
from server.world import TERMINAL, World

GARDENING = ("plant", "water", "harvest")
ACTION_EVENTS = {"community_" + kind: kind for kind in GARDENING}
OUTCOME_EVENTS = {"task_completed": "completed", "task_failed": "failed", "task_cancelled": "cancelled", "task_declined": "declined"}
NEXT_IN_CYCLE = {"plant": "water", "water": "harvest"}
SEED_BLOCKER = "No seeds remain"
DEADLINE_FAILURE = "Community task deadline elapsed"
MAX_VIOLATIONS = 50
EXIT_VIOLATION, EXIT_NO_CYCLE = 1, 2
FLAGS = ("AGENT_PROVIDER", "AGENT_ROUTINE_MODEL", "AGENT_REFLECTIONS", "AGENT_LIVE_EMBEDDINGS")


def read_events(storage, after=0):
    """Every event row after a sequence cursor, oldest first; never a latest-N window."""
    rows = storage.db.execute("SELECT * FROM events WHERE id>? ORDER BY id", (after,)).fetchall()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


def archived_tasks(storage):
    return {r["id"]: json.loads(r["data"]) for r in storage.db.execute("SELECT id,data FROM task_archive")}


def clock(seconds):
    s = int(round(seconds))
    return f"{s // 3600 % 24:02}:{s // 60 % 60:02}:{s % 60:02}"


def minutes(seconds):
    return round(seconds / 60, 2)


def source_state():
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30, check=True).stdout
    try:
        changed = [line[3:] for line in git("status", "--porcelain").splitlines() if line.strip()]
        return {"revision": git("rev-parse", "HEAD").strip(), "dirty": bool(changed), "changed_paths": changed}
    except (OSError, subprocess.SubprocessError):
        return {"revision": None, "dirty": None, "changed_paths": [], "note": "Git state was unavailable"}


def blocker_reason(world, event):
    name = world.agents.get(event["actor"], {}).get("name", "")
    return event["text"][len(name) + 2:] if name and event["text"].startswith(name + ": ") else event["text"]


def nested(counter_factory=Counter):
    return defaultdict(counter_factory)


def plain(value):
    """Nested defaultdicts and Counters as sorted plain dictionaries for JSON."""
    if isinstance(value, dict):
        return {k: plain(v) for k, v in sorted(value.items())}
    return value


class GardeningMonitor:
    """Observes a world between ticks: task lifetimes, blocked samples and running invariants."""

    def __init__(self, world):
        self.world = world
        self.cursor = 0
        self.last_time = world.time
        self.start = world.time
        self.event_counts = Counter()
        self.events = []  # task_* and gardening action rows, kept in full
        self.tasks = {}  # gardening task id -> attributes when first observed live
        self.open_before = []
        self.blocked_seconds = Counter()
        self.blocked_resident_seconds = 0.0
        self.peak_blocked = {"count": 0, "time": None, "tasks": []}
        self.deadline_checks = {}
        self.plants = self.harvests = 0
        self.seed_exhausted = None
        self.linked = defaultdict(list)  # task id -> action event ids, as read
        self.outcome_rows = defaultdict(list)
        self.harvested = []  # (item id, event id)
        self.violations = {}
        self.violation_count = 0
        self.initial = {"seeds": world.community["seeds"], "bed_owners": sorted(world.community["beds"]),
                        "vegetables": sorted(i["id"] for a in world.agents.values() for i in a["inventory"] if i["kind"] == "vegetables")}
        self.ingest()

    def violate(self, check, detail, tasks=(), events=()):
        self.violation_count += 1
        key = (check, tuple(tasks), tuple(events))
        if key in self.violations:
            self.violations[key]["occurrences"] += 1
        elif len(self.violations) < MAX_VIOLATIONS:
            self.violations[key] = {"check": check, "time": self.world.time, "clock": clock(self.world.time), "detail": detail,
                                    "tasks": list(tasks), "events": list(events), "occurrences": 1}

    def ingest(self):
        for row in read_events(self.world.storage, self.cursor):
            self.cursor = row["id"]
            kind = row["kind"]
            self.event_counts[kind] += 1
            if kind in ACTION_EVENTS or kind.startswith("task_"):
                self.events.append(row)
            if kind == "community_plant":
                self.plants += 1
                if self.seed_exhausted is None and self.initial["seeds"] - self.plants <= 0:
                    self.seed_exhausted = {"time": row["time"], "clock": clock(row["time"]), "elapsed_minutes": minutes(row["time"] - self.start),
                                           "event": row["id"], "task": row["payload"].get("task")}
            elif kind == "community_harvest":
                self.harvests += 1
            if kind in OUTCOME_EVENTS:
                self.outcome_rows[row["payload"].get("task")].append(row)
                self.check_outcome(row)
            elif kind in ACTION_EVENTS:
                self.check_action(row)

    def task_record(self, tid):
        return self.world.tasks.get(tid) or (self.world.storage.archived_task(tid) if tid else None)

    def check_action(self, row):
        """Checked as each action event is read: its task, owner, site, evidence and harvested item."""
        tid, action = row["payload"].get("task"), ACTION_EVENTS[row["kind"]]
        task = self.task_record(tid)
        self.linked[tid].append(row["id"])
        if (not task or task["kind"] != action or task["agent"] != row["actor"] or task["status"] != "completed"
                or row["payload"].get("site") != self.world.bed_goal(row["actor"]) or row["id"] not in task.get("evidence", [])):
            self.violate("action_event_unverified", f"A {action} event does not belong to a completed {action} task by its owner at its bed with the event in its evidence",
                         [tid] if tid else [], [row["id"]])
        if len(self.linked[tid]) > 1:
            self.violate("duplicate_action_event", "A task has more than one gardening action event", [tid] if tid else [], list(self.linked[tid]))
        if action == "harvest":
            item = (row["payload"].get("item") or {}).get("id")
            earlier = [seq for i, seq in self.harvested if i == item]
            if item is None or earlier:
                self.violate("harvest_item_not_unique", "A harvest item ID is missing or repeated", [tid] if tid else [], earlier + [row["id"]])
            self.harvested.append((item, row["id"]))

    def check_outcome(self, row):
        """Checked as each outcome event is read: completions have one action, other outcomes have none."""
        tid = row["payload"].get("task")
        task = self.task_record(tid)
        if not task or task["kind"] not in GARDENING:
            return
        if OUTCOME_EVENTS[row["kind"]] == "completed":
            if len(self.linked[tid]) != 1:
                self.violate("completion_without_single_action", f"A completed task has {len(self.linked[tid])} action events", [tid], [row["id"], *self.linked[tid]])
        elif self.linked[tid] or task.get("evidence"):
            self.violate("effect_without_completion", f"A {OUTCOME_EVENTS[row['kind']]} {task['kind']} task has action effects or evidence", [tid],
                         [row["id"], *self.linked[tid], *task.get("evidence", [])])

    def check_vegetables(self):
        held = Counter(i["id"] for a in self.world.agents.values() for i in a["inventory"] if i["kind"] == "vegetables")
        expected = Counter(self.initial["vegetables"] + [i for i, _ in self.harvested if i is not None])
        if held != expected:
            extra, missing = sorted((held - expected).elements()), sorted((expected - held).elements())
            owners = sorted({a["id"] for a in self.world.agents.values() for i in a["inventory"] if i["id"] in extra})
            self.violate("vegetable_reconciliation", f"Held vegetables differ from initial plus harvested items: unexpected {extra} held by {owners}; missing {missing}",
                         events=[seq for _, seq in self.harvested])
        return held

    def before_tick(self):
        live = self.world.tasks
        self.open_before = [tid for tid in self.tasks if tid in live and live[tid]["status"] not in TERMINAL]

    def after_tick(self):
        w = self.world
        step, self.last_time = w.time - self.last_time, w.time
        self.ingest()
        for tid, task in w.tasks.items():
            if tid not in self.tasks and task["kind"] in GARDENING:
                self.tasks[tid] = {"agent": task["agent"], "kind": task["kind"], "origin": task.get("origin", "player"), "created": task["created"]}
        # A task seen blocked after a tick is charged that tick's whole simulated step.
        blocked = [tid for tid in self.tasks if tid in w.tasks and w.tasks[tid]["status"] == "blocked"]
        for tid in blocked:
            self.blocked_seconds[tid] += step
        self.blocked_resident_seconds += step * len(blocked)
        if len(blocked) > self.peak_blocked["count"]:
            self.peak_blocked = {"count": len(blocked), "time": w.time, "clock": clock(w.time), "tasks": blocked}
        # The engine fails a community task once time > deadline, on the holder's next processed tick.
        for tid in self.open_before:
            task = w.tasks.get(tid)
            if task is None or w.time <= task["deadline"]:
                continue
            a = w.agents[task["agent"]]
            check = self.deadline_checks.setdefault(tid, {"task": tid, "deadline": task["deadline"], "first_tick_past_deadline": w.time, "skipped_ticks": 0})
            if task["status"] in TERMINAL or a["task"] != tid:
                # Only a single deadline failure event on this update, with the resident released, counts as enforcement.
                ends = self.outcome_rows.get(tid, [])
                failures = [e for e in ends if e["kind"] == "task_failed" and e["time"] == w.time and e["text"] == DEADLINE_FAILURE]
                enforced = task["status"] == "failed" and task.get("blocker") == DEADLINE_FAILURE and a["task"] != tid and len(ends) == len(failures) == 1
                check.update(terminal_status=task["status"], blocker=task.get("blocker", ""), terminal_time=w.time,
                             lag_seconds=round(w.time - task["deadline"], 3), released=a["task"] != tid,
                             outcome_events=[e["id"] for e in ends], failure_event=failures[0]["id"] if len(failures) == 1 else None, enforced=enforced,
                             on_first_processed_tick=enforced and (check["first_tick_past_deadline"] == w.time or check["skipped_ticks"] > 0))
                if not enforced:
                    self.violate("deadline_wrong_outcome", f"A task past its deadline ended as {task['status']} ({task.get('blocker', '')!r}) instead of one deadline failure that releases its resident",
                                 [tid], [e["id"] for e in ends])
            elif a["conversation"] or a["thinking"]:
                check["skipped_ticks"] += 1
            else:
                self.violate("deadline_not_enforced", "A task past its deadline stayed open after its holder's tick was processed", [tid])
        seeds = w.community["seeds"]
        if seeds < 0:
            self.violate("negative_seeds", f"Seeds fell to {seeds}")
        if self.initial["seeds"] - seeds != self.plants:
            self.violate("seed_reconciliation", f"{self.initial['seeds']} initial - {seeds} current != {self.plants} plant events")
        expected_beds = len(self.initial["bed_owners"]) + self.plants - self.harvests
        if len(w.community["beds"]) != expected_beds:
            self.violate("bed_reconciliation", f"{len(w.community['beds'])} beds != {expected_beds} from events")
        holding = defaultdict(list)
        for tid, meta in self.tasks.items():
            if meta["origin"] == "autonomous" and tid in w.tasks and w.tasks[tid]["status"] not in TERMINAL:
                holding[meta["agent"]].append(tid)
        for aid, tids in holding.items():
            if len(tids) > 1:
                self.violate("overlapping_autonomous_tasks", f"{aid} holds {len(tids)} open autonomous gardening tasks", tids)
        self.check_vegetables()

    def finish(self):
        w = self.world
        self.ingest()
        end = w.time
        archive = archived_tasks(w.storage)
        accepted, outcomes, blocks, actions = {}, defaultdict(list), defaultdict(list), defaultdict(list)
        action_rows = []
        for e in self.events:
            tid = e["payload"].get("task")
            if e["kind"] == "task_accepted" and tid:
                accepted.setdefault(tid, e)
            elif e["kind"] in OUTCOME_EVENTS:
                outcomes[tid].append(e)
            elif e["kind"] == "task_blocked":
                blocks[tid].append(e)
            elif e["kind"] in ACTION_EVENTS:
                action_rows.append(e)
                actions[tid].append(e)

        # Each task is resolved once, from live state or the archive table.
        tasks, sources = {}, Counter()
        for tid in dict.fromkeys([*self.tasks, *accepted]):
            live, stored = w.tasks.get(tid), archive.get(tid)
            record = live or stored
            if record is None:
                if tid in self.tasks:
                    self.violate("task_record_missing", "A tracked gardening task is in neither live state nor task_archive", [tid])
                continue
            if record["kind"] not in GARDENING:
                continue
            if live and stored:
                self.violate("task_double_recorded", "A task is both live and archived", [tid])
            tasks[tid] = record
            sources["live" if live else "archive"] += 1

        accepted_counts, terminal_counts, open_counts = nested(), nested(nested), nested(nested)
        for tid, task in tasks.items():
            origin = task.get("origin", "player")
            if tid in accepted:
                accepted_counts[task["kind"]][origin] += 1
            (terminal_counts if task["status"] in TERMINAL else open_counts)[task["kind"]][origin][task["status"]] += 1
            ends = outcomes.get(tid, [])
            if (len(ends) != 1 or OUTCOME_EVENTS[ends[0]["kind"]] != task["status"]) if task["status"] in TERMINAL else ends:
                self.violate("outcome_event_mismatch", f"Task status {task['status']} does not match its {len(ends)} outcome event(s)", [tid], [e["id"] for e in ends])

        # Physical effects link to exactly one completed task of the same kind, owner and bed.
        linked = []
        for tid, task in sorted(tasks.items(), key=lambda item: (item[1]["created"], item[0])):
            matches = actions.get(tid, [])
            if task["status"] == "completed":
                event = matches[0] if len(matches) == 1 else None
                if (not event or event["kind"] != "community_" + task["kind"] or event["actor"] != task["agent"]
                        or event["payload"].get("site") != w.bed_goal(task["agent"]) or event["id"] not in task.get("evidence", [])):
                    self.violate("action_evidence_mismatch", f"A completed {task['kind']} task needs exactly one matching action event by its owner at its bed", [tid], [e["id"] for e in matches])
                    continue
                item = event["payload"].get("item")
                linked.append({"task": tid, "agent": task["agent"], "kind": task["kind"], "origin": task.get("origin", "player"),
                               "created": task["created"], "event": event["id"], "event_time": event["time"], "clock": clock(event["time"]),
                               "site": event["payload"]["site"], "item": item["id"] if item else None,
                               "outcome_event": outcomes[tid][0]["id"] if outcomes.get(tid) else None})
            elif matches or task.get("evidence"):
                self.violate("effect_without_completion", f"A {task['status']} {task['kind']} task has action effects or evidence", [tid], [e["id"] for e in matches] + list(task.get("evidence", [])))
        orphans = [e["id"] for e in action_rows if e["payload"].get("task") not in tasks]
        if orphans:
            self.violate("action_without_task", "Gardening action events reference no gardening task", events=orphans)

        # Replay effects in event order against the initial and final resources.
        beds = set(self.initial["bed_owners"])
        for e in action_rows:
            if e["kind"] == "community_plant":
                if e["actor"] in beds:
                    self.violate("plant_on_existing_bed", "A bed was planted twice without a harvest", [e["payload"].get("task")], [e["id"]])
                beds.add(e["actor"])
            elif e["kind"] == "community_harvest":
                if e["actor"] not in beds:
                    self.violate("harvest_without_bed", "A harvest had no planted bed", [e["payload"].get("task")], [e["id"]])
                beds.discard(e["actor"])
        plants, harvests = self.event_counts["community_plant"], self.event_counts["community_harvest"]
        seeds = w.community["seeds"]
        if seeds < 0 or self.initial["seeds"] - seeds != plants:
            self.violate("seed_reconciliation", f"{self.initial['seeds']} initial - {seeds} final != {plants} plant events",
                         events=[e["id"] for e in action_rows if e["kind"] == "community_plant"])
        final_beds = set(w.community["beds"])
        if final_beds != beds or len(final_beds) != len(self.initial["bed_owners"]) + plants - harvests:
            self.violate("bed_reconciliation", f"Final beds {sorted(final_beds)} != replayed beds {sorted(beds)}")
        # Harvest item uniqueness was checked as each event was read; holdings are rechecked at the end.
        held = list(self.check_vegetables().elements())

        # Blocking: unique tasks, repeated events and sampled simulated time are separate measures.
        reason_events, reason_tasks = Counter(), defaultdict(set)
        task_reasons = defaultdict(list)
        for tid in tasks:
            for e in blocks.get(tid, []):
                reason = blocker_reason(w, e)
                reason_events[reason] += 1
                reason_tasks[reason].add(tid)
                if reason not in task_reasons[tid]:
                    task_reasons[tid].append(reason)
        affected, still_open = [], []
        for tid, task in sorted(tasks.items(), key=lambda item: (item[1]["created"], item[0])):
            ends = outcomes.get(tid, [])
            terminal = ends[0]["time"] if ends else None
            lifetime = (terminal if terminal is not None else end) - task["created"]
            row = {"task": tid, "agent": task["agent"], "kind": task["kind"], "origin": task.get("origin", "player"),
                   "created": task["created"], "created_clock": clock(task["created"]), "deadline": task["deadline"], "deadline_clock": clock(task["deadline"]),
                   "status": task["status"], "blocker": task.get("blocker", ""), "sampled_blocked_minutes": minutes(self.blocked_seconds[tid]),
                   "lifetime_minutes": minutes(lifetime), "censored": task["status"] not in TERMINAL}
            if task["status"] not in TERMINAL:
                still_open.append({**row, "observed_age_minutes": minutes(end - task["created"])})
            if blocks.get(tid) or self.blocked_seconds[tid]:
                first = blocks[tid][0]["time"] if blocks.get(tid) else None
                affected.append({**row, "first_blocked": first, "first_blocked_clock": clock(first) if first is not None else None,
                                 "task_blocked_events": len(blocks.get(tid, [])), "reasons": task_reasons[tid],
                                 "terminal_time": terminal, "terminal_clock": clock(terminal) if terminal is not None else None,
                                 "seed_starved": task["kind"] == "plant" and SEED_BLOCKER in task_reasons[tid]})
        starved = [r for r in affected if r["seed_starved"]]
        checks = []
        for tid, check in self.deadline_checks.items():
            checks.append({**check, "agent": tasks.get(tid, {}).get("agent"), "kind": tasks.get(tid, {}).get("kind"),
                           "seed_starved": any(r["task"] == tid for r in starved), "deadline_clock": clock(check["deadline"])})
        starved_past = [c for c in checks if c["seed_starved"]]

        bed_states = Counter("planted_unwatered" if not bed.get("ready_at") else "growing" if end < bed["ready_at"] else "ripe"
                             for bed in w.community["beds"].values())
        vegetables = Counter(a["id"] for a in w.agents.values() for i in a["inventory"] if i["kind"] == "vegetables")

        cycles, progress = [], {}
        for item in sorted(linked, key=lambda r: r["event"]):
            if item["origin"] != "autonomous":
                continue
            chain = progress.get(item["agent"], [])
            if item["kind"] == "plant":
                chain = [item]
            elif chain and NEXT_IN_CYCLE.get(chain[-1]["kind"]) == item["kind"]:
                chain = chain + [item]
            if len(chain) == 3:
                cycles.append({"agent": item["agent"], "tasks": [c["task"] for c in chain], "events": [c["event"] for c in chain],
                               "event_clocks": [c["clock"] for c in chain], "vegetables": chain[-1]["item"]})
                chain = []
            progress[item["agent"]] = chain

        by_kind = lambda kind: sorted({r["actor"] for r in action_rows if r["kind"] == "community_" + kind})
        peak = dict(self.peak_blocked)
        return {
            "tasks": {"accepted": plain(accepted_counts), "terminal": plain(terminal_counts), "open": plain(open_counts),
                      "unique_tasks": len(tasks), "resolved_from": dict(sources)},
            "residents": {label + suffix: len(ids) if suffix else ids for kind, label in (("plant", "planting"), ("water", "watering"), ("harvest", "harvesting"))
                          for ids in (by_kind(kind),) for suffix in ("_count", "")},
            "seeds": {"initial": self.initial["seeds"], "final": seeds, "plant_events": plants, "exhausted": self.seed_exhausted},
            "beds": {"initial": len(self.initial["bed_owners"]), "final": len(final_beds), "harvest_events": harvests,
                     "final_by_state": dict(sorted(bed_states.items())), "final_owners": sorted(final_beds)},
            "vegetables": {"initial": len(self.initial["vegetables"]), "final": len(held), "by_owner": dict(sorted(vegetables.items()))},
            "successful_actions": linked,
            "autonomous_cycles": {"count": len(cycles), "residents": sorted({c["agent"] for c in cycles}), "cycles": cycles},
            "blocking": {
                "time_unit_note": "Sampled blocked time charges each whole simulated tick step to every gardening task whose status is blocked after that tick.",
                "task_blocked_events_all": self.event_counts["task_blocked"],
                "task_blocked_events_gardening": sum(len(blocks.get(tid, [])) for tid in tasks),
                "unique_blocked_tasks": dict(sorted(Counter(r["kind"] for r in affected if r["task_blocked_events"]).items())),
                "unique_blocked_planting_tasks": sum(r["kind"] == "plant" and r["task_blocked_events"] > 0 for r in affected),
                "blockers_by_reason": {reason: {"events": reason_events[reason], "unique_tasks": len(reason_tasks[reason])} for reason in sorted(reason_events)},
                "peak_concurrently_blocked_tasks": peak,
                "sampled_blocked_resident_minutes": minutes(self.blocked_resident_seconds),
                "seed_contention": {"observed": bool(starved), "seed_starved_planting_tasks": len(starved),
                                    "note": "Planting tasks were blocked because no seeds remained." if starved else "No planting task was blocked by seed shortage in this run."},
                "deadline_enforcement": {"rule": "Past its deadline, a task must fail with '" + DEADLINE_FAILURE + "', emit exactly one task_failed event on that update and release its resident; any other outcome is a violation.",
                                         "tasks_observed_past_deadline": len(checks), "seed_starved_tasks_past_deadline": len(starved_past),
                                         "failed_through_deadline": sum(bool(c.get("enforced")) for c in starved_past),
                                         "released_on_first_processed_tick": sum(bool(c.get("on_first_processed_tick")) for c in starved_past),
                                         "checks": checks},
                "affected_tasks": affected,
            },
            "still_open_tasks": still_open,
            "events": {"total": sum(self.event_counts.values()), "by_kind": dict(sorted(self.event_counts.items()))},
            "invariants": {"passed": not self.violation_count, "violation_count": self.violation_count, "violations": list(self.violations.values())},
        }


def run(population=25, ticks=6000, seeds=12, dt=0.5):
    began = time.monotonic()
    world = World(cognition=Cognition("demo"), restore=False, residents=population)
    try:
        # Controlled workload: no spontaneous conversations or reflections; everything else is the engine's own.
        world.speed = 1
        world.reflections_enabled = False
        world.next_social = 10**10
        world.community["seeds"] = seeds
        residents = [a for a in world.agents.values() if a["id"] != "visitor"]
        for a in residents:
            a["next_decision"] = world.time
        start = world.time
        monitor = GardeningMonitor(world)
        initial_resources = {"seeds": world.community["seeds"], "beds": len(world.community["beds"]), "market_supplies": world.community["supplies"],
                             "vegetables": len(monitor.initial["vegetables"]), "inventory_items": sum(len(a["inventory"]) for a in residents)}
        for _ in range(ticks):
            monitor.before_tick()
            world.tick(dt)
            monitor.after_tick()
            if any(not job["future"].done() for job in world.jobs):
                time.sleep(.001)
        results = monitor.finish()
        report = {
            "evaluation": "autonomous-gardening", "provider": "demo", "source": source_state(),
            "workload": {"population": len(residents), "initial_resources": initial_resources,
                         "time_step": {"tick_dt": dt, "speed": world.speed, "simulated_seconds_per_tick": round((world.time - start) / ticks, 6)},
                         "ticks": ticks, "simulated_start": start, "simulated_start_clock": clock(start), "simulated_end": world.time,
                         "simulated_end_clock": clock(world.time), "simulated_duration_seconds": world.time - start,
                         "settings": {"storage": "in-memory SQLite", "cognition": "explicit demo (local rules)",
                                      "social_conversations": "disabled (next spontaneous conversation scheduled beyond the run)",
                                      "reflections": "disabled (reflections_enabled=False)", "initial_decisions": "every resident due at the first tick",
                                      "unchanged": "needs, routines, later decision timing, movement, retries, resources and task deadlines",
                                      "not_used": "player commands, replenishment, inventory removal, forced arrivals, timestamp fast-forwarding",
                                      "environment_flags": {k: os.environ.get(k) for k in FLAGS}},
                         "scheduling_note": "Winners depend on travel and tick order; task and item IDs are random, so repeated runs can pick different residents."},
            **results,
            "wall_seconds": round(time.monotonic() - began, 2),
            "timing_note": "Wall time is descriptive for this machine only.",
        }
        report["blockers"] = blockers(report)
        return report
    finally:
        world.close()


def blockers(report):
    found = []
    if not report["invariants"]["passed"]:
        found.append(f"{report['invariants']['violation_count']} invariant violation(s); see invariants.violations for task and event IDs.")
    if not report["autonomous_cycles"]["count"]:
        found.append(f"No autonomous plant-water-harvest cycle completed in {report['workload']['ticks']} ticks; see tasks, successful_actions and blocking.")
    return found


def exit_code(report):
    if not report["invariants"]["passed"]:
        return EXIT_VIOLATION
    return 0 if report["autonomous_cycles"]["count"] else EXIT_NO_CYCLE


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = argparse.ArgumentParser(description="Measure autonomous gardening and seed contention offline.")
    parser.add_argument("--population", type=int, default=25)
    parser.add_argument("--ticks", type=int, default=6000)
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not 5 <= args.population <= 25:
        parser.error("population must be 5-25")
    if not 1 <= args.ticks <= 100000:
        parser.error("ticks must be 1-100000")
    if args.seeds < 0:
        parser.error("seeds must be nonnegative")
    report = {"command": " ".join(["python tools/evaluate-gardening.py", *argv]), **run(args.population, args.ticks, args.seeds)}
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
