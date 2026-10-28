#!/usr/bin/env python3
"""Oberon log analysis server — stdlib http.server, bind 0.0.0.0:8765."""

from __future__ import annotations

import json
import os
import re
import tempfile
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from nle import build_nle  # noqa: E402
from parser import (  # noqa: E402
    MAX_EVENTS_PAYLOAD,
    filter_events,
    parse_and_classify,
    to_public_event,
    summarize,
)
from spec import Spec  # noqa: E402
from store import Store  # noqa: E402

WEB_DIR = ROOT / "web"
HOST = "0.0.0.0"
PORT = 8765
MAX_UPLOAD = 80 * 1024 * 1024

SPEC = Spec()
STORE = Store(
    Path(os.environ["LOG_TOOL_DATA_DIR"])
    if os.environ.get("LOG_TOOL_DATA_DIR")
    else None
)

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
}


def _json_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _parse_multipart(body: bytes, content_type: str) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    if "boundary=" not in content_type:
        return files
    boundary = content_type.split("boundary=", 1)[1].strip().strip('"').encode("utf-8")
    marker = b"--" + boundary
    parts = body.split(marker)
    for part in parts:
        if not part or part in (b"--", b"--\r\n"):
            continue
        if part.startswith(b"--"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        header_blob, sep, content = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        if content.endswith(b"\r\n"):
            content = content[:-2]
        headers = {}
        for line in header_blob.decode("utf-8", errors="replace").split("\r\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        disp = headers.get("content-disposition", "")
        filename = ""
        for chunk in disp.split(";"):
            chunk = chunk.strip()
            if chunk.lower().startswith("filename="):
                filename = chunk.split("=", 1)[1].strip().strip('"')
        if not filename:
            continue
        files.append((filename, content))
    return files


class Handler(BaseHTTPRequestHandler):
    server_version = "OberonLogTool/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(
        self, code: int, body: bytes, content_type: str, extra: dict | None = None
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, _json_bytes(obj), "application/json; charset=utf-8")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return b""
        return self.rfile.read(length) if length else b""

    def do_HEAD(self) -> None:
        self.do_GET(head_only=True)

    def do_GET(self, head_only: bool = False) -> None:
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            qs = parse_qs(parsed.query)
            if path.startswith("/api/"):
                self._api_get(path, qs)
                return
            self._static(path)
        except Exception as exc:
            traceback.print_exc()
            self._json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            self._api_post(path)
        except Exception as exc:
            traceback.print_exc()
            self._json(500, {"error": str(exc)})

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            self._api_delete(path)
        except Exception as exc:
            traceback.print_exc()
            self._json(500, {"error": str(exc)})

    def _static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"
        rel = path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() not in target.parents and target != WEB_DIR.resolve():
            self._json(403, {"error": "forbidden"})
            return
        if not target.is_file():
            self._json(404, {"error": "not found"})
            return
        data = target.read_bytes()
        ctype = MIME.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, data, ctype)

    def _api_get(self, path: str, qs: dict) -> None:
        SPEC.maybe_reload()
        if path == "/api/health":
            self._json(200, {"ok": True, "spec": SPEC.counts()})
            return
        if path == "/api/spec":
            self._json(
                200,
                {
                    "ok": SPEC.error is None,
                    "counts": SPEC.counts(),
                    "mtime": SPEC.mtime,
                    "rules": {
                        "anomaly": [r["match"] for r in SPEC.anomaly],
                        "noise": [r["match"] for r in SPEC.noise],
                        "mapping": [r["match"] for r in SPEC.mapping],
                        "key": [r["match"] for r in SPEC.key],
                        "operation": [r["match"] for r in SPEC.operation],
                    },
                },
            )
            return
        if path == "/api/logs":
            logs = STORE.list_logs()
            for rec in logs:
                try:
                    _, meta = parse_and_classify(
                        STORE.stored_path(rec),
                        SPEC,
                        rec.get("original_name"),
                        rec.get("source_mtime"),
                    )
                    rec["counts"] = {
                        key: meta.get(key, 0)
                        for key in ("total", "key", "anomaly", "noise", "shown")
                    }
                    rec["file_quality"] = meta["file_quality"]
                except (OSError, ValueError) as exc:
                    rec["file_quality"] = {"analyzable": False, "warnings": [str(exc)]}
                    rec["counts"] = {}
            self._json(200, {"logs": logs})
            return
        parts = path.strip("/").split("/")
        # /api/logs/{id} or /api/logs/{id}/timeline
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "logs":
            log_id = parts[2]
            rec = STORE.get(log_id)
            if rec is None:
                self._json(404, {"error": "log not found"})
                return
            if len(parts) == 3:
                self._json(200, rec)
                return
            if len(parts) == 4 and parts[3] == "timeline":
                self._timeline(rec, qs)
                return
        self._json(404, {"error": "unknown api"})

    def _timeline(self, rec: dict, qs: dict) -> None:
        show_noise = (qs.get("show_noise") or ["0"])[0] in ("1", "true", "yes")
        show_all = (qs.get("show_all") or ["0"])[0] in ("1", "true", "yes")
        path = STORE.stored_path(rec)
        if not path.is_file():
            self._json(404, {"error": "stored file missing"})
            return
        try:
            events, meta = parse_and_classify(
                path, SPEC, rec.get("original_name"), rec.get("source_mtime")
            )
        except ValueError as exc:
            self._json(422, {"error": str(exc)})
            return
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        raw_lines = raw_text.splitlines()
        center = window = None
        try:
            if qs.get("center"):
                center = int((qs.get("center") or ["0"])[0])
        except ValueError:
            center = None
        try:
            if qs.get("window"):
                window = int((qs.get("window") or ["0"])[0])
        except ValueError:
            window = None
        search = (qs.get("q") or [""])[0].casefold()
        direction = (qs.get("direction") or ["next"])[0]
        after = int((qs.get("after") or ["0"])[0])
        matches = [
            i
            for i, raw in enumerate(raw_lines, 1)
            if search and search in raw.casefold()
        ]
        candidates = reversed(matches) if direction == "prev" else iter(matches)
        target = next(
            (
                i
                for i in candidates
                if (i < after if direction == "prev" else i > after)
            ),
            None,
        )
        if matches and target is None:
            target = matches[-1] if direction == "prev" else matches[0]
        if target:
            center = target
        nle = build_nle(events, raw_lines, center=center, window=window)
        meta.update(summarize(events))
        STORE.update_meta(rec["id"], meta)
        visible = filter_events(events, show_noise=show_noise, show_all=show_all)
        truncated = False
        total = len(events)
        if total > MAX_EVENTS_PAYLOAD and not show_all:
            visible = filter_events(events, show_noise=False, show_all=False)
            truncated = True
        if len(visible) > MAX_EVENTS_PAYLOAD:
            visible = visible[:MAX_EVENTS_PAYLOAD]
            truncated = True
        payload = {
            "id": rec["id"],
            "name": rec.get("original_name"),
            "date": meta.get("date") or rec.get("date"),
            "date_source": meta.get("date_source"),
            "start_time": meta.get("start_time"),
            "end_time": meta.get("end_time"),
            "counts": {
                "total": meta["total"],
                "parsed": meta["parsed"],
                "key": meta["key"],
                "anomaly": meta["anomaly"],
                "noise": meta["noise"],
                "unmatched": meta["unmatched"],
                "shown": meta["shown"],
                "hidden_noise": meta["noise"],
                "returned": len(visible),
            },
            "search": {"total": len(matches), "line": target},
            "truncated": truncated,
            "filtered_default": not show_all,
            "spec": SPEC.counts(),
            "file_quality": meta["file_quality"],
            "events": [to_public_event(ev, i) for i, ev in enumerate(visible)],
            "line_count": nle["line_count"],
            "lines": nle["lines"],
            "lines_windowed": nle["lines_windowed"],
            "lines_start": nle["lines_start"],
            "lines_end": nle["lines_end"],
            "ticks": nle["ticks"],
            "tracks": nle["tracks"],
            "summaries": nle.get("summaries") or [],
        }
        self._json(200, payload)

    def _import_one(self, name, content, source_path=None, source_mtime=None):
        if source_path is not None:
            source_mtime = source_path.stat().st_mtime
        with tempfile.NamedTemporaryFile(dir=STORE.logs_dir, suffix=".txt") as tmp:
            tmp.write(content)
            tmp.flush()
            events, meta = parse_and_classify(Path(tmp.name), SPEC, name, source_mtime)
        meta["source_mtime"] = source_mtime
        rec = STORE.add(name, content, meta)
        rec["_preview"] = {
            key: meta.get(key, 0) for key in ("total", "key", "anomaly", "noise")
        }
        return rec

    def _api_post(self, path: str) -> None:
        SPEC.maybe_reload()
        if path == "/api/spec/reload":
            SPEC.reload(force=True)
            self._json(200, {"ok": SPEC.error is None, "counts": SPEC.counts()})
            return
        if path == "/api/logs":
            ctype = self.headers.get("Content-Type") or ""
            body = self._read_body()
            if not body:
                self._json(400, {"error": "empty body or too large"})
                return
            files = _parse_multipart(body, ctype)
            if not files:
                self._json(400, {"error": "no files in upload"})
                return
            # Browser sends per-file original lastModified in milliseconds.
            encoded = re.search(rb'name="last_modified"\r\n\r\n([^\r\n]+)', body)
            try:
                modified = json.loads(encoded[1]) if encoded else {}
            except (ValueError, TypeError):
                modified = {}
            imported = []
            errors = []
            for name, content in files:
                try:
                    imported.append(
                        self._import_one(
                            name,
                            content,
                            source_mtime=(
                                float(modified[name]) / 1000
                                if modified.get(name) is not None
                                else None
                            ),
                        )
                    )
                except Exception as exc:
                    errors.append({"name": name, "error": str(exc)})
            self._json(200, {"imported": imported, "errors": errors})
            return
        if path == "/api/logs/import-path":
            body = self._read_body()
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid json"})
                return
            paths = data.get("paths") or []
            if data.get("path"):
                paths = [data["path"]] + list(paths)
            if not paths:
                self._json(400, {"error": "path required"})
                return
            imported = []
            errors = []
            for p in paths:
                src = Path(p).expanduser()
                if not src.is_file():
                    errors.append({"path": p, "error": "not a file"})
                    continue
                try:
                    imported.append(self._import_one(src.name, src.read_bytes(), src))
                except Exception as exc:
                    errors.append({"path": p, "error": str(exc)})
            self._json(200, {"imported": imported, "errors": errors})
            return
        self._json(404, {"error": "unknown api"})

    def _api_delete(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "logs":
            ok = STORE.delete(parts[2])
            if not ok:
                self._json(404, {"error": "log not found"})
                return
            self._json(200, {"ok": True, "id": parts[2]})
            return
        self._json(404, {"error": "unknown api"})


def serve(host: str = HOST, port: int = PORT) -> None:
    SPEC.maybe_reload()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(
        f"Oberon log tool  http://{host}:{port}  spec={SPEC.path}  rules={SPEC.counts()}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstop", flush=True)
        httpd.server_close()


if __name__ == "__main__":
    host, port = HOST, PORT
    args = sys.argv[1:]
    if args:
        if ":" in args[0]:
            host, p = args[0].rsplit(":", 1)
            port = int(p)
        else:
            port = int(args[0])
    serve(host, port)
