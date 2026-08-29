"""Parse docs/oberon-log-spec.md markdown tables into match rules.

Classification tables must have a 日志匹配 / match column. The business-order
table (顺序 / 源码页面) and the 级别规则 table are skipped automatically.

Section keywords: 步骤映射, 关键信息, 异常, 噪声.
"""
from __future__ import annotations

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
    val = extract_last_mm(message)
    if val is None:
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
            "regex": None,
        }
        if mode == "regex":
            try:
                rule["regex"] = re.compile(pattern)
            except re.error:
                rule["mode"] = "contains"
                rule["notes"] = (rule["notes"] + " [invalid regex, fallback contains]").strip()
        rules.append(rule)
    return rules


def parse_spec_text(text: str) -> dict:
    lines = text.splitlines()
    section = None
    buckets = {"mapping": [], "key": [], "anomaly": [], "noise": []}
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
        self.anomaly: list[dict] = []
        self.noise: list[dict] = []
        self.error: str | None = None
        self.loaded_at: float | None = None
        self.reload(force=True)

    def reload(self, force: bool = False) -> bool:
        if not self.path.exists():
            self.error = f"spec not found: {self.path}"
            self.mapping = self.key = self.anomaly = self.noise = []
            return False
        mtime = self.path.stat().st_mtime
        if not force and self.mtime is not None and mtime == self.mtime:
            return False
        try:
            text = self.path.read_text(encoding="utf-8")
            buckets = parse_spec_text(text)
            self.mapping = buckets["mapping"]
            self.key = buckets["key"]
            self.anomaly = buckets["anomaly"]
            self.noise = buckets["noise"]
            self.mtime = mtime
            self.loaded_at = time.time()
            self.error = None
            return True
        except OSError as exc:
            self.error = str(exc)
            return False

    def maybe_reload(self) -> bool:
        return self.reload(force=False)

    def counts(self) -> dict:
        return {
            "mapping": len(self.mapping),
            "key": len(self.key),
            "anomaly": len(self.anomaly),
            "noise": len(self.noise),
            "path": str(self.path),
            "error": self.error,
        }

    def classify(self, message: str, raw: str, level: str | None) -> dict:
        """Apply match priority from the spec:

        1. log level E/C (including empty ---E---) -> anomaly
        2. anomaly table
        3. noise table
        4. step mapping + key-info tables
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

        if level in ("E", "C"):
            empty = not msg.strip()
            return {
                "step": "空错误行" if empty else (msg.strip()[:80] or "错误"),
                "category": "other",
                "timeline": "show",
                "mark": "anomaly",
                "source": "level",
                "rule": f"level:{level}",
            }

        hit = first_hit(self.anomaly)
        if hit:
            return _from_rule(hit, "anomaly")

        hit = first_hit(self.noise)
        if hit:
            out = _from_rule(hit, "noise")
            out["timeline"] = hit.get("timeline") or "hide"
            out["category"] = hit.get("category") or "noise"
            return out

        hit = first_hit(self.mapping) or first_hit(self.key)
        if hit:
            src = "mapping" if hit in self.mapping else "key"
            return apply_threshold(_from_rule(hit, src), hit, msg)

        return {
            "step": "",
            "category": "other",
            "timeline": "hide",
            "mark": "none",
            "source": "unmatched",
            "rule": "",
        }


def _from_rule(rule: dict, source: str) -> dict:
    return {
        "step": rule.get("step") or "",
        "category": rule.get("category") or "other",
        "timeline": rule.get("timeline") or "show",
        "mark": rule.get("mark") or "none",
        "source": source,
        "rule": rule.get("match") or "",
    }
