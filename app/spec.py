"""Parse docs/oberon-log-spec.md markdown tables into match rules.

Classification tables must have a 日志匹配 / match column. The business-order
table (顺序 / 源码页面) and the 级别规则 table are skipped automatically.

Section keywords: 步骤映射, 关键信息, 设置与切换, 异常, 噪声.
"""

from __future__ import annotations

import math
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = ROOT / "docs" / "oberon-log-spec.md"

HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")

MODE_ALIASES = {
    "contains": "contains",
    "contain": "contains",
    "substring": "contains",
    "子串": "contains",
    "包含": "contains",
    "prefix": "prefix",
    "前缀": "prefix",
    "startswith": "prefix",
    "regex": "regex",
    "regexp": "regex",
    "re": "regex",
    "正则": "regex",
}

TIMELINE_ALIASES = {
    "show": "show",
    "显示": "show",
    "hide": "hide",
    "隐藏": "hide",
}

MARK_ALIASES = {
    "none": "none",
    "普通": "none",
    "key": "key",
    "重点": "key",
    "重点标注": "key",
    "anomaly": "anomaly",
    "异常": "anomaly",
    "异常标注": "anomaly",
    "pin": "pin",
    "flag": "pin",
    "标记": "pin",
    "旗标": "pin",
    "特殊": "pin",
}

CATEGORY_ALIASES = {
    "lifecycle": "lifecycle",
    "生命周期": "lifecycle",
    "page": "page",
    "页面": "page",
    "step": "step",
    "手术步骤": "step",
    "步骤": "step",
    "key": "key",
    "关键": "key",
    "关键信息": "key",
    "robot": "robot",
    "机器人": "robot",
    "noise": "noise",
    "噪声": "noise",
    "other": "other",
    "其他": "other",
}


FLOAT_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def parse_threshold_cell(value: str) -> float | None:
    """Parse optional 阈值 cell: '>1', '>1mm', '1' -> 1.0. Empty/dash -> None."""
    s = (value or "").strip()
    if not s or s in ("-", "—", "–"):
        return None
    found = FLOAT_RE.findall(s)
    if not found:
        return None
    try:
        return float(found[-1])
    except ValueError:
        return None


def extract_last_mm(text: str) -> float | None:
    """Last floating number in the log message (mm). Ignores earlier indices."""
    if not text:
        return None
    found = FLOAT_RE.findall(text)
    if not found:
        return None
    try:
        return float(found[-1])
    except ValueError:
        return None


def apply_threshold(out: dict, rule: dict, message: str) -> dict:
    """If the rule carries a threshold, attach value_mm and mark anomaly when exceeded."""
    thr = rule.get("threshold")
    if thr is None:
        return out
    if out.get("event_id") in ("probe_error", "effector_error", "hip_error"):
        try:
            val = float(message.split()[-1])
        except (ValueError, IndexError):
            val = None
    else:
        val = extract_last_mm(message)
    if val is None or not math.isfinite(val) or val < 0:
        out.update(
            value_mm=None,
            threshold=thr,
            event_id=out.get("event_id", "") + "_invalid",
            mark="anomaly",
            timeline="show",
            notes="标定／配准误差无效（非有限数、负值或无法解析），不能作为有效完成证据",
        )
        return out
    out["value_mm"] = val
    out["threshold"] = thr
    if val > thr:
        out["mark"] = "anomaly"
    return out


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) or c == "" for c in cells)


def _col_field(header: str) -> str | None:
    h = header.strip()
    n = re.sub(r"\s+", "", h).lower()
    if n in ("event_id", "事件id"):
        return "event_id"
    if n in ("track", "轨道"):
        return "track"
    if n in ("parent", "父页面"):
        return "parent"
    if "日志匹配" in h or n in ("match", "pattern", "匹配"):
        return "match"
    if "匹配方式" in h or n in ("mode", "方式"):
        return "mode"
    if "软件步骤" in h or n in ("step",):
        return "step"
    if "类别" in h or "分类" in h or n == "category":
        return "category"
    if "时间轴" in h or n == "timeline":
        return "timeline"
    if "标注" in h or n == "mark":
        return "mark"
    if "阈值" in h or n in ("threshold", "thresh"):
        return "threshold"
    if "说明" in h or n in ("notes", "note", "备注"):
        return "notes"
    if "级别" in h or n == "level":
        return "level"
    if "步骤" in h and "源码" not in h and "顺序" not in h:
        return "step"
    return None


def _norm(value: str, aliases: dict[str, str], default: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return default
    if v in aliases:
        return aliases[v]
    for k, mapped in aliases.items():
        if k in v or v in k:
            return mapped
    return default


def _section_of(heading: str) -> str | None:
    h = heading.strip()
    hl = h.lower()
    if "设置与切换" in h or "设备控制操作" in h:
        return "operation"
    if any(k in h for k in ("软件页面与步骤", "业务顺序")):
        return "skip"
    if "噪声" in h or "noise" in hl:
        return "noise"
    if "异常" in h or "anomal" in hl:
        return "anomaly"
    if "关键信息" in h or "重点标注" in h:
        return "key"
    if "步骤映射" in h or "step mapping" in hl:
        return "mapping"
    return None


def parse_table(table_lines: list[str]) -> list[dict] | None:
    rows = [_cells(ln) for ln in table_lines if ln.strip()]
    if len(rows) < 2:
        return None
    headers = rows[0]
    fields = [_col_field(h) for h in headers]
    if "match" not in fields:
        return None
    start = 1
    if _is_separator(rows[1]):
        start = 2
    rules = []
    for row in rows[start:]:
        if _is_separator(row):
            continue
        rec: dict[str, str] = {}
        for i, field in enumerate(fields):
            if field is None:
                continue
            rec[field] = row[i] if i < len(row) else ""
        pattern = (rec.get("match") or "").strip()
        if not pattern or set(pattern) <= set("-: "):
            continue
        mode = _norm(rec.get("mode", ""), MODE_ALIASES, "contains")
        rule = {
            "match": pattern,
            "mode": mode,
            "step": (rec.get("step") or "").strip(),
            "category": _norm(rec.get("category", ""), CATEGORY_ALIASES, "other"),
            "timeline": _norm(rec.get("timeline", ""), TIMELINE_ALIASES, "show"),
            "mark": _norm(rec.get("mark", ""), MARK_ALIASES, "none"),
            "notes": (rec.get("notes") or "").strip(),
            "level": (rec.get("level") or "").strip().upper(),
            "threshold": parse_threshold_cell(rec.get("threshold") or ""),
            "event_id": rec.get("event_id", ""),
            "track": rec.get("track", ""),
            "parent": rec.get("parent", ""),
            "regex": None,
        }
        if mode == "regex":
            try:
                rule["regex"] = re.compile(pattern)
            except re.error:
                rule["mode"] = "contains"
                rule["notes"] = (
                    rule["notes"] + " [invalid regex, fallback contains]"
                ).strip()
        rules.append(rule)
    return rules


def parse_spec_text(text: str) -> dict:
    lines = text.splitlines()
    section = None
    buckets = {"mapping": [], "key": [], "operation": [], "anomaly": [], "noise": []}
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        mh = HEADING_RE.match(line)
        if mh:
            tagged = _section_of(mh.group(1))
            if tagged is not None:
                section = tagged
            i += 1
            continue
        if line.strip().startswith("|"):
            table = []
            while i < n and lines[i].strip().startswith("|"):
                table.append(lines[i])
                i += 1
            if section in buckets:
                parsed = parse_table(table)
                if parsed:
                    buckets[section].extend(parsed)
            continue
        i += 1
    return buckets


def rule_matches(rule: dict, text: str, level: str | None = None) -> bool:
    if not text:
        return False
    want_level = rule.get("level") or ""
    if want_level:
        allowed = {c for c in want_level.upper() if c in "TDIWEC"}
        if allowed and (level or "") not in allowed:
            return False
    mode = rule.get("mode") or "contains"
    pat = rule["match"]
    if mode == "prefix":
        return text.startswith(pat)
    if mode == "regex":
        rx = rule.get("regex")
        if rx is None:
            return False
        return rx.search(text) is not None
    return pat in text


class Spec:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else DEFAULT_SPEC
        self.mtime: float | None = None
        self.mapping: list[dict] = []
        self.key: list[dict] = []
        self.operation: list[dict] = []
        self.anomaly: list[dict] = []
        self.noise: list[dict] = []
        self.error: str | None = None
        self.loaded_at: float | None = None
        self.requirements = []
        self.limits = {"angle_key": 1.0, "angle_anomaly": 2.0}
        self.reload(force=True)

    def reload(self, force: bool = False) -> bool:
        if not self.path.exists():
            self.error = f"spec not found: {self.path}"
            self.mapping = self.key = self.operation = self.anomaly = self.noise = []
            return False
        mtime = self.path.stat().st_mtime
        if not force and self.mtime is not None and mtime == self.mtime:
            return False
        try:
            text = self.path.read_text(encoding="utf-8")
            buckets = parse_spec_text(text)
            limits = dict(self.limits)
            for key, val in re.findall(r"<!-- threshold:(\w+)=([0-9.]+) -->", text):
                if key in limits:
                    limits[key] = float(val)
            if limits["angle_key"] > limits["angle_anomaly"]:
                self.error = "角度提醒阈值不能大于异常阈值"
                return False
            required_section = text.split("## 必要步骤配置", 1)
            requirements = []
            if len(required_section) == 2:
                table = required_section[1].split("\n## ", 1)[0]
                for line in table.splitlines():
                    cells = _cells(line) if line.startswith("|") else []
                    if len(cells) == 4 and cells[0] not in ("要求ID", "---"):
                        requirements.append(
                            dict(
                                id=cells[0],
                                name=cells[1],
                                evidence=tuple(cells[2].split(",")),
                                when=cells[3],
                            )
                        )
            self.requirements = requirements
            self.limits = limits
            self.mapping = buckets["mapping"]
            self.key = buckets["key"]
            self.operation = buckets["operation"]
            self.anomaly = buckets["anomaly"]
            self.noise = buckets["noise"]
            self.mtime = mtime
            self.loaded_at = time.time()
            self.error = None
            return True
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            return False

    def maybe_reload(self) -> bool:
        return self.reload(force=False)

    def counts(self) -> dict:
        return {
            "mapping": len(self.mapping),
            "key": len(self.key),
            "operation": len(self.operation),
            "anomaly": len(self.anomaly),
            "noise": len(self.noise),
            "path": str(self.path),
            "error": self.error,
            "limits": self.limits,
        }

    def classify(self, message: str, raw: str, level: str | None) -> dict:
        """Apply match priority from the spec:

        1. log level E/C (including empty ---E---) -> anomaly
        2. anomaly table
        3. settings/switch/control operations (retain specific business mappings)
        4. noise table, then step mapping + key-info tables
        5. unmatched parsed lines hidden by default
        """
        msg = message or ""
        haystacks = [msg]
        if raw and raw != msg:
            haystacks.append(raw)

        def first_hit(rules: list[dict]) -> dict | None:
            for rule in rules:
                for text in haystacks:
                    if rule_matches(rule, text, level):
                        return rule
            return None

        operation = first_hit(self.operation)
        hit = None
        src = "unmatched"
        for source, rules in (
            ("anomaly", self.anomaly),
            ("noise", self.noise),
            ("mapping", self.mapping),
            ("key", self.key),
        ):
            hit = first_hit(rules)
            if hit:
                src = source
                break
            if source == "anomaly" and operation:
                # Broad transport/state-machine noise must not swallow actions.
                # Preserve page/task identity and named settings before fallback.
                mapping = first_hit(self.mapping)
                key = first_hit(self.key) if mapping is None else None
                hit = mapping or key or operation
                src = "mapping" if mapping else "key" if key else "operation"
                break
        out = (
            apply_threshold(_from_rule(hit, src), hit, msg)
            if hit
            else {
                "step": "",
                "category": "other",
                "timeline": "hide",
                "mark": "none",
                "source": "unmatched",
                "rule": "",
                "event_id": "",
                "track": "",
                "parent": "",
            }
        )
        if level in ("E", "C"):
            out.update(mark="anomaly", timeline="show")
            if not hit:
                out.update(
                    step="空错误行" if not msg.strip() else msg.strip()[:80],
                    source="level",
                    rule=f"level:{level}",
                )
        elif level == "W":
            if out["source"] == "noise":
                out.update(
                    category="other", mark="key", timeline="show", source="level"
                )
                out["notes"] = (
                    out.get("notes", "") + "；警告级转储保留为排查提醒"
                ).strip("；")
            elif not hit:
                out.update(step="警告", mark="key", timeline="show", source="level")
        return out


def _from_rule(rule: dict, source: str) -> dict:
    return {
        "step": rule.get("step") or "",
        "category": rule.get("category") or "other",
        "timeline": rule.get("timeline") or "show",
        "mark": rule.get("mark") or "none",
        "source": source,
        "rule": rule.get("match") or "",
        "event_id": rule.get("event_id") or "",
        "track": rule.get("track") or "",
        "parent": rule.get("parent") or "",
        "notes": rule.get("notes") or "",
    }
