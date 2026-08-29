"""Stdlib tests for Oberon spec / NLE (no Flask, no pip)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from nle import build_nle, collect_cut_deltas  # noqa: E402
from parser import classify_events, parse_and_classify, parse_log_lines  # noqa: E402
from spec import Spec  # noqa: E402

SPEC = Spec(ROOT / "docs" / "oberon-log-spec.md")


def _line(n: int, msg: str, level: str = "I", t: str = "10:00:00") -> str:
    return f"[{t} +08:00] [Daily_logger] [---{level}---] [thread 1] {msg}"


class SpecTests(unittest.TestCase):
    def test_spec_loads(self):
        self.assertIsNone(SPEC.error)
        self.assertGreater(SPEC.counts()["mapping"], 10)
        self.assertGreater(SPEC.counts()["noise"], 5)
        self.assertGreater(SPEC.counts()["anomaly"], 3)

    def test_no_ndi_failed_rule(self):
        hay = " ".join(r["match"] for r in SPEC.anomaly + SPEC.mapping + SPEC.key)
        self.assertNotIn("connect ndi failed", hay)

    def test_threshold_only_on_error_amplitude(self):
        keyed = [r for r in SPEC.key if r.get("threshold") is not None]
        matches = {r["match"] for r in keyed}
        self.assertEqual(
            matches,
            {
                "probe calibration error",
                "effector calibration error",
                "hip register calculate error",
            },
        )
        for r in SPEC.key:
            if "plan inclination" in r["match"] or "ras coordinate realtime" in r["match"]:
                self.assertIsNone(r.get("threshold"))

    def test_match_order_ec_then_anomaly_then_noise(self):
        empty_e = SPEC.classify("", "[12:00:00 +08:00] [Daily_logger] [---E---] [thread 1] ", "E")
        self.assertEqual(empty_e["mark"], "anomaly")
        self.assertEqual(empty_e["step"], "空错误行")
        crash = SPEC.classify("===== CRASH DETECTED =====", "CRASH DETECTED", None)
        self.assertEqual(crash["source"], "anomaly")
        torque = SPEC.classify("record torque, t1:1", "record torque, t1:1", "I")
        self.assertEqual(torque["source"], "noise")
        zero = SPEC.classify(
            "ras coordinate realtime anteversion:0 , inclination:0, depth:0",
            "",
            "I",
        )
        self.assertEqual(zero["source"], "noise")
        start = SPEC.classify("start operation", "start operation", "I")
        self.assertEqual(start["step"], "开始手术")
        self.assertEqual(start["mark"], "key")

    def test_tool_selection_is_key(self):
        named = SPEC.classify("set tool type new metal tool", "", "I")
        self.assertEqual(named["step"], "选择工具类型")
        self.assertEqual(named["mark"], "key")
        self.assertEqual(named["timeline"], "show")
        side = SPEC.classify("set tool side left", "", "I")
        self.assertEqual(side["step"], "选择工具侧别")
        self.assertEqual(side["mark"], "key")
        reamer = SPEC.classify("set reamer rod: right rod", "", "I")
        self.assertEqual(reamer["step"], "选择磨头杆")
        self.assertEqual(reamer["mark"], "key")
        cup = SPEC.classify("set cup rod:  yozx install rod", "", "I")
        self.assertEqual(cup["step"], "选择装杯杆")
        self.assertEqual(cup["mark"], "key")
        echo_colon = SPEC.classify("set tool type: 2", "", "I")
        self.assertEqual(echo_colon["timeline"], "hide")
        self.assertNotEqual(echo_colon["mark"], "key")
        echo_num = SPEC.classify("set tool type 2", "", "I")
        self.assertEqual(echo_num["timeline"], "hide")
        self.assertNotEqual(echo_num["mark"], "key")
        echo_side = SPEC.classify("set tool side 1", "", "I")
        self.assertEqual(echo_side["timeline"], "hide")
        self.assertNotEqual(echo_side["mark"], "key")


class NleTests(unittest.TestCase):
    def test_uuid_merge_and_labels(self):
        uid = "78828786-c0d4-41dd-b1b3-ac1fea432abe"
        lines = [
            _line(1, "Oberon Application Startup  version 2.9.0.20260330", "D", "10:00:00"),
            _line(2, f"start load plan uuid: {{{uid}}}"),
            _line(3, "switch cup type: 50/42"),
            _line(4, "patient name 张三,gender 男, age 60, entry side 后外侧,operation side 左"),
            _line(5, "start operation"),
            _line(6, "Oberon Application Startup  version 2.9.0.20260330", "D", "11:00:00"),
            _line(7, f"start load plan uuid: {{{uid}}}"),
            _line(8, "switch cup type: 50/42"),
            _line(9, "patient name 张三,gender 男, age 60, entry side 后外侧,operation side 左"),
        ]
        events = classify_events(parse_log_lines(lines, "2026-04-01"), SPEC)
        nle = build_nle(events, lines)
        cases = [c for c in nle["tracks"]["cases"] if c.get("uuid")]
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["uuid"], uid)
        self.assertIn("50/42", cases[0]["label"])
        self.assertIn("左", cases[0]["label"])
        self.assertNotIn("张三", cases[0]["label"])
        self.assertEqual(len(nle["summaries"]), 1)
        self.assertTrue(nle["summaries"][0]["started"])
        pins = [m for m in nle["tracks"]["markers"] if m.get("kind") == "startup"]
        self.assertGreaterEqual(len(pins), 2)
        self.assertEqual(pins[0].get("version"), "2.9.0.20260330")

    def test_empty_startup_no_card(self):
        lines = [
            _line(1, "Oberon Application Startup  version 2.9.0.20260330", "D"),
            _line(2, "detect net ip 127.0.0.1"),
        ]
        events = classify_events(parse_log_lines(lines, None), SPEC)
        nle = build_nle(events, lines)
        self.assertEqual(nle["summaries"], [])
        self.assertTrue(any(c.get("label") == "未打开方案" for c in nle["tracks"]["cases"]))

    def test_loaded_not_started(self):
        uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        lines = [
            _line(1, "Oberon Application Startup  version 2.8.0.20251027", "D"),
            _line(2, f"start load plan uuid: {{{uid}}}"),
            _line(3, "switch cup type: 48"),
            _line(4, "patient name X,gender NA, age 0, entry side 后外侧,operation side 右"),
        ]
        events = classify_events(parse_log_lines(lines, None), SPEC)
        nle = build_nle(events, lines)
        self.assertEqual(len(nle["summaries"]), 1)
        self.assertFalse(nle["summaries"][0]["started"])
        self.assertEqual(nle["summaries"][0]["steps"], [])

    def test_required_steps_evidence(self):
        uid = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
        lines = [
            _line(1, "Oberon Application Startup  version 2.9.0", "D"),
            _line(2, f"start load plan uuid: {{{uid}}}"),
            _line(3, "start operation"),
            _line(4, "enter device prepare page"),
            _line(5, "probe calibration error 0.06"),
            _line(6, "planviewer hand over,plan inclination: 40.0, plan anterversion: 20.0"),
            _line(7, "enter hip navigation page"),
            _line(8, "switch install hip mark nail step"),
            _line(9, "switch register hip step"),
            _line(10, "hip register calculate error 0.5"),
            _line(11, "switch polish hip step"),
            _line(12, "ras coordinate realtime anteversion:19.2 , inclination:41.5, depth:2.1"),
            _line(13, "switch install hip cup step"),
            _line(14, "switch verify hip cup install step"),
            _line(15, "cup verified point:x:1, y:2, z:3"),
        ]
        events = classify_events(parse_log_lines(lines, None), SPEC)
        nle = build_nle(events, lines)
        steps = {s["id"]: s for s in nle["summaries"][0]["steps"]}
        for sid in (
            "device_prepare",
            "probe_cal",
            "plan_target",
            "hip_nail",
            "hip_register",
            "hip_polish",
            "hip_cup",
            "hip_verify",
        ):
            self.assertTrue(steps[sid]["ok"], sid)
        l1 = {s["label"] for s in nle["tracks"]["l1"]}
        self.assertIn("设备准备", l1)
        self.assertIn("髋导航", l1)
        l2 = {s["label"] for s in nle["tracks"]["l2"]}
        self.assertIn("髋配准", l2)
        self.assertIn("髋臼打磨", l2)

    def test_planning_window_ignores_postop_planviewer(self):
        uid = "cccccccc-dddd-eeee-ffff-000000000000"
        lines = [
            _line(1, "Oberon Application Startup  version 2.9.0", "D"),
            _line(2, f"start load plan uuid: {{{uid}}}"),
            _line(3, "start operation"),
            _line(4, "enter device prepare page"),
            _line(5, "switch polish hip step"),
            _line(6, "planviewer hand over,plan inclination: 40.0, plan anterversion: 20.0"),
        ]
        events = classify_events(parse_log_lines(lines, None), SPEC)
        nle = build_nle(events, lines)
        plan = next(s for s in nle["summaries"][0]["steps"] if s["id"] == "plan_target")
        self.assertFalse(plan["ok"])
        self.assertIn("术后", plan.get("missing_detail") or "")

    def test_zero_ras_not_measured_and_delta_flags(self):
        lines = [
            _line(1, "Oberon Application Startup  version 2.9.0", "D"),
            _line(2, "planviewer hand over,plan inclination: 40.0, plan anterversion: 20.0"),
            _line(3, "ras coordinate realtime anteversion:0 , inclination:0, depth:0"),
            _line(4, "ras coordinate realtime anteversion:20.0 , inclination:43.5, depth:1.2"),
        ]
        events = classify_events(parse_log_lines(lines, None), SPEC)
        items, flags = collect_cut_deltas(events)
        self.assertTrue(all(it["measured"] != 0 or it["label"] != "外展角" or it["line"] != 3 for it in items))
        self.assertTrue(all(it["line"] != 3 for it in items))
        inc = next(it for it in items if it["label"] == "外展角")
        self.assertAlmostEqual(inc["delta"], 3.5)
        self.assertEqual(inc["level"], "anomaly")
        self.assertTrue(any(f["level"] == "anomaly" for f in flags))

    def test_kuka_disconnect_only_after_start(self):
        lines = [
            _line(1, "Oberon Application Startup  version 2.9.0", "D"),
            _line(2, "kuka app is disconnected"),
            _line(3, "start load plan uuid: {11111111-1111-1111-1111-111111111111}"),
            _line(4, "start operation"),
            _line(5, "kuka app is disconnected"),
        ]
        events = classify_events(parse_log_lines(lines, None), SPEC)
        pre = next(e for e in events if e["line"] == 2)
        post = next(e for e in events if e["line"] == 5)
        self.assertEqual(pre["timeline"], "hide")
        self.assertEqual(post["mark"], "anomaly")

    def test_crash_block(self):
        lines = [
            _line(1, "Oberon Application Startup  version 2.9.0", "D"),
            "===== CRASH DETECTED =====",
            "Caught signal 6 (SIGABRT (Aborted)), printing backtrace:",
            _line(4, "start operation"),
        ]
        events = parse_log_lines(lines, None)
        blocks = [e for e in events if e.get("block")]
        self.assertTrue(blocks)
        self.assertIn("CRASH DETECTED", blocks[0]["raw"])
        classified = classify_events(events, SPEC)
        crash = next(e for e in classified if e.get("block"))
        self.assertEqual(crash["mark"], "anomaly")

    def test_parse_and_classify_tempfile(self):
        text = "\n".join(
            [
                _line(1, "Oberon Application Startup  version 2.5.1.20241101", "D"),
                _line(2, "rebooting sirius"),
            ]
        )
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
            path = Path(f.name)
        try:
            events, meta = parse_and_classify(path, SPEC, "tha_log_file_2026-04-27.txt")
            self.assertEqual(meta["date"], "2026-04-27")
            self.assertEqual(meta["date_source"], "filename")
            self.assertGreaterEqual(meta["parsed"], 2)
            self.assertTrue(any(e.get("session") == "startup" for e in events))
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
