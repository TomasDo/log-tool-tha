"""Imported log files on disk (data/logs + data/index.json)."""

from __future__ import annotations

import json
import hashlib
import threading
from functools import wraps
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOGS_DIR = DATA_DIR / "logs"
INDEX_PATH = DATA_DIR / "index.json"
CST = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)

    return call


class Store:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.logs_dir = self.data_dir / "logs"
        self.index_path = self.data_dir / "index.json"
        self.lock = threading.RLock()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if not self.index_path.exists():
            return {"logs": []}
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"logs": []}

    def _save(self, data: dict) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    def list_logs(self) -> list[dict]:
        logs = list(self._load().get("logs") or [])
        logs.sort(
            key=lambda x: (
                x.get("date") or "",
                x.get("start_time") or "",
                x.get("imported_at") or "",
            ),
            reverse=True,
        )
        return logs

    def get(self, log_id: str) -> dict | None:
        for item in self._load().get("logs") or []:
            if item.get("id") == log_id:
                return item
        return None

    def stored_path(self, item: dict) -> Path:
        return self.logs_dir / item["stored_name"]

    @locked
    def add(self, original_name: str, content: bytes, meta: dict) -> dict:
        size = meta.get("size") or len(content)
        data = self._load()
        digest = hashlib.sha256(content).hexdigest()
        for rec in data.get("logs") or []:
            if not rec.get("sha256"):
                old = self.stored_path(rec)
                if old.is_file():
                    rec["sha256"] = hashlib.sha256(old.read_bytes()).hexdigest()
            if rec.get("sha256") == digest:
                aliases = rec.setdefault("aliases", [])
                if (
                    original_name != rec["original_name"]
                    and original_name not in aliases
                ):
                    aliases.append(original_name)
                self._save(data)
                return {**rec, "duplicate": True}
        log_id = uuid.uuid4().hex
        suffix = Path(original_name).suffix or ".txt"
        stored_name = f"{log_id}{suffix}"
        dest = self.logs_dir / stored_name
        dest.write_bytes(content)
        rec = {
            "id": log_id,
            "original_name": original_name,
            "stored_name": stored_name,
            "size": size,
            "sha256": digest,
            "source_mtime": meta.get("source_mtime"),
            "file_quality": meta.get("file_quality"),
            "line_count": meta.get("line_count", 0),
            "parsed_count": meta.get("parsed", 0),
            "date": meta.get("date"),
            "date_source": meta.get("date_source"),
            "start_time": meta.get("start_time"),
            "end_time": meta.get("end_time"),
            "counts": {
                "total": meta.get("total", 0),
                "key": meta.get("key", 0),
                "anomaly": meta.get("anomaly", 0),
                "noise": meta.get("noise", 0),
                "shown": meta.get("shown", 0),
            },
            "imported_at": _now(),
        }
        data.setdefault("logs", []).append(rec)
        self._save(data)
        return rec

    @locked
    def update_meta(self, log_id, meta):
        data = self._load()
        for rec in data.get("logs", []):
            if rec["id"] == log_id:
                for key in (
                    "date",
                    "date_source",
                    "file_quality",
                    "start_time",
                    "end_time",
                ):
                    if (
                        key not in ("date", "date_source")
                        or meta.get("date") is not None
                    ):
                        rec[key] = meta.get(key)
                rec["counts"] = {
                    key: meta.get(key, 0)
                    for key in ("total", "key", "anomaly", "noise", "shown")
                }
        self._save(data)

    def add_from_path(self, src: Path, original_name: str | None, meta: dict) -> dict:
        return self.add(original_name or src.name, src.read_bytes(), meta)

    @locked
    def delete(self, log_id: str) -> bool:
        data = self._load()
        logs = data.get("logs") or []
        kept = []
        found = None
        for item in logs:
            if item.get("id") == log_id:
                found = item
            else:
                kept.append(item)
        if found is None:
            return False
        path = self.logs_dir / found["stored_name"]
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
        data["logs"] = kept
        self._save(data)
        return True
