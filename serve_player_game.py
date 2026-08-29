from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

from generate_player_game import DEFAULT_RUNTIME, generate_player_package
from player_game_package import GENERATOR_VERSION, package_id


class GameHandler(BaseHTTPRequestHandler):
    cache_dir: Path = ROOT / "out" / "player_cache"
    workshops: int = 3200
    catalogue_cap: int = 30000
    runtime_path: Path = DEFAULT_RUNTIME

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=31536000, immutable" if status == 200 else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {
                "ok": True,
                "generator_version": GENERATOR_VERSION,
                "runtime": self.runtime_path.name,
            })
            return
        if parsed.path != "/game":
            self._json(404, {"error": "not_found"})
            return
        query = parse_qs(parsed.query)
        player_key = (query.get("player_key") or [""])[0].strip()
        if not player_key:
            self._json(400, {"error": "player_key_required"})
            return
        if len(player_key) > 512:
            self._json(400, {"error": "player_key_too_long"})
            return

        pid = package_id(player_key)
        cache_path = self.cache_dir / GENERATOR_VERSION / f"{pid}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            payload = generate_player_package(
                player_key,
                output_path=cache_path,
                workshops=self.workshops,
                catalogue_cap=self.catalogue_cap,
                runtime=self.runtime_path,
                include_debug=False,
            )
        self._json(200, payload)

    def log_message(self, fmt: str, *args: object) -> None:
        # Do not print player keys from request URLs into ordinary logs.
        path = urlparse(self.path).path
        sys.stderr.write(f"{self.address_string()} {path} {args[1] if len(args) > 1 else ''}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve deterministic player-safe archaeology careers over a tiny HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    parser.add_argument(
        "--runtime",
        type=Path,
        default=DEFAULT_RUNTIME,
        help="Compact player runtime; defaults to cache/atolia_runtime_v2.nc.",
    )
    args = parser.parse_args()
    GameHandler.workshops = args.workshops
    GameHandler.catalogue_cap = args.catalogue_cap
    GameHandler.runtime_path = args.runtime if args.runtime.is_absolute() else ROOT / args.runtime
    server = ThreadingHTTPServer((args.host, args.port), GameHandler)
    print(json.dumps({
        "listen": f"http://{args.host}:{args.port}",
        "generator_version": GENERATOR_VERSION,
        "runtime": str(GameHandler.runtime_path),
    }))
    server.serve_forever()


if __name__ == "__main__":
    main()
