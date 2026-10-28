"""NLE-style timeline spans: cases/sessions + L1/L2/L3 page tracks.

X axis is log line number. Stable event IDs and hierarchy come from the spec;
all views share the same session and plan boundaries.
"""

from __future__ import annotations

import math
import re
from typing import Any

from parser import LOG_RE

UUID_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)
CUP_TYPE_RE = re.compile(r"switch cup type:\s*(\S+)", re.I)
SIDE_RE = re.compile(r"operation side\s+(left|right|l|r|左|右)", re.I)
VERSION_RE = re.compile(r"Oberon Application Startup\s+version\s+(\S+)", re.I)
NUM_TOKEN = r"([+-]?(?:(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|nan|inf(?:inity)?))"
PLAN_RE = re.compile(
    r"planviewer hand over,plan inclination:\s*"
    + NUM_TOKEN
    + r"\s*,\s*plan anterversion:\s*"
    + NUM_TOKEN
    + r"\s*$",
    re.I,
)
UUID_LOAD = "start load plan uuid"
EXPECTED_RAS: list[tuple[str, str]] = [("外展角", "deg"), ("前倾角", "deg")]

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


def annotate_context(events: list[dict]) -> None:
    session = 0
    closed = True
    case = None
    page = ""
    task = ""
    for ev in events:
        eid = ev.get("event_id")
        if eid == "startup" or closed:
            session += 1
            closed = False
            case, page, task = None, "", ""
        if eid == "plan_load":
            case = _extract_uuid(_msg(ev))
            page = task = ""
        if ev.get("track") == "l1":
            page, task = eid, ""
        if ev.get("track") == "l2":
            page = ev.get("parent") or page
            task = eid
        ev.update(
            session_id=f"session-{session}",
            case_id=case,
            context={"page_id": page, "step_id": task},
            page=page,
        )
        if eid in ("exit", "crash"):
            closed = True
            case, page, task = None, "", ""


def rule_labels() -> dict:
    from spec import Spec

    spec = Spec()
    return {
        r["event_id"]: r["step"]
        for r in spec.mapping + spec.key + spec.anomaly
        if r.get("event_id")
    }


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


def parse_error_event(ev: dict) -> dict | None:
    labels = {
        "hip_error": ("髋配准", "RMS"),
        "probe_error": ("设备准备", "探针"),
        "effector_error": ("设备准备", "末端"),
    }
    identity = labels.get(ev.get("event_id"))
    if identity and ev.get("value_mm") is not None:
        return {"target": identity[0], "label": identity[1], "value": ev["value_mm"]}
    return None


def collect_cut_deltas(events: list[dict]) -> tuple[list[dict], list[dict]]:
    annotate_context(events)
    targets = {}
    boundary = None
    items, flags = [], []
    num = NUM_TOKEN
    pair = re.compile(
        r"anteversion:\s*" + num + r"\s*,\s*inclination:\s*" + num + r"(?=\s*(?:,|$))",
        re.I,
    )

    def invalid(ev):
        ev.pop("metrics", None)
        ev.update(
            event_id=ev["event_id"] + "_invalid",
            mark="anomaly",
            timeline="show",
            notes="坐标数值无效（非有限数或无法解析），不计算偏差，也不作为有效结果证据",
        )

    for ev in events:
        ctx = (ev.get("session_id"), ev.get("case_id"))
        eid = ev.get("event_id")
        if ctx != boundary or eid in ("startup", "plan_load", "exit", "crash"):
            targets = {}
            boundary = ctx
        msg = _msg(ev)
        line = int(ev["line"])
        if eid == "plan_legacy_invalid":
            targets.pop("legacy", None)
            continue
        if eid in ("target_ras_invalid", "target_app_invalid"):
            coordinate = "RAS" if eid == "target_ras_invalid" else "APP"
            targets.pop(coordinate, None)
            if coordinate == "RAS":
                targets.pop("legacy", None)
            continue
        if eid == "plan_legacy":
            m = PLAN_RE.search(msg)
            if not m or not all(math.isfinite(float(v)) for v in m.groups()):
                targets.pop("legacy", None)
                invalid(ev)
            else:
                targets["legacy"] = (
                    float(m[2]),
                    float(m[1]),
                    line,
                    "旧版方案预览 / RAS",
                )
            continue
        if eid in ("target_ras", "target_app"):
            m = pair.search(msg)
            coordinate = "RAS" if eid == "target_ras" else "APP"
            if not m or not all(math.isfinite(float(v)) for v in m.groups()):
                targets.pop(coordinate, None)
                if coordinate == "RAS":
                    targets.pop("legacy", None)
                invalid(ev)
            else:
                targets[coordinate] = (
                    float(m[1]),
                    float(m[2]),
                    line,
                    "显式坐标目标",
                )
            continue
        if eid not in ("measured_ras", "measured_app"):
            continue
        m = pair.search(msg)
        dm = re.search(r"depth:\s*" + num + r"\s*$", msg, re.I)
        if not m:
            invalid(ev)
            continue
        av, inc = float(m[1]), float(m[2])
        depth = float(dm[1]) if dm else None
        if not all(math.isfinite(v) for v in (av, inc, depth) if v is not None) or (
            "depth:" in msg and not dm
        ):
            invalid(ev)
            continue
        if av == 0 and inc == 0 and depth == 0:
            level = ev.get("level")
            warning = level == "W"
            error = level in ("E", "C")
            ev.update(
                source="level" if warning else "noise",
                category="other" if warning else "noise",
                timeline="show" if warning or error else "hide",
                mark="anomaly" if error else "key" if warning else "none",
            )
            continue
        coordinate = "RAS" if eid == "measured_ras" else "APP"
        target = targets.get(coordinate) or (
            targets.get("legacy") if coordinate == "RAS" else None
        )
        if target and not all(
            math.isfinite(v) for v in (av - target[0], inc - target[1])
        ):
            invalid(ev)
            continue
        limits = ev.get("limits") or {"angle_key": 1.0, "angle_anomaly": 2.0}
        readings = []
        for label, measured, planned in (
            ("外展角", inc, target[1] if target else None),
            ("前倾角", av, target[0] if target else None),
            ("深度", depth, None),
        ):
            if measured is None:
                continue
            delta = measured - planned if planned is not None else None
            over1 = delta is not None and abs(delta) > limits["angle_key"]
            over2 = delta is not None and abs(delta) > limits["angle_anomaly"]
            threshold_level = "anomaly" if over2 else "key" if over1 else "ok"
            level = "key" if over1 or over2 else "ok"
            rec = dict(
                label=label,
                unit="mm" if label == "深度" else "deg",
                plan=planned,
                measured=measured,
                delta=delta,
                over1=over1,
                over2=over2,
                line=line,
                span=ev.get("context", {}).get("step_id"),
                level=level,
                threshold_level=threshold_level,
                assessment="process_snapshot",
                assessment_reason="过程位姿快照，非最终杯验证结果；偏差超阈值仅作排查提示",
                missing=False,
                coordinate=coordinate,
                target_line=target[2] if target else None,
                target_source=target[3] if target else "缺少目标",
                limits=limits,
                session_id=ev.get("session_id"),
                case_id=ev.get("case_id"),
            )
            items.append(rec)
            readings.append(rec)
        ev["metrics"] = readings
        if any(r["over1"] or r["over2"] for r in readings):
            if ev.get("mark") != "anomaly":
                ev.update(mark="key", timeline="show")
            flags.append({"line": line, "level": ev["mark"]})
    return items, flags


def _missing_cut_row(display: str, unit: str, line: int) -> dict:
    return {
        "label": display,
        "unit": unit,
        "missing": True,
        "over1": True,
        "over2": False,
        "line": line,
    }


def attach_cut_deltas(spans, items, events=None, line_count=0):
    for sp in spans:
        if sp.get("event_id") not in ("hip_polish", "hip_cup", "hip_verify"):
            continue
        hit = [
            e
            for e in items
            if sp["start"] <= e["line"] <= sp["end"]
            and e.get("session_id") == sp.get("session_id")
            and e.get("case_id") == sp.get("case_id")
        ]
        latest = {}
        invalid_after = {}
        for ev in events or []:
            if sp["start"] <= ev["line"] <= sp["end"] and ev.get("event_id") in (
                "measured_ras_invalid",
                "measured_app_invalid",
            ):
                coordinate = (
                    "RAS" if ev["event_id"] == "measured_ras_invalid" else "APP"
                )
                invalid_after[coordinate] = ev["line"]
        for e in hit:
            if e["line"] > invalid_after.get(e["coordinate"], 0):
                latest[(e["coordinate"], e["label"])] = e
        if invalid_after:
            sp["result_state"] = "存在无效位姿快照，见行 " + ", ".join(
                str(n) for n in invalid_after.values()
            )
        sp["cut_deltas"] = list(latest.values()) or [
            _missing_cut_row(label, unit, sp["start"]) for label, unit in EXPECTED_RAS
        ]


def build_page_tracks(events, line_count, times):
    labels = rule_labels()
    buckets = {"l1": [], "l2": [], "l3": [], "device": []}
    opened = {}
    boundary = None

    def close(level, end):
        for key in ("l3", "l2", "l1"):
            if int(key[1]) >= level and key in opened:
                sp = opened.pop(key)
                sp["end"] = max(sp["start"], end)
                sp["t1"] = times[min(len(times), sp["end"]) - 1] if times else ""
                buckets[key].append(sp)

    def enter(track, eid, label, ev):
        if track in opened and opened[track]["event_id"] == eid:
            return
        close(int(track[1]), ev["line"] - 1)
        opened[track] = _span(
            f"{track}-{ev['line']}",
            label,
            ev["line"],
            ev["line"],
            times,
            {
                "event_id": eid,
                "session_id": ev.get("session_id"),
                "case_id": ev.get("case_id"),
            },
        )

    for ev in events:
        current = (ev.get("session_id"), ev.get("case_id"))
        eid, track = ev.get("event_id"), ev.get("track")
        if boundary != current or eid in ("startup", "plan_load", "exit", "crash"):
            close(1, ev["line"] - 1)
            boundary = current
        if track in ("l1", "l2", "l3"):
            parent = ev.get("parent")
            if (
                track == "l2"
                and parent
                and ("l1" not in opened or opened["l1"]["event_id"] != parent)
            ):
                enter("l1", parent, labels.get(parent, parent), ev)
            if track == "l3":
                # Sampling / clear / undo are operations, not a lasting page state.
                buckets["l3"].append(
                    _span(
                        f"l3-{ev['line']}",
                        ev["step"],
                        ev["line"],
                        ev["line_end"],
                        times,
                        {
                            "event_id": eid,
                            "session_id": ev.get("session_id"),
                            "case_id": ev.get("case_id"),
                            "mark": ev.get("mark"),
                            "notes": ev.get("notes"),
                        },
                    )
                )
            else:
                enter(track, eid, ev["step"], ev)
        if track == "device":
            buckets["device"].append(
                _span(
                    f"dev-{ev['line']}",
                    ev["step"],
                    ev["line"],
                    ev["line_end"],
                    times,
                    {
                        "mark": ev.get("mark"),
                        "event_id": eid,
                        "case_id": ev.get("case_id"),
                        "session_id": ev.get("session_id"),
                        "notes": ev.get("notes"),
                    },
                )
            )
    close(1, line_count)
    for key in ("l1", "l2"):
        for sp in buckets[key]:
            hit = [e for e in events if sp["start"] <= e["line"] <= sp["end"]]
            errors = {}
            for ev in hit:
                invalid_label = {
                    "probe_error_invalid": "探针",
                    "effector_error_invalid": "末端",
                    "hip_error_invalid": "RMS",
                }.get(ev.get("event_id"))
                if invalid_label:
                    errors.pop(invalid_label, None)
                    sp["result_state"] = (
                        f"最新{invalid_label}误差无效，见行 {ev['line']}"
                    )
                if ev.get("event_id") in ("clear_sparse", "clear_dense"):
                    errors.clear()
                    sp["result_state"] = "结果已清空／回退粗配准"
                rec = parse_error_event(ev)
                if rec and (
                    sp["event_id"] == "page_prepare" or sp["event_id"] == "hip_register"
                ):
                    errors[rec["label"]] = dict(
                        rec,
                        line=ev["line"],
                        over=ev.get("mark") == "anomaly",
                        threshold=ev.get("threshold"),
                    )
                    sp.pop("result_state", None)
            if errors:
                sp["errors"] = list(errors.values())
                sp["error_max"] = max(e["value"] for e in errors.values())
    items, _ = collect_cut_deltas(events)
    attach_cut_deltas(buckets["l2"], items, events, line_count)
    return buckets


def _extract_version(msg: str) -> str | None:
    m = VERSION_RE.search(msg)
    return m.group(1) if m else None


def _extract_uuid(msg: str) -> str | None:
    if UUID_LOAD in msg:
        m = UUID_RE.search(msg)
        return m.group(1).lower() if m else None
    return None


def build_sessions_and_cases(events, line_count, times):
    annotate_context(events)
    meta, order = {}, []
    markers = []
    segments = []
    run = None
    pending = {}
    physical = {}
    for ev in events:
        sid, uid = ev.get("session_id"), ev.get("case_id")
        eid = ev.get("event_id")
        msg = _msg(ev)
        if sid not in physical:
            physical[sid] = {"partial": eid != "startup", "version": None}
            pending = {}
        ver = _extract_version(msg)
        if ver:
            physical[sid]["version"] = ver
        if eid == "startup":
            markers.append(
                dict(
                    line=ev["line"],
                    kind="startup",
                    t=ev.get("time"),
                    version=ver,
                    session_id=sid,
                )
            )
        if eid == "exit":
            markers.append(dict(line=ev["line"], kind="exit", t=ev.get("time")))
        if uid and uid not in meta:
            order.append(uid)
            meta[uid] = dict(pending)
        target = meta[uid] if uid else pending
        cm = CUP_TYPE_RE.search(msg)
        sm = SIDE_RE.search(msg)
        if cm:
            target["cup"] = cm[1].rstrip(",")
        if sm:
            target["side"] = _norm_side(sm[1])
        if run is None or (run["session_id"], run["uuid"]) != (sid, uid):
            if run:
                run["end"] = ev["line"] - 1
                segments.append(run)
            run = dict(start=ev["line"], end=line_count, session_id=sid, uuid=uid)
    if run:
        segments.append(run)
    counts = {}
    seen = set()
    sessions = []
    cases = []
    for i, seg in enumerate(segments):
        uid = seg["uuid"]
        sid = seg["session_id"]
        n = order.index(uid) + 1 if uid else 0
        if uid and (uid, sid) not in seen:
            counts[uid] = counts.get(uid, 0) + 1
            seen.add((uid, sid))
        m = meta.get(uid, {})
        label = _case_label(n, uid, m) if uid else "未打开方案"
        color = CASE_PALETTE[(n - 1) % len(CASE_PALETTE)] if uid else UNKNOWN_CASE_COLOR
        extra = dict(
            uuid=uid,
            case_id=uid,
            session_id=sid,
            n=counts.get(uid, 0),
            case_n=n,
            case_label=label,
            color=color,
            cup=m.get("cup"),
            side=m.get("side"),
            version=physical[sid]["version"],
            partial=physical[sid]["partial"],
            restart=counts.get(uid, 0) > 1,
            session_ids=[sid],
        )
        sessions.append(
            _span(f"ses-{i}", label, seg["start"], seg["end"], times, extra)
        )
        cases.append(
            _span(
                f"case-{i}", label, seg["start"], seg["end"], times, {**extra, "n": n}
            )
        )
    return {"cases": cases, "sessions": sessions, "markers": markers}


def _case_label(nth: int, uid: str, meta: dict) -> str:
    cup = (meta.get("cup") or meta.get("brand") or "").strip()
    side = _side_zh(meta.get("side"))
    bits = [f"手术{nth}"]
    if cup:
        bits.append(cup)
    if side:
        bits.append(side)
    return " · ".join(bits)


def annotate_hlevel(events):
    for ev in events:
        track = ev.get("track", "")
        ev["hlevel"] = {"l1": 1, "l2": 2, "l3": 3, "device": 0}.get(track)


def _special_index(
    events: list[dict], markers: list[dict], line_count: int
) -> list[str]:
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
        if ev.get("event_id") == "startup":
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
        c = center or 1
        half = max(1, win // 2)
        lo = max(1, c - half)
        hi = min(n, lo + win - 1)
        if hi - lo + 1 < win:
            lo = max(1, hi - win + 1)
        windowed = lo > 1 or hi < n
    out = []
    for i in range(lo, hi + 1):
        raw = raw_lines[i - 1].rstrip("\n\r")
        m = LOG_RE.match(raw.lstrip("\ufeff"))
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
                "special": (
                    specials[i - 1] if specials and i - 1 < len(specials) else ""
                )
                or "",
            }
        )
    return out, windowed, lo, hi


def _in_ranges(line: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= line <= b for a, b in ranges)


def uuid_ranges(events, line_count):
    annotate_context(events)
    out = {}
    uid = None
    start = None
    for ev in events:
        current = ev.get("case_id")
        if current != uid or ev.get("event_id") == "plan_load":
            if uid and start is not None:
                out.setdefault(uid, []).append((start, ev["line"] - 1))
            uid = current
            start = ev["line"]
    if uid and start is not None:
        out.setdefault(uid, []).append((start, line_count))
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


def _first_phrase_line(evs, phrases):
    for ev in evs:
        if ev.get("event_id") in phrases:
            return int(ev["line"])
    return None


def _planning_snapshot(evs):
    closed = set()
    line = None
    post = None
    for ev in evs:
        sid = ev.get("session_id")
        if ev.get("event_id") == "plan_load":
            closed.discard(sid)
        if ev.get("event_id") in ("hip_polish", "hip_cup", "page_postop"):
            closed.add(sid)
        if ev.get("event_id") in ("plan_legacy", "target_ras", "target_app"):
            if sid not in closed:
                line = ev["line"]
            else:
                post = ev["line"]
    return (
        (True, line, None)
        if line
        else (False, post, "仅操作后／术后记录目标" if post else "未做")
    )


def _eval_required_steps(evs, cut_items, ranges, fallback_line):
    from spec import Spec

    rules = evs[0].get("requirements") if evs else None
    rules = rules if rules is not None else Spec().requirements
    steps = []
    present = {e.get("event_id") for e in evs}
    for rule in rules:
        if rule["when"] and rule["when"] not in present:
            continue
        if rule["id"] == "plan_target":
            ok, line, detail = _planning_snapshot(evs)
        else:
            line = _first_phrase_line(evs, rule["evidence"])
            ok, detail = bool(line), None if line else "未做"
        step = _step(rule["id"], rule["name"], ok, line or fallback_line, detail)
        if ok:
            evidence = next((e for e in evs if e["line"] == line), None)
            if evidence:
                step["evidence"] = {
                    key: evidence.get(key)
                    for key in ("line", "line_end", "message", "session_id", "event_id")
                }
        if rule["id"] == "hip_verify" and not any(e.get("metrics") for e in evs):
            step["missing_ras"] = True
        steps.append(step)
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
            meta[uid]["start"] = min(
                meta[uid]["start"], int(c.get("start") or meta[uid]["start"])
            )
            meta[uid]["end"] = max(
                meta[uid]["end"], int(c.get("end") or meta[uid]["end"])
            )

    out: list[dict] = []
    for uid in order:
        m = meta[uid]
        ranges = owned.get(uid) or [(m["start"], m["end"])]
        evs = [e for e in events if _in_ranges(int(e.get("line") or 1), ranges)]
        started = any(e.get("event_id") == "operation_start" for e in evs)
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
    annotate_context(events)
    _cut_items, _ = collect_cut_deltas(events)
    times = _time_index(events, line_count)
    marks, noise = _mark_index(events, line_count)
    annotate_hlevel(events)
    pages = build_page_tracks(events, line_count, times)

    sc = build_sessions_and_cases(events, line_count, times)
    summaries = build_summaries(events, sc["cases"], _cut_items, line_count)
    specials = _special_index(events, sc["markers"], line_count)
    lines, windowed, lo, hi = build_lines(
        raw_lines, marks, noise, specials, center=center, window=window
    )
    by_line = {}
    for ev in events:
        for ln in range(ev["line"], ev.get("line_end", ev["line"]) + 1):
            by_line[ln] = ev
    for row in lines:
        ev = by_line.get(row["n"], {})
        row.update(
            {
                k: ev.get(k)
                for k in (
                    "step",
                    "timeline",
                    "event_id",
                    "session_id",
                    "case_id",
                    "context",
                    "metrics",
                    "notes",
                )
            }
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
        "ticks": {
            kind: [e["line"] for e in events if e.get("mark") == kind]
            for kind in ("key", "anomaly")
        },
        "tracks": tracks,
        "summaries": summaries,
    }
