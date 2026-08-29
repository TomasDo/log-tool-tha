"""NLE-style timeline spans: cases/sessions + L1/L2/L3 page tracks.

X axis is log line number. Hierarchy matching is hardcoded from
docs/page-hierarchy.md (not the spec business-order table).
"""
from __future__ import annotations

import re
from typing import Any

from parser import LOG_RE

UUID_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)
CUP_TYPE_RE = re.compile(r"switch cup type:\s*(\S+)", re.I)
SIDE_RE = re.compile(r"operation side\s+(left|right|l|r|左|右)", re.I)
VERSION_RE = re.compile(r"Oberon Application Startup\s+version\s+(\S+)", re.I)
PROBE_ERR_RE = re.compile(r"probe calibration error\s+([0-9.]+)", re.I)
EFFECTOR_ERR_RE = re.compile(r"effector calibration error\s+([0-9.]+)", re.I)
HIP_REG_ERR_RE = re.compile(r"hip register calculate error\s+([0-9.]+)", re.I)
PLAN_RE = re.compile(
    r"planviewer hand over,plan inclination:\s*([+-]?(?:\d+\.?\d*|\.\d+))"
    r"\s*,\s*plan anterversion:\s*([+-]?(?:\d+\.?\d*|\.\d+))",
    re.I,
)
RAS_RE = re.compile(
    r"ras coordinate realtime anteversion:\s*([+-]?(?:\d+\.?\d*|\.\d+))"
    r"\s*,\s*inclination:\s*([+-]?(?:\d+\.?\d*|\.\d+))"
    r"\s*,\s*depth:\s*([+-]?(?:\d+\.?\d*|\.\d+))",
    re.I,
)
DEVICE_STEP_RE = re.compile(r"current device prepare step\s+(\d+)", re.I)

ERROR_LIMIT_MM = 1.0
CUT_LIMIT_1 = 1.0
CUT_LIMIT_2 = 2.0
STARTUP_MSG = "Oberon Application Startup"
EXIT_MSG = "Oberon Application Exit"
START_OP = "start operation"
UUID_LOAD = "start load plan uuid"

RAS_SPAN_LABELS = ("髋臼打磨", "安装髋臼杯", "验证髋臼杯")
RAS_TO_VERIFY = {
    "髋臼打磨": "验证髋臼杯",
    "安装髋臼杯": "验证髋臼杯",
}
EXPECTED_RAS: list[tuple[str, str]] = [("外展角", "deg"), ("前倾角", "deg")]

POLISH_PHRASES = ("switch polish hip step",)
INSTALL_CUP_PHRASES = ("switch install hip cup step",)
PLAN_WINDOW_CLOSE = POLISH_PHRASES + INSTALL_CUP_PHRASES

ALL_LINES_LIMIT = 30_000
HUGE_LINES = 80_000
DEFAULT_WINDOW = 12_000

CASE_PALETTE = [
    "#3d8bff",
    "#ff8c42",
    "#e63956",
    "#2ec4b6",
    "#7b61ff",
    "#f4c430",
    "#ff5d8f",
    "#3ddc97",
    "#c77dff",
    "#ffb703",
]
UNKNOWN_CASE_COLOR = "#6b7684"


def _norm_side(token: str) -> str | None:
    s = (token or "").strip().lower()
    if s in ("left", "l", "左"):
        return "left"
    if s in ("right", "r", "右"):
        return "right"
    return None


def _side_zh(side: str | None) -> str:
    if side == "left":
        return "左"
    if side == "right":
        return "右"
    return ""


def _msg(ev: dict) -> str:
    return ev.get("message") or ev.get("raw") or ""


def match_l1(msg: str) -> tuple[str, str | None]:
    """Return (action, label). action: enter | end_if | end_all | none."""
    if EXIT_MSG in msg or STARTUP_MSG in msg:
        return "end_all", None
    if "enter poster operation page" in msg:
        return "enter", "术后"
    if "enter femur navigation page" in msg:
        return "enter", "股骨导航"
    if "enter hip navigation page" in msg:
        return "enter", "髋导航"
    if "enter device prepare page" in msg:
        return "enter", "设备准备"
    if "enter planviewer page" in msg or "switch planviewer page" in msg:
        return "enter", "方案预览"
    return "none", None


def match_l2(msg: str) -> tuple[str, str | None]:
    if "enter hip navigation step 1 install nail" in msg or "switch install hip mark nail step" in msg:
        return "enter", "安装髋标记钉"
    if "enter hip navigation step 2 register hip" in msg or "switch register hip step" in msg:
        return "enter", "髋配准"
    if "switch polish hip step" in msg:
        return "enter", "髋臼打磨"
    if "switch install hip cup step" in msg:
        return "enter", "安装髋臼杯"
    if (
        "enter hip navigation step 5 validate hip cup" in msg
        or "switch verify hip cup install step" in msg
    ):
        return "enter", "验证髋臼杯"
    if "install femur navigation component step" in msg:
        return "enter", "安装股骨导航组件"
    if "install femur nail step" in msg:
        return "enter", "安装股骨钉"
    if "register femur step" in msg:
        return "enter", "股骨配准"
    if "cut femur step" in msg:
        return "enter", "股骨截骨"
    return "none", None


def match_l3(msg: str) -> tuple[str, str | None]:
    if "cup verified point" in msg:
        return "enter", "杯验证点"
    if "sparse point" in msg:
        return "enter", "配准稀疏采集"
    if "dense point" in msg:
        return "enter", "配准密采集"
    if "verify point" in msg:
        return "enter", "配准验证点"
    return "none", None


def match_device(msg: str) -> tuple[str, str | None]:
    """Background / device-status events. Not surgical L1-L3."""
    low = msg.lower()
    m = DEVICE_STEP_RE.search(msg)
    if m:
        return "tick", f"设备准备{m.group(1)}"
    if "robot emergency stop" in low:
        return "tick", "急停"
    if "kuka app is connected" in low or "kuka app is disconnected" in low:
        return "tick", "KUKA"
    if "kuka states are fault" in low:
        return "tick", "KUKA"
    if "connect mxio" in low:
        return "tick", "MXIO"
    if "marker data is invalid" in low:
        return "tick", "示踪器"
    if "hard switch" in low or "soft switch" in low or "handguding" in low:
        return "tick", "示教开关"
    return "none", None


def _time_index(events: list[dict], line_count: int) -> list[str]:
    times = [""] * max(line_count, 0)
    for ev in events:
        t = ev.get("time") or ""
        if not t:
            continue
        a = int(ev.get("line") or 1)
        b = int(ev.get("line_end") or a)
        for i in range(max(1, a), min(line_count, b) + 1):
            if not times[i - 1]:
                times[i - 1] = t
    last = ""
    for i, t in enumerate(times):
        if t:
            last = t
        elif last:
            times[i] = last
    return times


def _mark_index(events: list[dict], line_count: int) -> tuple[list[str], list[bool]]:
    marks = ["none"] * max(line_count, 0)
    noise = [False] * max(line_count, 0)
    rank = {"none": 0, "key": 1, "anomaly": 2}
    for ev in events:
        a = int(ev.get("line") or 1)
        b = int(ev.get("line_end") or a)
        is_noise = ev.get("source") == "noise" or ev.get("category") == "noise"
        mk = ev.get("mark") or "none"
        for i in range(max(1, a), min(line_count, b) + 1):
            if is_noise:
                noise[i - 1] = True
            if mk in rank and rank[mk] > rank[marks[i - 1]]:
                marks[i - 1] = mk
    return marks, noise


def _span(
    sid: str,
    label: str,
    start: int,
    end: int,
    times: list[str],
    extra: dict | None = None,
) -> dict:
    n = len(times)
    s = max(1, start)
    e = max(s, min(end, n) if n else end)
    rec = {
        "id": sid,
        "label": label,
        "start": s,
        "end": e,
        "t0": times[s - 1] if n and s <= n else "",
        "t1": times[e - 1] if n and e <= n else "",
    }
    if extra:
        rec.update(extra)
    return rec


class _Open:
    __slots__ = ("label", "start", "extra")

    def __init__(self, label: str, start: int, extra: dict | None = None):
        self.label = label
        self.start = start
        self.extra = extra or {}


def _close(open_span: _Open | None, end: int, times: list[str], bucket: list, prefix: str) -> None:
    if open_span is None:
        return
    if end < open_span.start:
        end = open_span.start
    extra = dict(open_span.extra)
    extra.setdefault("level", {"l1": 1, "l2": 2, "l3": 3, "dev": 0}.get(prefix))
    bucket.append(
        _span(
            f"{prefix}-{len(bucket)}",
            open_span.label,
            open_span.start,
            end,
            times,
            extra,
        )
    )


def parse_error_event(msg: str) -> dict | None:
    m = HIP_REG_ERR_RE.search(msg)
    if m:
        return {"target": "髋配准", "label": "RMS", "value": float(m.group(1))}
    m = PROBE_ERR_RE.search(msg)
    if m:
        return {"target": "设备准备", "label": "探针", "value": float(m.group(1))}
    m = EFFECTOR_ERR_RE.search(msg)
    if m:
        return {"target": "设备准备", "label": "末端", "value": float(m.group(1))}
    return None


def collect_errors(events: list[dict]) -> list[dict]:
    out = []
    for ev in events:
        rec = parse_error_event(_msg(ev))
        if not rec:
            continue
        rec["line"] = int(ev.get("line") or 1)
        rec["over"] = rec["value"] > ERROR_LIMIT_MM
        out.append(rec)
    return out


def attach_errors(spans: list[dict], errors: list[dict]) -> None:
    """Put error readings onto the matching page span (last value per label)."""
    for sp in spans:
        hit = [
            e
            for e in errors
            if e["target"] == sp.get("label") and int(sp["start"]) <= e["line"] <= int(sp["end"]) + 12
        ]
        if not hit:
            continue
        by_key: dict = {}
        for e in hit:
            by_key[e["label"]] = e
        ordered = sorted(by_key.values(), key=lambda e: (e.get("point") or 0, e["line"]))
        sp["errors"] = [
            {
                "label": e["label"],
                "value": round(e["value"], 3),
                "over": bool(e["over"]),
                "line": e["line"],
            }
            for e in ordered
        ]
        mx = max(e["value"] for e in ordered)
        sp["error_max"] = round(mx, 3)


def _near_zero(v: float) -> bool:
    return abs(v) < 1e-9


def collect_cut_deltas(events: list[dict]) -> tuple[list[dict], list[dict]]:
    """Compare realtime RAS to the latest in-session plan snapshot.

    All-zero RAS (page switch) is ignored. Plan inclination is not thresholded.
    Returns (items, flags) with the same shape the frontend uses for hover Δ.
    """
    plan_inc: float | None = None
    plan_av: float | None = None
    items: list[dict] = []
    flags: list[dict] = []

    for ev in events:
        msg = _msg(ev).rstrip()
        line = int(ev.get("line") or 1)
        if STARTUP_MSG in msg:
            plan_inc = None
            plan_av = None
            continue

        pm = PLAN_RE.search(msg)
        if pm:
            plan_inc = float(pm.group(1))
            plan_av = float(pm.group(2))
            continue

        rm = RAS_RE.search(msg)
        if not rm:
            continue
        av = float(rm.group(1))
        inc = float(rm.group(2))
        depth = float(rm.group(3))
        if _near_zero(av) and _near_zero(inc) and _near_zero(depth):
            continue

        for display, measured, planned in (
            ("外展角", inc, plan_inc),
            ("前倾角", av, plan_av),
        ):
            rec = {
                "label": display,
                "unit": "deg",
                "plan": planned,
                "measured": measured,
                "delta": None,
                "over1": False,
                "over2": False,
                "line": line,
                "span": "髋臼打磨",
                "level": "ok",
                "missing": False,
            }
            if planned is None:
                items.append(rec)
                continue
            delta = measured - planned
            ad = abs(delta)
            over2 = ad > CUT_LIMIT_2
            over1 = ad > CUT_LIMIT_1
            if over2:
                level = "anomaly"
            elif over1:
                level = "key"
            else:
                level = "ok"
            rec["delta"] = delta
            rec["over1"] = over1
            rec["over2"] = over2
            rec["level"] = level
            items.append(rec)
            if level in ("key", "anomaly"):
                flags.append({"line": line, "level": level})
    return items, flags


def _session_end_for(line: int, events: list[dict] | None, line_count: int) -> int:
    if not events:
        return line_count or line
    for ev in events:
        ln = int(ev.get("line") or 1)
        if ln <= line:
            continue
        msg = _msg(ev)
        if STARTUP_MSG in msg:
            return max(line, ln - 1)
        if EXIT_MSG in msg:
            return ln
    return line_count or line


def _cut_row_from_item(e: dict) -> dict:
    row = {
        "label": e["label"],
        "unit": e["unit"],
        "over1": bool(e.get("over1")),
        "over2": bool(e.get("over2")),
        "line": e["line"],
        "missing": False,
    }
    if e.get("plan") is not None:
        row["plan"] = round(e["plan"], 2)
    if e.get("measured") is not None:
        row["measured"] = round(e["measured"], 2)
    if e.get("delta") is not None:
        row["delta"] = round(e["delta"], 2)
    return row


def _missing_cut_row(display: str, unit: str, line: int) -> dict:
    return {
        "label": display,
        "unit": unit,
        "missing": True,
        "over1": True,
        "over2": False,
        "line": line,
    }


def _fill_cut_deltas(sp: dict, expected: list[tuple[str, str]], hit: list[dict], mark_line: int) -> None:
    by_key: dict = {}
    for e in hit:
        by_key[e["label"]] = e
    rows = []
    for display, unit in expected:
        if display in by_key:
            rows.append(_cut_row_from_item(by_key[display]))
        else:
            rows.append(_missing_cut_row(display, unit, mark_line))
    sp["cut_deltas"] = rows


def attach_cut_deltas(
    spans: list[dict],
    items: list[dict],
    events: list[dict] | None = None,
    line_count: int = 0,
) -> None:
    if not line_count:
        line_count = max((int(s.get("end") or 0) for s in spans), default=0)

    for sp in spans:
        lab = sp.get("label")
        if lab not in RAS_SPAN_LABELS:
            continue
        lo = int(sp["start"])
        hi = int(sp["end"]) + 12
        hit = [e for e in items if lo <= e["line"] <= hi]
        _fill_cut_deltas(sp, EXPECTED_RAS, hit, lo)

    for sp in spans:
        lab = sp.get("label")
        verify_lab = RAS_TO_VERIFY.get(lab or "")
        if not verify_lab:
            continue
        if sp.get("cut_deltas") and not any(c.get("missing") for c in sp["cut_deltas"]):
            continue
        cut_start = int(sp["start"])
        session_end = _session_end_for(cut_start, events, line_count)
        has_verify_after = any(
            s.get("label") == verify_lab and cut_start < int(s["start"]) <= session_end for s in spans
        )
        if has_verify_after:
            continue
        hit = [e for e in items if cut_start <= e["line"] <= session_end]
        if hit or sp.get("cut_deltas"):
            _fill_cut_deltas(sp, EXPECTED_RAS, hit, cut_start)


def gather_missing_cut_flags(spans: list[dict]) -> list[dict]:
    flags: list[dict] = []
    seen: set[int] = set()
    for sp in spans:
        for c in sp.get("cut_deltas") or []:
            if not c.get("missing"):
                continue
            ln = int(c.get("line") or 0)
            if not ln or ln in seen:
                continue
            seen.add(ln)
            flags.append({"line": ln, "level": "key"})
    return flags


def apply_cut_flags(marks: list[str], flags: list[dict]) -> None:
    n = len(marks)
    for f in flags:
        ln = int(f.get("line") or 0)
        if not (1 <= ln <= n):
            continue
        level = f.get("level") or "none"
        i = ln - 1
        if level == "anomaly":
            marks[i] = "anomaly"
        elif level == "key" and marks[i] != "anomaly":
            marks[i] = "key"


def build_page_tracks(events: list[dict], line_count: int, times: list[str]) -> dict:
    l1: list[dict] = []
    l2: list[dict] = []
    l3: list[dict] = []
    device: list[dict] = []
    l2_ticks: list[dict] = []
    o1: _Open | None = None
    o2: _Open | None = None
    o3: _Open | None = None

    def close_l3(end: int) -> None:
        nonlocal o3
        _close(o3, end, times, l3, "l3")
        o3 = None

    def close_l2(end: int) -> None:
        nonlocal o2
        close_l3(end)
        _close(o2, end, times, l2, "l2")
        o2 = None

    def close_l1(end: int) -> None:
        nonlocal o1
        close_l2(end)
        _close(o1, end, times, l1, "l1")
        o1 = None

    for ev in events:
        msg = _msg(ev)
        line = int(ev.get("line") or 1)
        prev = line - 1 if line > 1 else line

        a1, lab1 = match_l1(msg)
        if a1 == "end_all":
            close_l1(line)
            continue
        if a1 == "end_if":
            if o1 and o1.label == lab1:
                close_l1(prev if prev >= o1.start else line)
            continue
        if a1 == "enter" and lab1:
            if o1 and o1.label == lab1:
                pass
            else:
                close_l1(prev if o1 else prev)
                o1 = _Open(lab1, line)
        a2, lab2 = match_l2(msg)
        if a2 == "exit":
            if o2 and (lab2 is None or o2.label == lab2):
                _close(o2, line, times, l2, "l2")
                o2 = None
                close_l3(line)
            elif lab2:
                last = l2_ticks[-1] if l2_ticks else None
                if not (last and last["label"] == lab2 and line - int(last["end"]) <= 2):
                    l2_ticks.append(
                        _span(f"l2-{len(l2)+len(l2_ticks)}", lab2, line, line, times, {"level": 2})
                    )
        elif a2 == "enter" and lab2:
            if o2 and o2.label == lab2:
                pass
            else:
                close_l3(prev)
                _close(o2, prev if o2 else prev, times, l2, "l2")
                o2 = _Open(lab2, line)

        a3, lab3 = match_l3(msg)
        if a3 == "exit":
            if o3 and (lab3 is None or o3.label == lab3):
                _close(o3, line, times, l3, "l3")
                o3 = None
        elif a3 == "enter" and lab3:
            if o3 and o3.label == lab3:
                pass
            else:
                _close(o3, prev if o3 else prev, times, l3, "l3")
                o3 = _Open(lab3, line)

        ad, labd = match_device(msg)
        if ad == "tick" and labd:
            last = device[-1] if device else None
            if last and last["label"] == labd and line - int(last["end"]) <= 2:
                last["end"] = line
            else:
                device.append(_span(f"dev-{len(device)}", labd, line, line, times, {"level": 0}))

    close_l1(line_count)
    l2.extend(l2_ticks)
    errs = collect_errors(events)
    attach_errors(l1, errs)
    attach_errors(l2, errs)
    attach_errors(l3, errs)
    cut_items, _cut_flags = collect_cut_deltas(events)
    attach_cut_deltas(l2, cut_items, events, line_count)
    attach_cut_deltas(l3, cut_items, events, line_count)
    return {"l1": l1, "l2": l2, "l3": l3, "device": device}


def _extract_version(msg: str) -> str | None:
    m = VERSION_RE.search(msg)
    return m.group(1) if m else None


def _extract_uuid(msg: str) -> str | None:
    if UUID_LOAD in msg:
        m = UUID_RE.search(msg)
        return m.group(1).lower() if m else None
    return None


def build_sessions_and_cases(events: list[dict], line_count: int, times: list[str]) -> dict:
    sessions_raw: list[dict] = []
    markers: list[dict] = []
    cur: dict | None = None

    def start_session(line: int, t: str) -> dict:
        return {
            "start": line,
            "end": line_count,
            "t0": t,
            "startups": [line],
            "exits": [],
            "uuid": None,
            "cup": None,
            "brand": None,
            "series": None,
            "side": None,
            "uuid_line": None,
            "plan_changes": [],
            "version": None,
            "version_line": None,
        }

    for ev in events:
        msg = _msg(ev)
        line = int(ev.get("line") or 1)
        t = ev.get("time") or (times[line - 1] if times and line <= len(times) else "")

        if STARTUP_MSG in msg:
            mk = {"line": line, "kind": "startup", "t": t}
            ver = _extract_version(msg)
            if ver:
                mk["version"] = ver
                mk["version_line"] = line
            markers.append(mk)
            if cur is not None:
                meaningful = cur["uuid"] or cur["plan_changes"] or (line - cur["start"] > 8)
                last_startup = cur["startups"][-1] if cur["startups"] else cur["start"]
                if not meaningful and line - last_startup <= 8:
                    cur["startups"].append(line)
                else:
                    cur["end"] = max(cur["start"], line - 1)
                    sessions_raw.append(cur)
                    cur = start_session(line, t)
            else:
                cur = start_session(line, t)
            if ver and cur is not None and not cur.get("version"):
                cur["version"] = ver
                cur["version_line"] = line
            continue

        if EXIT_MSG in msg:
            markers.append({"line": line, "kind": "exit", "t": t})
            if cur is not None:
                cur["exits"].append(line)
                cur["end"] = line
                sessions_raw.append(cur)
                cur = None
            elif sessions_raw and not sessions_raw[-1]["exits"]:
                sessions_raw[-1]["exits"].append(line)
                sessions_raw[-1]["end"] = line
            elif sessions_raw:
                prev = sessions_raw[-1]
                if line - prev["end"] <= 30:
                    prev["exits"].append(line)
                    prev["end"] = line
            continue

        if cur is None:
            continue

        ver = _extract_version(msg)
        if ver:
            if not cur.get("version"):
                cur["version"] = ver
                cur["version_line"] = line
            for mk in markers:
                if mk["kind"] == "startup" and mk["line"] >= cur["start"] and mk["line"] <= line:
                    if not mk.get("version"):
                        mk["version"] = ver
                        mk["version_line"] = line

        uid = _extract_uuid(msg)
        if uid:
            if cur["uuid"] is None:
                cur["uuid"] = uid
                cur["uuid_line"] = line
            elif uid != cur["uuid"]:
                cur["plan_changes"].append((line, uid))
                cur["uuid"] = uid
                cur["uuid_line"] = line

        cm = CUP_TYPE_RE.search(msg)
        if cm:
            cup = (cm.group(1) or "").strip().rstrip(",")
            cur["cup"] = cup
            cur["brand"] = cup

        sm = SIDE_RE.search(msg)
        if sm:
            cur["side"] = _norm_side(sm.group(1))

    if cur is not None:
        cur["end"] = line_count
        sessions_raw.append(cur)

    case_order: list[str] = []
    case_meta: dict[str, dict] = {}

    def remember(uid: str, cup, side) -> None:
        if uid not in case_meta:
            case_order.append(uid)
            case_meta[uid] = {"cup": cup, "brand": cup, "series": None, "side": side}
        else:
            meta = case_meta[uid]
            if cup and not meta.get("cup"):
                meta["cup"] = cup
                meta["brand"] = cup
            if side and not meta["side"]:
                meta["side"] = side

    pieces: list[dict] = []
    for idx, ses in enumerate(sessions_raw):
        changes = ses.get("plan_changes") or []
        if not changes:
            uid = ses.get("uuid")
            if uid:
                remember(uid, ses.get("cup") or ses.get("brand"), ses.get("side"))
            pieces.append({**ses, "session_i": idx, "uuid": uid})
        else:
            initial = None
            splits: list[tuple[int, str]] = []
            for ev in events:
                line = int(ev.get("line") or 1)
                if line < ses["start"] or line > ses["end"]:
                    continue
                uid = _extract_uuid(_msg(ev))
                if uid:
                    if initial is None:
                        initial = uid
                        remember(uid, None, None)
                    elif uid != (splits[-1][1] if splits else initial):
                        splits.append((line, uid))
                        remember(uid, None, None)
            cursor_uid = initial
            cursor_start = ses["start"]
            for sl, uid in splits:
                pieces.append(
                    {
                        **ses,
                        "session_i": idx,
                        "uuid": cursor_uid,
                        "start": cursor_start,
                        "end": max(cursor_start, sl - 1),
                    }
                )
                cursor_uid = uid
                cursor_start = sl
            pieces.append(
                {
                    **ses,
                    "session_i": idx,
                    "uuid": cursor_uid,
                    "start": cursor_start,
                    "end": ses["end"],
                }
            )

    restart_count: dict[str, int] = {}
    sessions_out: list[dict] = []
    for idx, ses in enumerate(sessions_raw):
        uid = None
        for p in pieces:
            if p["session_i"] == idx and p.get("uuid"):
                uid = p["uuid"]
                break
        if uid is None:
            uid = ses.get("uuid")
        if uid:
            restart_count[uid] = restart_count.get(uid, 0) + 1
            n = restart_count[uid]
        else:
            n = 0
        extra = {
            "uuid": uid,
            "n": n,
            "restart": bool(uid and n > 1),
            "cup": ses.get("cup"),
            "brand": ses.get("cup") or ses.get("brand"),
            "series": ses.get("series"),
            "side": ses.get("side"),
            "version": ses.get("version"),
            "version_line": ses.get("version_line"),
        }
        if uid:
            remember(uid, ses.get("cup") or ses.get("brand"), ses.get("side"))
            meta = case_meta[uid]
            nth = case_order.index(uid) + 1
            extra["case_n"] = nth
            extra["case_label"] = _case_label(nth, uid, meta)
            extra["color"] = CASE_PALETTE[(nth - 1) % len(CASE_PALETTE)]
            label = extra["case_label"] if n <= 1 else f"#{n} 重启"
        else:
            extra["case_n"] = 0
            extra["case_label"] = "未打开方案"
            extra["color"] = UNKNOWN_CASE_COLOR
            label = "未打开方案"
        sessions_out.append(_span(f"ses-{idx}", label, ses["start"], ses["end"], times, extra))

    cases_out: list[dict] = []
    run: dict | None = None

    def flush_run() -> None:
        nonlocal run
        if not run:
            return
        uid = run["uuid"]
        extra = {
            "uuid": uid,
            "n": run["n"],
            "color": run["color"],
            "cup": run.get("cup"),
            "brand": run.get("brand"),
            "series": run.get("series"),
            "side": run.get("side"),
            "session_ids": run["session_ids"],
        }
        cases_out.append(
            _span(f"case-{len(cases_out)}", run["label"], run["start"], run["end"], times, extra)
        )
        run = None

    for ses in sessions_out:
        uid = ses.get("uuid")
        if uid:
            nth = ses.get("case_n") or (case_order.index(uid) + 1)
            color = CASE_PALETTE[(nth - 1) % len(CASE_PALETTE)]
            label = ses.get("case_label") or _case_label(nth, uid, case_meta.get(uid) or {})
            n = nth
        else:
            color = UNKNOWN_CASE_COLOR
            label = "未打开方案"
            n = 0
        if run and run["uuid"] == uid and run["uuid"] is not None:
            run["end"] = ses["end"]
            run["session_ids"].append(ses["id"])
            continue
        if run and run["uuid"] is None and uid is None:
            run["end"] = ses["end"]
            run["session_ids"].append(ses["id"])
            continue
        flush_run()
        run = {
            "uuid": uid,
            "n": n,
            "color": color,
            "label": label,
            "start": ses["start"],
            "end": ses["end"],
            "cup": ses.get("cup"),
            "brand": ses.get("brand"),
            "series": ses.get("series"),
            "side": ses.get("side"),
            "session_ids": [ses["id"]],
        }
    flush_run()

    return {"cases": cases_out, "sessions": sessions_out, "markers": markers}


def _case_label(nth: int, uid: str, meta: dict) -> str:
    cup = (meta.get("cup") or meta.get("brand") or "").strip()
    side = _side_zh(meta.get("side"))
    bits = [f"手术{nth}"]
    if cup:
        bits.append(cup)
    if side:
        bits.append(side)
    return " · ".join(bits)


def annotate_hlevel(events: list[dict]) -> None:
    for ev in events:
        msg = _msg(ev)
        a1, _ = match_l1(msg)
        a2, _ = match_l2(msg)
        a3, _ = match_l3(msg)
        ad, _ = match_device(msg)
        if a1 == "enter" or a1 == "end_if":
            ev["hlevel"] = 1
        elif a2 != "none":
            ev["hlevel"] = 2
        elif a3 != "none":
            ev["hlevel"] = 3
        elif ad != "none":
            ev["hlevel"] = 0
        else:
            ev["hlevel"] = None


def _special_index(events: list[dict], markers: list[dict], line_count: int) -> list[str]:
    spec = [""] * max(line_count, 0)
    for mk in markers:
        ln = int(mk.get("line") or 0)
        if mk.get("kind") == "startup" and 1 <= ln <= line_count:
            spec[ln - 1] = "startup"
        vl = mk.get("version_line")
        if vl and 1 <= int(vl) <= line_count and spec[int(vl) - 1] != "startup":
            spec[int(vl) - 1] = "version"
    for ev in events:
        msg = _msg(ev)
        line = int(ev.get("line") or 1)
        if not (1 <= line <= line_count):
            continue
        if STARTUP_MSG in msg:
            spec[line - 1] = "startup"
        elif _extract_version(msg) and spec[line - 1] != "startup":
            spec[line - 1] = "version"
    return spec


def build_lines(
    raw_lines: list[str],
    marks: list[str],
    noise: list[bool],
    specials: list[str] | None = None,
    center: int | None = None,
    window: int | None = None,
) -> tuple[list[dict], bool, int, int]:
    n = len(raw_lines)
    lo, hi = 1, n
    windowed = False
    if n > ALL_LINES_LIMIT:
        win = window or DEFAULT_WINDOW
        if n > HUGE_LINES and window is None:
            win = DEFAULT_WINDOW
        c = center or max(1, n // 2)
        half = max(1, win // 2)
        lo = max(1, c - half)
        hi = min(n, lo + win - 1)
        if hi - lo + 1 < win:
            lo = max(1, hi - win + 1)
        windowed = lo > 1 or hi < n
    out = []
    for i in range(lo, hi + 1):
        raw = raw_lines[i - 1].rstrip("\n\r")
        m = LOG_RE.match(raw)
        t = m.group(1) if m else ""
        lv = m.group(4) if m else ""
        out.append(
            {
                "n": i,
                "t": t,
                "lv": lv,
                "raw": raw,
                "mark": marks[i - 1] if i - 1 < len(marks) else "none",
                "noise": bool(noise[i - 1]) if i - 1 < len(noise) else False,
                "special": (specials[i - 1] if specials and i - 1 < len(specials) else "") or "",
            }
        )
    return out, windowed, lo, hi


def compact_ticks(marks: list[str]) -> dict:
    key: list[int] = []
    anomaly: list[int] = []
    for i, mk in enumerate(marks, 1):
        if mk == "anomaly":
            anomaly.append(i)
        elif mk == "key":
            key.append(i)
    return {"key": key, "anomaly": anomaly}


def _in_ranges(line: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= line <= b for a, b in ranges)


def uuid_ranges(events: list[dict], line_count: int) -> dict[str, list[tuple[int, int]]]:
    """Line ranges owned by each plan uuid.

    Startup clears uuid until the next load. Same uuid across sessions is
    merged by the caller.
    """
    out: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    start: int | None = None

    def flush(end: int) -> None:
        nonlocal current, start
        if current and start is not None and end >= start:
            out.setdefault(current, []).append((start, end))
        current = None
        start = None

    last_line = 0
    for ev in events:
        msg = _msg(ev)
        line = int(ev.get("line") or 1)
        last_line = line
        if STARTUP_MSG in msg:
            flush(line - 1)
            continue
        if EXIT_MSG in msg:
            flush(line)
            continue
        uid = _extract_uuid(msg)
        if not uid:
            continue
        if current is None:
            current = uid
            start = line
        elif uid != current:
            flush(line - 1)
            current = uid
            start = line
    flush(line_count or last_line)
    return out


def _step(
    sid: str,
    name: str,
    ok: bool,
    line: int | None = None,
    missing_detail: str | None = None,
    extra: dict | None = None,
) -> dict:
    rec: dict[str, Any] = {"id": sid, "name": name, "ok": bool(ok)}
    if line:
        rec["line"] = int(line)
    if missing_detail:
        rec["missing_detail"] = missing_detail
    if extra:
        rec.update(extra)
    return rec


def _first_phrase_line(evs: list[dict], phrases: tuple[str, ...]) -> int | None:
    for ev in evs:
        msg = _msg(ev)
        if any(p in msg for p in phrases):
            return int(ev.get("line") or 1)
    return None


def _planning_snapshot(evs: list[dict]) -> tuple[bool, int | None, str | None]:
    """Plan hand-over only counts before hip polish / cup install."""
    closed = False
    line: int | None = None
    post_line: int | None = None
    for ev in evs:
        msg = _msg(ev)
        ln = int(ev.get("line") or 1)
        if any(p in msg for p in PLAN_WINDOW_CLOSE):
            closed = True
        if "planviewer hand over,plan inclination" in msg:
            if not closed:
                line = ln
            elif post_line is None:
                post_line = ln
    if line:
        return True, line, None
    if post_line:
        return False, post_line, "仅术后打开方案预览"
    return False, None, "未做"


def _ras_touched(evs: list[dict], ranges: list[tuple[int, int]]) -> tuple[bool, int | None]:
    for ev in evs:
        ln = int(ev.get("line") or 1)
        if not _in_ranges(ln, ranges):
            continue
        m = RAS_RE.search(_msg(ev))
        if not m:
            continue
        av, inc, depth = float(m.group(1)), float(m.group(2)), float(m.group(3))
        if _near_zero(av) and _near_zero(inc) and _near_zero(depth):
            continue
        return True, ln
    return False, None


def _eval_required_steps(
    evs: list[dict],
    cut_items: list[dict],
    ranges: list[tuple[int, int]],
    fallback_line: int,
) -> list[dict]:
    steps: list[dict] = []

    prep_line = _first_phrase_line(
        evs, ("enter device prepare page", "current device prepare step")
    )
    steps.append(
        _step("device_prepare", "设备准备", bool(prep_line), prep_line or fallback_line, None if prep_line else "未做")
    )

    probe_line = _first_phrase_line(evs, ("probe calibration error",))
    steps.append(
        _step("probe_cal", "探针标定", bool(probe_line), probe_line or fallback_line, None if probe_line else "未做")
    )

    plan_ok, plan_line, plan_detail = _planning_snapshot(evs)
    steps.append(_step("plan_target", "规划目标", plan_ok, plan_line or fallback_line, plan_detail))

    nail_line = _first_phrase_line(
        evs, ("switch install hip mark nail step", "enter hip navigation step 1 install nail")
    )
    steps.append(
        _step("hip_nail", "安装髋标记钉", bool(nail_line), nail_line or fallback_line, None if nail_line else "未做")
    )

    hip_reg = _first_phrase_line(evs, ("hip register calculate error",))
    steps.append(
        _step("hip_register", "髋配准", bool(hip_reg), hip_reg or fallback_line, None if hip_reg else "未做")
    )

    polish = _first_phrase_line(evs, POLISH_PHRASES)
    steps.append(
        _step("hip_polish", "髋臼打磨", bool(polish), polish or fallback_line, None if polish else "未做")
    )

    cup_install = _first_phrase_line(evs, INSTALL_CUP_PHRASES)
    steps.append(
        _step(
            "hip_cup",
            "安装髋臼杯",
            bool(cup_install),
            cup_install or fallback_line,
            None if cup_install else "未做",
        )
    )

    verify = _first_phrase_line(
        evs,
        (
            "cup verified point",
            "switch verify hip cup install step",
            "enter hip navigation step 5 validate hip cup",
        ),
    )
    ras_ok, ras_line = _ras_touched(evs, ranges)
    extra = {}
    if not ras_ok and (polish or cup_install or verify):
        extra["missing_ras"] = True
        if verify:
            # entered verify/polish but no non-zero RAS
            pass
    steps.append(
        _step(
            "hip_verify",
            "验证髋臼杯",
            bool(verify),
            verify or fallback_line,
            None if verify else "未做",
            extra or None,
        )
    )

    if _first_phrase_line(evs, ("enter femur navigation page",)):
        for sid, name, phrases in (
            ("femur_nail", "安装股骨钉", ("install femur nail step",)),
            ("femur_register", "股骨配准", ("register femur step",)),
            ("femur_cut", "股骨截骨", ("cut femur step",)),
        ):
            ln = _first_phrase_line(evs, phrases)
            steps.append(_step(sid, name, bool(ln), ln or fallback_line, None if ln else "未做"))

    _ = cut_items  # Δ lives on L2 hover; summary uses presence of steps
    return steps


def build_summaries(
    events: list[dict],
    cases: list[dict],
    cut_items: list[dict],
    line_count: int = 0,
) -> list[dict]:
    """One 方案汇总 card per plan uuid (skip 未打开方案)."""
    owned = uuid_ranges(events, line_count)
    order: list[str] = []
    meta: dict[str, dict] = {}
    for c in cases:
        uid = c.get("uuid")
        if not uid:
            continue
        if uid not in meta:
            order.append(uid)
            meta[uid] = {
                "uuid": uid,
                "case_n": int(c.get("n") or c.get("case_n") or len(order)),
                "label": c.get("label") or "",
                "color": c.get("color") or UNKNOWN_CASE_COLOR,
                "start": int(c.get("start") or 1),
                "end": int(c.get("end") or c.get("start") or 1),
            }
        else:
            meta[uid]["start"] = min(meta[uid]["start"], int(c.get("start") or meta[uid]["start"]))
            meta[uid]["end"] = max(meta[uid]["end"], int(c.get("end") or meta[uid]["end"]))

    out: list[dict] = []
    for uid in order:
        m = meta[uid]
        ranges = owned.get(uid) or [(m["start"], m["end"])]
        evs = [e for e in events if _in_ranges(int(e.get("line") or 1), ranges)]
        started = any(START_OP in _msg(e) for e in evs)
        rec = {
            "uuid": uid,
            "case_n": m["case_n"],
            "label": m["label"],
            "color": m["color"],
            "start": m["start"],
            "end": m["end"],
            "started": started,
            "steps": [],
        }
        if started:
            rec["steps"] = _eval_required_steps(evs, cut_items, ranges, m["start"])
        out.append(rec)
    return out


def build_nle(
    events: list[dict],
    raw_lines: list[str],
    center: int | None = None,
    window: int | None = None,
) -> dict:
    line_count = len(raw_lines)
    times = _time_index(events, line_count)
    marks, noise = _mark_index(events, line_count)
    _cut_items, cut_flags = collect_cut_deltas(events)
    apply_cut_flags(marks, cut_flags)
    annotate_hlevel(events)
    pages = build_page_tracks(events, line_count, times)
    apply_cut_flags(marks, gather_missing_cut_flags(pages["l2"]))
    apply_cut_flags(marks, gather_missing_cut_flags(pages["l3"]))
    sc = build_sessions_and_cases(events, line_count, times)
    summaries = build_summaries(events, sc["cases"], _cut_items, line_count)
    specials = _special_index(events, sc["markers"], line_count)
    lines, windowed, lo, hi = build_lines(
        raw_lines, marks, noise, specials, center=center, window=window
    )
    tracks = {
        "cases": sc["cases"],
        "sessions": sc["sessions"],
        "l1": pages["l1"],
        "l2": pages["l2"],
        "l3": pages["l3"],
        "device": pages.get("device") or [],
        "markers": sc["markers"],
    }
    return {
        "line_count": line_count,
        "lines": lines,
        "lines_windowed": windowed,
        "lines_start": lo,
        "lines_end": hi,
        "ticks": compact_ticks(marks),
        "tracks": tracks,
        "summaries": summaries,
    }
