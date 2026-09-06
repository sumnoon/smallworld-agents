"""Local HTTP/SSE transport using only the Python standard library."""
import argparse
import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

from .world import World, CommandError, ROOT


def load_environment():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                if name.strip() in ("AGENT_PROVIDER", "AGENT_MODEL", "OPENAI_API_KEY", "AGENT_MAX_REQUESTS", "OLLAMA_BASE_URL", "AGENT_MODEL_TIMEOUT"):
                    os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


class SimulationHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, world):
        super().__init__(address, Handler)
        self.world = world
        self.stopping = threading.Event()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def allowed_host(self):
        return urlsplit("http://" + self.headers.get("Host", "")).hostname in ("127.0.0.1", "localhost")

    def send_json(self, value, code=200):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.allowed_host():
            self.send_json({"error": "Local access only"}, 403)
            return
        path = unquote(urlsplit(self.path).path)
        if path == "/api/state":
            self.send_json(self.server.world.snapshot())
        elif path == "/api/layout":
            self.send_json(self.server.world.layout)
        elif path.startswith("/api/agents/"):
            try:
                self.send_json(self.server.world.inspect(path.rsplit("/", 1)[-1]))
            except CommandError as exc:
                self.send_json({"error": str(exc)}, 404)
        elif path == "/api/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                while not self.server.stopping.is_set():
                    self.wfile.write(("data: " + json.dumps(self.server.world.snapshot()) + "\n\n").encode())
                    self.wfile.flush()
                    self.server.stopping.wait(.2)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            self.close_connection = True
        else:
            # Deliberate allowlist: never serve .env, SQLite, source config or arbitrary workspace files.
            if path == "/":
                file = ROOT / "client/index.html"
            elif path.startswith(("/client/", "/assets/")):
                file = (ROOT / path.lstrip("/")).resolve()
                allowed = [ROOT / "client", ROOT / "assets"]
                if not any(file.is_relative_to(folder) for folder in allowed) or file.suffix.lower() not in (".html", ".js", ".css", ".png", ".svg", ".json", ".ico"):
                    self.send_json({"error": "Not found"}, 404)
                    return
            else:
                self.send_json({"error": "Not found"}, 404)
                return
            if not file.is_file():
                self.send_json({"error": "Not found"}, 404)
                return
            raw = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(file)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if not self.allowed_host() or (origin and urlsplit(origin).netloc != self.headers.get("Host")):
            self.send_json({"error": "Same-origin local commands only"}, 403)
            return
        if urlsplit(self.path).path != "/api/command":
            self.send_json({"error": "Not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise CommandError("Command too large or empty")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise CommandError("Command must be a JSON object")
            self.send_json(self.server.world.command(data))
        except (ValueError, UnicodeDecodeError) as exc:
            self.send_json({"error": str(exc)[:250]}, 400)


def run(port=8766, database=None):
    load_environment()
    if database is None:
        (ROOT / "data").mkdir(exist_ok=True)
        database = ROOT / "data/neighborhood.sqlite3"
    world = World(database)
    server = SimulationHTTPServer(("127.0.0.1", port), world)

    def clock():
        last = time.monotonic()
        save_at = last + 5
        while not server.stopping.wait(.1):
            now = time.monotonic()
            try:
                world.tick(now - last)
                if now >= save_at:
                    world.save()
                    save_at = now + 5
            except Exception as exc:
                # Keep the interface reachable so a runtime failure is visible.
                with world.lock:
                    world.paused = True
                    world.event("system", "error", "Simulation paused after an internal error: " + type(exc).__name__)
            last = now

    ticker = threading.Thread(target=clock, name="world-clock", daemon=True)
    ticker.start()
    print(f"Smallworld Agents is running at http://127.0.0.1:{port}", flush=True)
    print("Mode: " + world.cognition.mode + ". Press Ctrl+C to save and stop.", flush=True)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.stopping.set()
        ticker.join(timeout=2)
        server.server_close()
        world.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local isometric neighborhood")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    run(args.port, args.database)
