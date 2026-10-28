"""Parse Oberon spdlog daily-logger files into classified events."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from spec import Spec

LOG_RE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2}) ([+\-]\d{2}:?\d{2})\] "
    r"\[(\w+)\] "
    r"\[---([TDIWEC])---\] "
    r"\[thread (\d+)\] ?(.*)$"
)
DATE_IN_NAME = re.compile(r"(?:tha_)?log_file_(\d{4}-\d{2}-\d{2})")
CST = timezone(timedelta(hours=8))

MAX_EVENTS_PAYLOAD = 50_000

STARTUP_APP = "Oberon Application Startup"


def extract_date_from_name(name: str) -> str | None:
    m = DATE_IN_NAME.search(name)
    return m.group(1) if m else None


def date_from_mtime(path: Path) -> str:
    ts = datetime.fromtimestamp(path.stat().st_mtime, CST)
    return ts.strftime("%Y-%m-%d")


def resolve_file_date(
    path: Path, original_name: str | None = None
) -> tuple[str | None, str]:
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
        m = LOG_RE.match(line.lstrip("\ufeff"))
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
    merged = []
    for ev in events:
        crash = bool(
            re.search(
                r"(?m)^(?:[= ]*CRASH DETECTED[= ]*|Caught signal\s+\d+\b[^\n]*)$",
                ev["raw"],
            )
        )
        if (
            crash
            and merged
            and merged[-1].get("level") in ("E", "C")
            and not merged[-1]["message"].strip()
        ):
            header = merged.pop()
            header.update(
                line_end=ev["line_end"],
                raw=header["raw"] + "\n" + ev["raw"],
                message=ev["message"],
                block=True,
            )
            merged.append(header)
        else:
            merged.append(ev)
    return merged


def inspect_content(content: bytes) -> dict:
    text = content.decode("utf-8", errors="replace")
    if not content or not text.strip("\ufeff\x00 \r\n\t"):
        raise ValueError("日志为空或全部为零字节，无法分析")
    if "Titan Application Startup" in text:
        raise ValueError("检测到 Titan 日志，本工具仅分析 Oberon")
    oberon = any(
        token in text
        for token in (
            "Oberon Application Startup",
            "start load plan uuid",
            "switch register hip step",
            "hip register calculate error",
            "ras coordinate realtime",
            "app coordinate realtime",
            "switch polish hip step",
            "switch install hip cup step",
        )
    )
    warnings = []
    if not oberon:
        warnings.append("无法确认是 Oberon 日志，仅供原文查看")
    elif STARTUP_APP not in text:
        warnings.append("日志片段缺少软件启动行，记录可能不完整")
    if "\x00" in text:
        warnings.append("文件包含零字节，部分记录可能损坏")
    return {
        "product": "oberon" if oberon else "unknown",
        "analyzable": oberon,
        "partial": oberon and STARTUP_APP not in text,
        "warnings": warnings,
    }


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
    manual_restart = None
    out = []
    classes = [
        spec.classify(e.get("message") or "", e.get("raw") or "", e.get("level"))
        for e in events
    ]
    for i, (ev, cls) in enumerate(zip(events, classes)):
        eid = cls.get("event_id")
        error_level = ev.get("level") in ("E", "C")
        if eid in ("startup", "plan_load"):
            in_surgery = False
            manual_restart = None
            current_group = current_page = ""
        if eid == "operation_start":
            in_surgery = True
            manual_restart = None
        if eid == "sirius_manual_restart":
            manual_restart = ev["line"]
        if eid == "kuka_disconnected":
            if not error_level and (manual_restart is not None or not in_surgery):
                reason = (
                    f"此前有人工重启请求（行 {manual_restart}），断开记录保留为提醒；未证明连接已恢复"
                    if manual_restart is not None
                    else "本区间未记录明确的手术开始，断开状态保留为提醒，不推断为术中故障"
                )
                cls.update(mark="key", timeline="show", notes=reason)
            manual_restart = None
        if eid == "mxio_fault" and not error_level:
            for following, next_cls in zip(events[i + 1 :], classes[i + 1 :]):
                next_id = next_cls.get("event_id")
                if next_id in (
                    "startup",
                    "plan_load",
                    "operation_start",
                    "exit",
                    "crash",
                    "mxio_fault",
                    "mxio_normal",
                ):
                    break
                if next_id == "teach_custom" and following.get("level") not in (
                    "E",
                    "C",
                ):
                    cls.update(
                        mark="key",
                        timeline="show",
                        step="MXIO 连接失败，启用替代模块监听",
                        notes=f"行 {following['line']} 记录启用自定义示教模块监听；属于已记录的回退流程，不代表模块已连接或示教可用",
                    )
                    break
        if eid == "emergency_pressed" and not in_surgery and not error_level:
            cls.update(
                mark="key",
                timeline="show",
                notes="急停按下状态；本区间未记录手术开始，保留为安全状态提醒，不直接认定软件故障",
            )
        if eid in (
            "kuka_connected",
            "devices_normal",
            "kuka_fault",
            "ndi_fault",
            "devices_fault",
            "exit",
            "crash",
            "page_postop",
        ):
            manual_restart = None
        if eid in ("exit", "page_postop", "crash"):
            in_surgery = False

        step = cls["step"]
        cat = cls["category"]
        if cat == "page" and cls["timeline"] == "show" and step:
            current_page = step
        if cat in ("lifecycle", "page", "step") and cls["timeline"] == "show" and step:
            current_group = step
        sess = {"startup": "startup", "exit": "exit"}.get(cls.get("event_id"))
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
                "event_id": cls.get("event_id", ""),
                "limits": dict(spec.limits),
                "requirements": spec.requirements,
                "track": cls.get("track", ""),
                "parent": cls.get("parent", ""),
                "notes": cls.get("notes", ""),
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


def filter_events(
    events: list[dict], show_noise: bool = False, show_all: bool = False
) -> list[dict]:
    if show_all:
        return events
    out = []
    for ev in events:
        if ev.get("source") == "unmatched":
            continue
        if (
            ev.get("source") == "noise" or ev.get("category") == "noise"
        ) and not show_noise:
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
        **{
            k: ev.get(k)
            for k in (
                "event_id",
                "session_id",
                "case_id",
                "context",
                "metrics",
                "notes",
                "threshold",
            )
        },
    }


def parse_and_classify(
    path: Path,
    spec: Spec,
    original_name: str | None = None,
    source_mtime: float | None = None,
) -> tuple[list[dict], dict]:
    file_date, date_source = resolve_file_date(path, original_name)
    content = path.read_bytes()
    quality = inspect_content(content)
    if not extract_date_from_name(original_name or path.name):
        file_date = (
            datetime.fromtimestamp(source_mtime, CST).strftime("%Y-%m-%d")
            if source_mtime is not None
            else None
        )
        date_source = "mtime" if source_mtime is not None else "unknown"
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()
    raw_events = parse_log_lines(lines, file_date)
    events = classify_events(raw_events, spec)
    if quality["analyzable"]:
        from nle import collect_cut_deltas

        collect_cut_deltas(events)
    else:
        events = []
    meta = summarize(events)
    meta["file_quality"] = quality
    meta["line_count"] = len(lines)
    meta["date"] = file_date
    meta["date_source"] = date_source
    meta["size"] = path.stat().st_size
    return events, meta
