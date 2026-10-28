"""Regression tests use generated messages only; no hospital records."""

import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from parser import (
    parse_log_lines,
    classify_events,
    inspect_content,
    parse_and_classify,
    summarize,
)
from spec import Spec
from nle import build_nle, collect_cut_deltas
from store import Store

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
START = "Oberon Application Startup version 2.9.0"


def line(msg, level="I", tz="+08:00"):
    return f"[10:00:00 {tz}] [Daily_logger] [---{level}---] [thread 1] {msg}"


def analyze(messages, spec=None):
    lines = [line(m) for m in messages]
    ev = classify_events(parse_log_lines(lines, None), spec or Spec())
    return ev, build_nle(ev, lines)


def load(uid=A):
    return f"start load plan uuid: {{{uid}}}"


class AnalysisTests(unittest.TestCase):
    def test_timezone_bom_crlf_and_original(self):
        for tz in ("+0800", "+08:00", "-0500"):
            raw = "\ufeff" + line(START, tz=tz) + "\r\n"
            ev = parse_log_lines([raw], None)[0]
            self.assertTrue(ev["parsed"])
            self.assertEqual(ev["raw"], raw.rstrip("\r\n"))

    def test_crash_header_and_backtrace_one_event(self):
        ls = [
            line("", "E"),
            "=== CRASH DETECTED ===",
            "Caught signal 11",
            "#0 frame",
            "END OF BACKTRACE",
            line(START),
        ]
        ev = classify_events(parse_log_lines(ls, None), Spec())
        self.assertEqual(len(ev), 2)
        self.assertEqual(ev[0]["line_end"], 5)
        self.assertEqual(ev[0]["event_id"], "crash")
        self.assertEqual(summarize(ev)["anomaly"], 1)

    def test_invalid_and_wrong_product(self):
        for b in (b"", b"\x00" * 20, b" \n", b"Titan Application Startup version 1"):
            with self.assertRaises(ValueError):
                inspect_content(b)

    def test_unknown_and_partial(self):
        self.assertFalse(inspect_content(b"unrelated")["analyzable"])
        self.assertTrue(inspect_content(line(load()).encode())["partial"])

    def test_fragment_generates_summary(self):
        _, n = analyze([load(), "start operation", "switch polish hip step"])
        self.assertEqual(len(n["summaries"]), 1)
        self.assertTrue(n["tracks"]["sessions"][0]["partial"])

    def test_two_plans_and_metadata_no_bleed(self):
        _, n = analyze(
            [
                START,
                load(),
                "switch cup type: 48",
                "operation side left",
                "start operation",
                load(B),
                "switch cup type: 52",
                "operation side right",
                "start operation",
            ]
        )
        cards = n["summaries"]
        self.assertEqual(len(cards), 2)
        self.assertIn("48", cards[0]["label"])
        self.assertIn("左", cards[0]["label"])
        self.assertIn("52", cards[1]["label"])
        self.assertIn("右", cards[1]["label"])

    def test_click_does_not_start(self):
        _, n = analyze([START, load(), "click start operation"])
        self.assertFalse(n["summaries"][0]["started"])

    def test_no_cross_plan_or_restart_delta(self):
        for boundary in (load(B), START):
            ev, _ = analyze(
                [
                    START,
                    load(),
                    "ras coordinate plan anteversion:20 , inclination:40",
                    boundary,
                    "ras coordinate realtime anteversion:20 , inclination:44, depth:3",
                ]
            )
            self.assertTrue(all(m["delta"] is None for m in ev[-1]["metrics"]))

    def test_coordinate_targets_and_depth(self):
        ev, _ = analyze(
            [
                START,
                load(),
                "ras coordinate plan anteversion:20 , inclination:40",
                "app coordinate plan anteversion:10 , inclination:30",
                "app coordinate realtime anteversion:10 , inclination:30, depth:4",
                "ras coordinate realtime anteversion:20 , inclination:43, depth:2",
            ]
        )
        self.assertEqual(ev[-2]["metrics"][0]["delta"], 0)
        self.assertEqual(ev[-1]["metrics"][0]["delta"], 3)
        self.assertIsNone(ev[-1]["metrics"][2]["delta"])

    def test_explicit_target_precedes_legacy(self):
        ev, _ = analyze(
            [
                START,
                load(),
                "ras coordinate plan anteversion:20 , inclination:40",
                "planviewer hand over,plan inclination: 50, plan anterversion: 30",
                "ras coordinate realtime anteversion:20 , inclination:40, depth:1",
            ]
        )
        self.assertEqual(ev[-1]["metrics"][0]["plan"], 40)

    def test_threshold_boundaries_and_count_consistency(self):
        for delta, mark in ((1, "none"), (1.01, "key"), (2, "key"), (2.01, "key")):
            ev, n = analyze(
                [
                    START,
                    load(),
                    "ras coordinate plan anteversion:20 , inclination:40",
                    f"ras coordinate realtime anteversion:20 , inclination:{40+delta}, depth:1",
                ]
            )
            self.assertEqual(ev[-1]["mark"], mark)
            self.assertEqual(summarize(ev)["anomaly"], len(n["ticks"]["anomaly"]))

    def test_two_exceeded_values_one_event(self):
        ev, n = analyze(
            [
                START,
                load(),
                "ras coordinate plan anteversion:20 , inclination:40",
                "ras coordinate realtime anteversion:25 , inclination:45, depth:1",
            ]
        )
        self.assertEqual(summarize(ev)["anomaly"], 0)
        self.assertTrue(
            all(m["threshold_level"] == "anomaly" for m in ev[-1]["metrics"][:2])
        )

    def test_zero_variant_is_noise(self):
        ev, _ = analyze(
            [
                START,
                "app coordinate realtime anteversion:0.0 , inclination:0.00, depth:0.0",
            ]
        )
        self.assertEqual(ev[-1]["category"], "noise")
        self.assertNotIn("metrics", ev[-1])

    def test_planning_window_restarts_on_reload_and_ends_at_postop(self):
        _, n = analyze(
            [
                START,
                load(),
                "start operation",
                "switch polish hip step",
                load(),
                "ras coordinate plan anteversion:20 , inclination:40",
                "start operation",
            ]
        )
        self.assertTrue(
            next(x for x in n["summaries"][0]["steps"] if x["id"] == "plan_target")[
                "ok"
            ]
        )
        _, n = analyze(
            [
                START,
                load(),
                "start operation",
                "enter poster operation page",
                "ras coordinate plan anteversion:20 , inclination:40",
            ]
        )
        self.assertFalse(
            next(x for x in n["summaries"][0]["steps"] if x["id"] == "plan_target")[
                "ok"
            ]
        )
        cls = Spec().classify("kuka and ndi states are fault", "", "I")
        self.assertEqual(cls["event_id"], "devices_fault")

    def test_faults_operations_and_warning_semantics(self):
        for message in (
            "kuka app is disconnected",
            "ras coordinate realtime anteversion:0 , inclination:0, depth:0",
        ):
            events = classify_events(
                parse_log_lines([line(message, "E")], None), Spec()
            )
            build_nle(events, [line(message, "E")])
            self.assertEqual(events[0]["mark"], "anomaly")
            self.assertEqual(events[0]["timeline"], "show")
        for msg in (
            "ndi states are fault",
            "kuka and ndi states are fault",
            "hip marker offset is too big, fix-line motion stops",
            "robot command response exception catched: Motion Failed.",
            "probe compensate reamer fail",
        ):
            self.assertEqual(Spec().classify(msg, msg, "I")["mark"], "anomaly")
        cls = Spec().classify("cart teach button is pressed", "", "E")
        self.assertEqual(cls["event_id"], "teach_pressed")
        self.assertEqual(cls["mark"], "anomaly")
        self.assertEqual(Spec().classify("new warning", "", "W")["timeline"], "show")

    def test_no_later_step_borrowing(self):
        ev, n = analyze(
            [
                START,
                load(),
                "switch polish hip step",
                "switch install hip cup step",
                "ras coordinate plan anteversion:20 , inclination:40",
                "ras coordinate realtime anteversion:20 , inclination:40, depth:1",
            ]
        )
        spans = n["tracks"]["l2"]
        self.assertTrue(all(x.get("missing") for x in spans[0]["cut_deltas"]))
        self.assertTrue(all(not x.get("missing") for x in spans[1]["cut_deltas"]))

    def test_clear_keeps_historical_evidence(self):
        _, n = analyze(
            [
                START,
                load(),
                "start operation",
                "switch register hip step",
                "hip register calculate error 0.5",
                "clear dense, register result reverted to coarse",
            ]
        )
        step = next(s for s in n["summaries"][0]["steps"] if s["id"] == "hip_register")
        self.assertTrue(step["ok"])
        self.assertEqual(step["evidence"]["line"], 5)
        self.assertFalse(n["tracks"]["l2"][0].get("errors"))

    def test_hot_reload_threshold_and_label(self):
        src = Spec().path.read_text()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rules.md"
            p.write_text(src)
            sp = Spec(p)
            p.write_text(
                src.replace(
                    "threshold:angle_anomaly=2", "threshold:angle_anomaly=5"
                ).replace("设备准备 | page", "准备设备 | page")
            )
            sp.reload(force=True)
            ev, _ = analyze(
                [
                    START,
                    "ras coordinate plan anteversion:20 , inclination:40",
                    "ras coordinate realtime anteversion:20 , inclination:43, depth:1",
                ],
                sp,
            )
            self.assertEqual(ev[-1]["mark"], "key")

    def test_discontiguous_cases_do_not_cover_other_plan(self):
        _, n = analyze(
            [START, load(), "start operation", load(B), "click start operation", load()]
        )
        self.assertEqual(len(n["summaries"]), 2)
        self.assertTrue(n["summaries"][0]["started"])
        self.assertFalse(n["summaries"][1]["started"])
        a_ranges = [c for c in n["tracks"]["cases"] if c["uuid"] == A]
        self.assertEqual([(c["start"], c["end"]) for c in a_ranges], [(2, 3), (6, 6)])

    def test_crash_ticks_count_one(self):
        ls = [
            line(START),
            line(load()),
            line("switch polish hip step"),
            line("", "E"),
            "CRASH DETECTED",
            "Caught signal 11",
            "#0 frame",
        ]
        es = classify_events(parse_log_lines(ls, None), Spec())
        n = build_nle(es, ls)
        self.assertEqual(len(n["ticks"]["anomaly"]), 1)
        self.assertEqual(n["tracks"]["l2"][0]["end"], 3)

    def test_idempotent_analysis(self):
        es, _ = analyze(
            [
                START,
                load(),
                "ras coordinate plan anteversion:20 , inclination:40",
                "ras coordinate realtime anteversion:24 , inclination:44, depth:1",
            ]
        )
        before = summarize(es)
        for _ in range(2):
            collect_cut_deltas(es)
        self.assertEqual(summarize(es), before)

    def test_summary_configuration_uses_stable_identity(self):
        src = Spec().path.read_text()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rules.md"
            p.write_text(
                src.replace(
                    "| hip_nail | 安装髋标记钉 | hip_nail |",
                    "| hip_nail | 钉安装检查 | hip_nail |",
                )
            )
            es, n = analyze(
                [START, load(), "start operation", "switch install hip mark nail step"],
                Spec(p),
            )
            step = next(s for s in n["summaries"][0]["steps"] if s["id"] == "hip_nail")
            self.assertTrue(step["ok"])
            self.assertEqual(step["name"], "钉安装检查")

    def test_window_keeps_full_timeline(self):
        for count in (30001, 80001):
            ls = (
                [line(START), line(load()), line("start operation")]
                + [line("current torque, t1:0")] * (count - 4)
                + [line("ndi states are fault")]
            )
            ev = classify_events(parse_log_lines(ls, None), Spec())
            n = build_nle(ev, ls, center=count)
            self.assertTrue(n["lines_windowed"])
            self.assertEqual(n["lines_end"], count)
            self.assertIn(count, n["ticks"]["anomaly"])

    def test_store_hash_and_legacy_records(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            one = store.add("a.txt", b"aa", {})
            dup = store.add("renamed.txt", b"aa", {})
            self.assertTrue(dup["duplicate"])
            self.assertEqual(one["id"], dup["id"])
            two = store.add("a.txt", b"bb", {})
            self.assertNotEqual(two["id"], one["id"])
            data = store._load()
            data["logs"][0].pop("sha256")
            store._save(data)
            self.assertTrue(store.add("again.txt", b"aa", {})["duplicate"])

    def test_original_date_and_unknown_raw_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "copy.txt"
            p.write_text(line(START))
            _, m = parse_and_classify(p, Spec(), "renamed.txt", 0)
            self.assertEqual(m["date"], "1970-01-01")
            self.assertEqual(m["date_source"], "mtime")
            _, m = parse_and_classify(p, Spec(), "renamed.txt")
            self.assertEqual(m["date_source"], "unknown")
            p.write_text(line("start operation"))
            ev, m = parse_and_classify(p, Spec())
            self.assertEqual(ev, [])
            self.assertFalse(m["file_quality"]["analyzable"])


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["LOG_TOOL_DATA_DIR"] = cls.tmp.name
        cls.main = importlib.import_module("app.main")
        cls.old = cls.main.STORE
        cls.main.STORE = Store(Path(cls.tmp.name))
        cls.server = cls.main.ThreadingHTTPServer(("127.0.0.1", 0), cls.main.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.main.STORE = cls.old
        cls.tmp.cleanup()
        os.environ.pop("LOG_TOOL_DATA_DIR", None)

    def test_import_search_and_date_api(self):
        p = Path(self.tmp.name) / "source.txt"
        p.write_text(
            "\n".join(
                [
                    line(START),
                    line(load()),
                    line("current torque, t1:3"),
                    line("ndi states are fault"),
                ]
            )
        )
        os.utime(p, (0, 0))
        req = Request(
            self.url + "/api/logs/import-path",
            data=json.dumps({"path": str(p)}).encode(),
            headers={"Content-Type": "application/json"},
        )
        result = json.load(urlopen(req))
        rec = result["imported"][0]
        payload = json.load(
            urlopen(self.url + f"/api/logs/{rec['id']}/timeline?q=torque&after=1")
        )
        self.assertEqual(payload["search"]["line"], 3)
        self.assertEqual(payload["date"], "1970-01-01")
        self.assertEqual(payload["counts"]["anomaly"], 1)
        self.assertEqual(payload["lines"][-1]["event_id"], "ndi_fault")

    def test_anomaly_review_public_payload_and_counts(self):
        p = Path(self.tmp.name) / "anomaly-review.txt"
        p.write_text(
            "\n".join(
                line(m)
                for m in [
                    "connect mxio failed",
                    "use custom module control robot teach",
                    START,
                    load(),
                    "start operation",
                    "ras coordinate plan anteversion:20 , inclination:40",
                    "ras coordinate realtime anteversion:25 , inclination:45, depth:1",
                    "probe calibration error nan",
                    "ndi states are fault",
                ]
            )
        )
        req = Request(
            self.url + "/api/logs/import-path",
            data=json.dumps({"path": str(p)}).encode(),
            headers={"Content-Type": "application/json"},
        )
        rec = json.load(urlopen(req))["imported"][0]
        payload = json.loads(
            urlopen(self.url + f"/api/logs/{rec['id']}/timeline").read(),
            parse_constant=lambda v: self.fail(f"Nonfinite JSON value {v}"),
        )
        self.assertEqual(payload["counts"]["anomaly"], 2)
        self.assertEqual(payload["ticks"]["anomaly"], [8, 9])
        pose = next(e for e in payload["events"] if e["line"] == 7)
        self.assertEqual(pose["mark"], "key")
        self.assertEqual(pose["metrics"][0]["threshold_level"], "anomaly")
        self.assertEqual(
            payload["lines"][6]["metrics"][0]["assessment"], "process_snapshot"
        )
        self.assertIn("监听", payload["events"][0]["notes"])
        listed = json.load(urlopen(self.url + "/api/logs"))["logs"]
        self.assertEqual(
            next(r for r in listed if r["id"] == rec["id"])["counts"]["anomaly"], 2
        )

    def test_browser_multipart_mtime_and_partial_batch(self):
        boundary = "test-boundary"
        pieces = []

        def field(name, value, filename=None):
            header = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
            if filename:
                header += f'; filename="{filename}"'
            pieces.append(header.encode() + b"\r\n\r\n" + value + b"\r\n")

        field("files", line(START).encode(), "browser.txt")
        field("files", b"\0" * 12, "zero.txt")
        field("last_modified", json.dumps({"browser.txt": 1000}).encode())
        body = b"".join(pieces) + f"--{boundary}--\r\n".encode()
        result = json.load(
            urlopen(
                Request(
                    self.url + "/api/logs",
                    data=body,
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}"
                    },
                )
            )
        )
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(len(result["imported"]), 1)
        self.assertEqual(result["imported"][0]["source_mtime"], 1)
        self.assertEqual(result["imported"][0]["date"], "1970-01-01")


if __name__ == "__main__":
    unittest.main()
