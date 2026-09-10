"""Optional Ollama semantic retrieval; called only on a cognition worker."""
import hashlib
import json
import math
import os
import threading
import time
import urllib.request


class SemanticMemory:
    def __init__(self):
        self.model = os.getenv("AGENT_EMBEDDING_MODEL", "")
        self.url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.cache = {}
        self.lock = threading.Lock()
        self.calls = self.tokens = 0
        self.limit = max(1,int(os.getenv("AGENT_MAX_EMBED_REQUESTS", "500")))
        self.error = ""
        self.retry_at = 0
        self.enabled = os.getenv("AGENT_MEMORY_RETRIEVAL", "on") != "off"

    def key(self, text):
        return hashlib.sha256((self.model + "\0" + text).encode()).hexdigest()

    def rank(self, context):
        candidates = context.pop("memory_candidates", context.get("memories", []))
        if not self.enabled:
            context["memories"] = []
            return context
        if not self.model or time.monotonic() < self.retry_at:
            return context
        query = context.pop("memory_query", "recent experiences")
        texts = list(dict.fromkeys([query] + [m["text"] for m in candidates]))
        try:
            with self.lock:
                missing = [t for t in texts if self.key(t) not in self.cache]
                for start in range(0, len(missing), 32):
                    if self.calls >= self.limit:
                        raise ValueError("Embedding request budget reached")
                    self.calls += 1
                    batch = missing[start:start+32]
                    body = json.dumps({"model": self.model, "input": batch, "truncate": True}).encode()
                    request = urllib.request.Request(self.url + "/api/embed", data=body, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=15) as response:
                        result = json.load(response)
                    vectors = result.get("embeddings", [])
                    if len(vectors) != len(batch) or any(not v or any(type(x) not in (int, float) or not math.isfinite(x) for x in v) for v in vectors):
                        raise ValueError("Invalid embedding response")
                    self.tokens += result.get("prompt_eval_count", 0)
                    for text, vector in zip(batch, vectors):
                        self.cache[self.key(text)] = vector
                q = self.cache[self.key(query)]
                def score(memory):
                    v = self.cache[self.key(memory["text"])]
                    if len(q) != len(v):
                        raise ValueError("Embedding dimensions changed")
                    cosine = sum(a*b for a,b in zip(q,v)) / max(1e-9, math.sqrt(sum(x*x for x in q)*sum(x*x for x in v)))
                    return 3*cosine + memory["importance"]/10 + .995**(max(0, context["time"]-memory["accessed"])/3600)
                ranked = [{**m, "retrieval_score": round(score(m), 3), "retrieval_method": "semantic"} for m in candidates]
                context["memories"] = sorted(ranked, key=lambda m:(m["retrieval_score"],m["id"]), reverse=True)[:8]
                self.error = ""
                if len(self.cache) > 10000:
                    self.cache = {self.key(t): self.cache[self.key(t)] for t in texts}
        except Exception as exc:
            self.error = "Embeddings unavailable; lexical retrieval active (" + type(exc).__name__ + ")"
            self.retry_at = time.monotonic() + 60
        return context

    def status(self):
        return {"mode": "disabled" if not self.enabled else "semantic" if self.model and not self.error else "lexical",
                "model": self.model, "requests": self.calls, "request_limit":self.limit, "tokens": self.tokens, "cached": len(self.cache), "error": self.error}
