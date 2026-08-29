"""Parse Oberon spdlog daily-logger files into classified events."""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from spec import Spec

LOG_RE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2}) ([+\-]\d{2}:\d{2})\] "
    r"\[(\w+)\] "
    r"\[---([TDIWEC])---\] "
    r"\[thread (\d+)\] ?(.*)$"
)
DATE_IN_NAME = re.compile(r"(?:tha_)?log_file_(\d{4}-\d{2}-\d{2})")
CST = timezone(timedelta(hours=8))

MAX_EVENTS_PAYLOAD = 50_000

START_OP = "start operation"
EXIT_APP = "Oberon Application Exit"
STARTUP_APP = "Oberon Application Startup"
END_SURGERY = "enter poster operation page"


def extract_date_from_name(name: str) -> str | None:
    m = DATE_IN_NAME.search(name)
    return m.group(1) if m else None


def date_from_mtime(path: Path) -> str:
    ts = datetime.fromtimestamp(path.stat().st_mtime, CST)
    return ts.strftime("%Y-%m-%d")


def resolve_file_date(path: Path, original_name: str | None = None) -> tuple[str | None, str]:
    name = original_name or path.name
    d = extract_date_from_name(name)
    if d:
        return d, "filename"
    try:
        return date_from_mtime(path), "mtime"
    except OSError:
        return None, "unknown"


def parse_log_lines(lines: list[str], file_date: str | None) -> list[dict]:
    events: list[dict] = []
    pending: list[tuple[int, str]] = []
    last_time = None
    last_tz = None
    last_thread = None

    def flush_unmatched() -> None:
        nonlocal pending
        if not pending:
            return
        while pending and not pending[0][1].strip():
            pending.pop(0)
        while pending and not pending[-1][1].strip():
            pending.pop()
        if not pending:
            return
        start = pending[0][0]
        end = pending[-1][0]
        body = [p[1] for p in pending]
        raw = "\n".join(body)
        first = body[0]
        events.append(
            {
                "line": start,
                "line_end": end,
                "time": last_time,
                "tz": last_tz,
                "date": file_date,
                "level": None,
                "thread": last_thread,
                "logger": None,
                "message": first[:240],
                "raw": raw,
                "parsed": False,
                "block": True,
            }
        )
        pending = []

    for i, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip("\n\r")
        m = LOG_RE.match(line)
        if m:
            flush_unmatched()
            hhmmss, tz, logger, level, thread, message = m.groups()
            last_time, last_tz, last_thread = hhmmss, tz, thread
            events.append(
                {
                    "line": i,
                    "line_end": i,
                    "time": hhmmss,
                    "tz": tz,
                    "date": file_date,
                    "level": level,
                    "thread": thread,
                    "logger": logger,
                    "message": message,
                    "raw": line,
                    "parsed": True,
                    "block": False,
                }
            )
        else:
            pending.append((i, line))
    flush_unmatched()
    return events


def _session_flag(step: str, category: str) -> str | None:
    if category != "lifecycle":
        return None
    s = step or ""
    if "退出" in s:
        return "exit"
    if "启动" in s and "版本" not in s:
        return "startup"
    return None


def classify_events(events: list[dict], spec: Spec) -> list[dict]:
    spec.maybe_reload()
    current_group = ""
    current_page = ""
    in_surgery = False
    out = []
    for ev in events:
        msg = ev.get("message") or ""
        if STARTUP_APP in msg:
            in_surgery = False
        if START_OP in msg:
            in_surgery = True
        cls = spec.classify(msg, ev.get("raw") or "", ev.get("level"))

        if "kuka app is disconnected" in msg.lower():
            if in_surgery:
                cls["mark"] = "anomaly"
                cls["timeline"] = "show"
                cls["step"] = "KUKA 断开"
            else:
                cls["mark"] = "none"
                cls["timeline"] = "hide"
                cls["step"] = "KUKA 断开（非术中）"

        if EXIT_APP in msg or END_SURGERY in msg:
            in_surgery = False

        step = cls["step"]
        cat = cls["category"]
        if cat == "page" and cls["timeline"] == "show" and step:
            current_page = step
        if cat in ("lifecycle", "page", "step") and cls["timeline"] == "show" and step:
            current_group = step
        sess = _session_flag(step, cat)
        item = dict(ev)
        item.update(
            {
                "step": step,
                "category": cat,
                "timeline": cls["timeline"],
                "mark": cls["mark"],
                "source": cls["source"],
                "rule": cls["rule"],
                "group": current_group or step,
                "page": current_page,
                "session": sess,
                "value_mm": cls.get("value_mm"),
                "threshold": cls.get("threshold"),
            }
        )
        out.append(item)
    return out


def summarize(events: list[dict]) -> dict:
    total = len(events)
    key = anomaly = noise = unmatched = shown = parsed = 0
    start = end = None
    for ev in events:
        if ev.get("parsed"):
            parsed += 1
        if ev.get("time"):
            if start is None:
                start = ev["time"]
            end = ev["time"]
        mark = ev.get("mark")
        src = ev.get("source")
        if mark == "key":
            key += 1
        if mark == "anomaly":
            anomaly += 1
        if src == "noise" or ev.get("category") == "noise":
            noise += 1
        if src == "unmatched":
            unmatched += 1
        if ev.get("timeline") == "show":
            shown += 1
    return {
        "total": total,
        "parsed": parsed,
        "unmatched_blocks": total - parsed,
        "key": key,
        "anomaly": anomaly,
        "noise": noise,
        "unmatched": unmatched,
        "shown": shown,
        "hidden_noise": noise,
        "start_time": start,
        "end_time": end,
    }


def filter_events(events: list[dict], show_noise: bool = False, show_all: bool = False) -> list[dict]:
    if show_all:
        return events
    out = []
    for ev in events:
        if ev.get("source") == "unmatched":
            continue
        if (ev.get("source") == "noise" or ev.get("category") == "noise") and not show_noise:
            if ev.get("mark") == "anomaly":
                out.append(ev)
            continue
        if ev.get("timeline") == "show" or ev.get("mark") in ("key", "anomaly"):
            out.append(ev)
        elif show_noise:
            out.append(ev)
    return out


def to_public_event(ev: dict, idx: int) -> dict:
    return {
        "i": idx,
        "line": ev["line"],
        "line_end": ev.get("line_end") or ev["line"],
        "time": ev.get("time"),
        "tz": ev.get("tz"),
        "date": ev.get("date"),
        "level": ev.get("level"),
        "thread": ev.get("thread"),
        "message": ev.get("message") or "",
        "raw": ev.get("raw") or "",
        "step": ev.get("step") or "",
        "category": ev.get("category") or "other",
        "timeline": ev.get("timeline") or "hide",
        "mark": ev.get("mark") or "none",
        "source": ev.get("source") or "",
        "group": ev.get("group") or "",
        "page": ev.get("page") or "",
        "session": ev.get("session"),
        "value_mm": ev.get("value_mm"),
        "threshold": ev.get("threshold"),
        "block": bool(ev.get("block")),
        "hlevel": ev.get("hlevel"),
    }


def parse_and_classify(path: Path, spec: Spec, original_name: str | None = None) -> tuple[list[dict], dict]:
    file_date, date_source = resolve_file_date(path, original_name)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    raw_events = parse_log_lines(lines, file_date)
    events = classify_events(raw_events, spec)
    meta = summarize(events)
    meta["line_count"] = len(lines)
    meta["date"] = file_date
    meta["date_source"] = date_source
    meta["size"] = path.stat().st_size
    return events, meta
