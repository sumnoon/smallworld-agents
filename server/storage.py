import json
import math
import re
import sqlite3


class Storage:
    def __init__(self, filename):
        self.db = sqlite3.connect(str(filename), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY, owner TEXT, kind TEXT, text TEXT,
              created REAL, accessed REAL, importance REAL, evidence TEXT);
            CREATE INDEX IF NOT EXISTS memory_owner ON memories(owner, created);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, time REAL, actor TEXT, kind TEXT, text TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS snapshots(name TEXT PRIMARY KEY, data TEXT);
            CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, response TEXT);
        ''')
        self.db.commit()

    def event(self, time, actor, kind, text, payload=None):
        cursor = self.db.execute("INSERT INTO events(time,actor,kind,text,payload) VALUES(?,?,?,?,?)",
                                 (time, actor, kind, text, json.dumps(payload or {})))
        self.db.commit()
        return cursor.lastrowid

    def memory(self, owner, kind, text, time, importance=4, evidence=None):
        self.db.execute("INSERT INTO memories(owner,kind,text,created,accessed,importance,evidence) VALUES(?,?,?,?,?,?,?)",
                        (owner, kind, text[:1200], time, time, importance, json.dumps(evidence or [])))
        self.db.commit()

    def memories(self, owner, limit=30):
        rows = self.db.execute("SELECT * FROM memories WHERE owner=? ORDER BY id DESC LIMIT ?", (owner, limit)).fetchall()
        return [{**dict(r), "evidence": json.loads(r["evidence"])} for r in rows]

    def retrieve(self, owner, query, time, limit=8):
        # Transparent lexical baseline. The adapter can later replace similarity with embeddings.
        stop = {"the", "and", "with", "what", "that", "this", "have", "you", "are", "for", "was", "your", "from"}
        tokens = lambda text: set(re.findall(r"[a-z]{3,}", text.lower())) - stop
        q = tokens(query)
        ranked = []
        for memory in self.memories(owner, 1000):
            m = tokens(memory["text"])
            relevance = len(q & m) / math.sqrt(max(1, len(q) * len(m)))
            recency = .995 ** (max(0, time - memory["accessed"]) / 3600)
            score = 3 * relevance + memory["importance"] / 10 + recency
            ranked.append({**memory, "retrieval_score": round(score, 3)})
        ranked.sort(key=lambda m: (m["retrieval_score"], m["id"]), reverse=True)
        result = ranked[:limit]
        self.db.executemany("UPDATE memories SET accessed=? WHERE id=?", [(time, m["id"]) for m in result])
        self.db.commit()
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
        self.db.commit()

    def load(self, name="autosave"):
        row = self.db.execute("SELECT data FROM snapshots WHERE name=?", (name,)).fetchone()
        return json.loads(row[0]) if row else None

    def command_result(self, command_id):
        row = self.db.execute("SELECT response FROM commands WHERE id=?", (command_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def remember_command(self, command_id, result):
        self.db.execute("INSERT OR REPLACE INTO commands VALUES(?,?)", (command_id, json.dumps(result)))
        self.db.commit()

    def close(self):
        self.db.close()
