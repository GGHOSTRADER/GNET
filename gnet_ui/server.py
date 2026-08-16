"""Local-only browser UI for the directory-backed model registry."""

from __future__ import annotations

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re

from inference.model_registry import (
    RegistryError,
    discover_registry,
    update_registry_entry,
)


HOST = "127.0.0.1"
PORT = 9020
_STRATEGY_ROUTE = re.compile(r"^/api/strategies/([A-Za-z0-9_.-]{1,64})$")
_STATIC_DIR = Path(__file__).with_name("static")


def _entry_payload(entry) -> dict:
    data = asdict(entry)
    data["artifact_dir"] = str(entry.artifact_dir)
    data["registry_file"] = str(entry.registry_file)
    return data


class RegistryHandler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            body = (_STATIC_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/strategies":
            entries, errors = discover_registry()
            self._json(
                200,
                {"strategies": [_entry_payload(entry) for entry in entries], "errors": errors},
            )
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        matched = _STRATEGY_ROUTE.fullmatch(self.path)
        if not matched:
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4_096:
                raise RegistryError("invalid request size")
            changes = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(changes, dict):
                raise RegistryError("request body must be an object")
            entry = update_registry_entry(matched.group(1), changes)
        except (RegistryError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(200, {"strategy": _entry_payload(entry), "restart_required": True})

    def log_message(self, format: str, *args) -> None:
        print(f"[registry_ui] {self.address_string()} {format % args}")


def run() -> None:
    print(f"[registry_ui] Open http://{HOST}:{PORT}")
    with ThreadingHTTPServer((HOST, PORT), RegistryHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    run()
