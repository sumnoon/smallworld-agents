import json
import hashlib
import zlib
from contextlib import contextmanager
from functools import lru_cache
import math
import re
import sqlite3

STOP_WORDS = frozenset({"the", "and", "with", "what", "that", "this", "have", "you", "are", "for", "was", "your", "from"})


@lru_cache(maxsize=32768)
def tokens(text):
    return frozenset(re.findall(r"[a-z]{3,}", text.lower())) - STOP_WORDS


class Storage:
    def __init__(self, filename):
        self.db = sqlite3.connect(str(filename), check_same_thread=False)
        self.depth = 0
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY, owner TEXT, kind TEXT, text TEXT,
              created REAL, accessed REAL, importance REAL, evidence TEXT);
            CREATE INDEX IF NOT EXISTS memory_owner ON memories(owner, created);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, time REAL, actor TEXT, kind TEXT, text TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS snapshots(name TEXT PRIMARY KEY, data TEXT);
            CREATE TABLE IF NOT EXISTS replay_frames(id INTEGER PRIMARY KEY, time REAL, digest TEXT, data BLOB);
            CREATE TABLE IF NOT EXISTS embeddings(key TEXT PRIMARY KEY, vector TEXT);
            CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, time REAL, agent TEXT, method TEXT, data TEXT);
            CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, response TEXT);
            CREATE TABLE IF NOT EXISTS task_archive(id TEXT PRIMARY KEY, finished REAL, agent TEXT, status TEXT, data TEXT);
        ''')
        self.flush()

    def event(self, time, actor, kind, text, payload=None):
        cursor = self.db.execute("INSERT INTO events(time,actor,kind,text,payload) VALUES(?,?,?,?,?)",
                                 (time, actor, kind, text, json.dumps(payload or {})))
        self.flush()
        return cursor.lastrowid

    def memory(self, owner, kind, text, time, importance=4, evidence=None):
        if kind == "observation":
            prior = self.db.execute("SELECT id FROM memories WHERE owner=? AND kind=? AND text=? AND created>?", (owner, kind, text[:1200], time-300)).fetchone()
            if prior:
                return prior[0]
        cursor = self.db.execute("INSERT INTO memories(owner,kind,text,created,accessed,importance,evidence) VALUES(?,?,?,?,?,?,?)",
                        (owner, kind, text[:1200], time, time, importance, json.dumps(evidence or [])))
        self.flush()

        return cursor.lastrowid

    def memories(self, owner, limit=30):
        rows = self.db.execute("SELECT * FROM memories WHERE owner=? ORDER BY id DESC LIMIT ?", (owner, limit)).fetchall()
        return [{**dict(r), "evidence": json.loads(r["evidence"])} for r in rows]

    def importance_since(self, owner, since, window=120):
        """Summed importance of recent direct memories, without decoding rows in Python."""
        row = self.db.execute("""SELECT COALESCE(SUM(importance),0) FROM
            (SELECT importance, kind, created FROM memories WHERE owner=? ORDER BY id DESC LIMIT ?)
            WHERE created>? AND kind NOT IN ('identity','reflection')""", (owner, window, since)).fetchone()
        return row[0]

    def retrieve(self, owner, query, time, limit=8):
        # Transparent lexical baseline. Evidence is decoded only for the returned memories.
        q = tokens(query)
        ranked = []
        for row in self.db.execute("SELECT * FROM memories WHERE owner=? ORDER BY id DESC LIMIT 1000", (owner,)):
            m = tokens(row["text"])
            relevance = len(q & m) / math.sqrt(max(1, len(q) * len(m)))
            recency = .995 ** (max(0, time - row["accessed"]) / 3600)
            ranked.append((round(3 * relevance + row["importance"] / 10 + recency, 3), row["id"], row))
        ranked.sort(key=lambda entry: entry[:2], reverse=True)
        result = [{**dict(row), "evidence": json.loads(row["evidence"]), "retrieval_score": score} for score, _, row in ranked[:limit]]
        self.db.executemany("UPDATE memories SET accessed=? WHERE id=?", [(time, m["id"]) for m in result])
        self.flush()
        return result

    def events(self, limit=40):
        rows = self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def dialogue(self, owner, limit=40):
        rows = self.db.execute("""SELECT * FROM events WHERE kind='dialogue' AND
            (actor=? OR EXISTS (SELECT 1 FROM json_each(json_extract(events.payload,'$.recipients')) WHERE value=?))
            ORDER BY id DESC LIMIT ?""", (owner, owner, limit)).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def save(self, data, name="autosave"):
        self.db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?)", (name, json.dumps(data)))
        self.flush()

    def load(self, name="autosave"):
        row = self.db.execute("SELECT data FROM snapshots WHERE name=?", (name,)).fetchone()
        return json.loads(row[0]) if row else None

    def command_result(self, command_id):
        row = self.db.execute("SELECT response FROM commands WHERE id=?", (command_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def remember_command(self, command_id, result):
        self.db.execute("INSERT OR REPLACE INTO commands VALUES(?,?)", (command_id, json.dumps(result)))
        self.flush()

    def flush(self):
        if not self.depth:
            self.db.commit()

    @contextmanager
    def transaction(self):
        outer = self.depth == 0
        self.depth += 1
        try:
            yield
        except BaseException:
            if outer:
                self.db.rollback()
            raise
        else:
            if outer:
                self.db.commit()
        finally:
            self.depth -= 1

    def record_frame(self, state):
        raw = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
        self.db.execute("INSERT INTO replay_frames(time,digest,data) VALUES(?,?,?)",
                        (state["time"], hashlib.sha256(raw).hexdigest(), zlib.compress(raw)))
        # Keep the newest 7,201 frames (one per six simulated seconds plus commands); bounded disk usage.
        self.db.execute("DELETE FROM replay_frames WHERE id < (SELECT MAX(id)-7200 FROM replay_frames)")
        self.flush()

    def replay_index(self):
        return [dict(r) for r in self.db.execute("SELECT id,time,digest FROM replay_frames ORDER BY id")]

    def replay_frame(self, frame_id):
        row = self.db.execute("SELECT digest,data FROM replay_frames WHERE id=?", (frame_id,)).fetchone()
        if not row:
            raise ValueError("Replay frame not found")
        raw = zlib.decompress(row["data"])
        if hashlib.sha256(raw).hexdigest() != row["digest"]:
            raise ValueError("Replay integrity check failed")
        return json.loads(raw)

    def archive_tasks(self, tasks):
        self.db.executemany("INSERT OR REPLACE INTO task_archive VALUES(?,?,?,?,?)",
                            [(t["id"], t.get("finished_at", 0), t["agent"], t["status"], json.dumps(t)) for t in tasks])
        self.flush()

    def archived_task(self, task_id):
        row = self.db.execute("SELECT data FROM task_archive WHERE id=?", (task_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def decision(self, time, agent, method, data):
        self.db.execute("INSERT INTO decisions(time,agent,method,data) VALUES(?,?,?,?)", (time, agent, method, json.dumps(data)))
        self.flush()

    def close(self):
        self.db.close()
