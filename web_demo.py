#!/usr/bin/env python3
"""Loopback-only web demo of a behavior-based board-move channel."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from demo import BOARD_SIZE, decode_moves, encode_message, legal_moves

MAX_REQUEST_BYTES = 4096

HTML_PATH = Path(__file__).with_name("index.html")


class APIError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class GameService:
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.lock = threading.Lock()
        self.active_game: dict | None = None
        self.records = self._load_records()

    def _load_records(self) -> list[dict]:
        if not self.storage_path.exists():
            return []
        try:
            records = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"cannot read local game history: {error}") from error
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise RuntimeError("local game history has an invalid format")
        return records

    def _save_records(self, records: list[dict]) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.write_text(
                json.dumps(records, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            raise APIError(500, f"could not save local game history: {error}") from error

    def start(self, message: str) -> dict:
        try:
            moves = encode_message(message)
        except ValueError as error:
            raise APIError(400, str(error)) from error

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        game = {
            "game_id": str(uuid.uuid4()),
            "created_at": now,
            "completed_at": None,
            "message": message,
            "moves": [list(move) for move in moves],
            "played_moves": [],
            "status": "in progress",
        }
        with self.lock:
            records = [*self.records, game]
            self._save_records(records)
            self.records = records
            self.active_game = {
                **game,
                "moves": moves,
                "board": [None] * (BOARD_SIZE * BOARD_SIZE),
            }
        return {
            "game_id": game["game_id"],
            "move_count": len(moves),
            "message_length": len(message),
        }

    def step(self, game_id: str) -> dict:
        with self.lock:
            if self.active_game is None or self.active_game["game_id"] != game_id:
                raise APIError(409, "no active game matches this game ID")
            if len(self.active_game["played_moves"]) >= len(self.active_game["moves"]):
                raise APIError(409, "this game is already complete")

            active = copy.deepcopy(self.active_game)
            position = len(active["played_moves"])
            move = active["moves"][position]
            choices = legal_moves(active["board"])
            rank = choices.index(move)
            label = f"{rank % 4:02b}"
            active["board"][move[0] * BOARD_SIZE + move[1]] = move
            active["played_moves"].append(list(move))

            record_index = next(
                index for index, record in enumerate(self.records)
                if record["game_id"] == game_id
            )
            records = copy.deepcopy(self.records)
            record = records[record_index]
            record["played_moves"] = active["played_moves"]
            complete = len(active["played_moves"]) == len(active["moves"])
            decoded = ""
            if complete:
                decoded = decode_moves(active["moves"])
                record["status"] = "complete"
                record["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

            self._save_records(records)
            self.records = records
            self.active_game = active

        decoded_so_far = decoded
        if not complete and len(active["played_moves"]) >= 4:
            complete_bytes = len(active["played_moves"]) // 4
            decoded_so_far = decode_moves(active["moves"][:complete_bytes * 4])
        return {
            "move": list(move),
            "position": position + 1,
            "rank": rank,
            "label": label,
            "legal_count": len(choices),
            "decoded": decoded_so_far,
            "complete": complete,
        }

    def history(self) -> list[dict]:
        with self.lock:
            return copy.deepcopy(self.records)


def make_handler(service: GameService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalMoveDemo/1.0"

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; "
                             "script-src 'unsafe-inline'; connect-src 'self'; "
                             "base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, value: dict | list) -> None:
            self._send(
                status,
                "application/json; charset=utf-8",
                json.dumps(value, ensure_ascii=True).encode("utf-8"),
            )

        def _read_json(self) -> dict:
            if self.headers.get_content_type() != "application/json":
                raise APIError(415, "request must use application/json")
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length or "")
            except ValueError as error:
                raise APIError(400, "invalid Content-Length") from error
            if length < 0 or length > MAX_REQUEST_BYTES:
                raise APIError(413, f"request body must be at most {MAX_REQUEST_BYTES} bytes")
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise APIError(400, "request body must be valid UTF-8 JSON") from error
            if not isinstance(value, dict):
                raise APIError(400, "request body must be a JSON object")
            return value

        def do_GET(self) -> None:
            route = urlsplit(self.path).path
            if route == "/":
                try:
                    page = HTML_PATH.read_bytes()
                except OSError as error:
                    self.log_error("could not read website file %s: %s", HTML_PATH, error)
                    self._json(500, {"error": "website file is unavailable"})
                    return
                self._send(200, "text/html; charset=utf-8", page)
            elif route == "/api/history":
                self._json(200, {"games": service.history()})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            route = urlsplit(self.path).path
            try:
                body = self._read_json()
                if route == "/api/start":
                    message = body.get("message")
                    if not isinstance(message, str):
                        raise APIError(400, "message must be a string")
                    self._json(201, service.start(message))
                elif route == "/api/step":
                    game_id = body.get("game_id")
                    if not isinstance(game_id, str):
                        raise APIError(400, "game_id must be a string")
                    self._json(200, service.step(game_id))
                else:
                    self._json(404, {"error": "not found"})
            except APIError as error:
                self._json(error.status, {"error": str(error)})

        def log_message(self, format: str, *args: object) -> None:
            sys.stderr.write(f"[local web demo] {self.address_string()} - {format % args}\n")

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the offline board-move demo as a loopback-only web app."
    )
    parser.add_argument("--port", type=int, default=8765, help="local HTTP port (default: 8765)")
    parser.add_argument(
        "--storage",
        type=Path,
        default=Path("demo_messages.json"),
        help="local JSON file for saved messages and game moves (default: demo_messages.json)",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    storage_path = args.storage.expanduser().resolve()
    try:
        service = GameService(storage_path)
    except RuntimeError as error:
        parser.error(str(error))

    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(service))
    except OSError as error:
        parser.error(f"could not start local server: {error}")
    print(f"Local demo available at http://127.0.0.1:{args.port}/")
    print(f"Messages and move histories will be stored in: {storage_path}")
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local demo.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
