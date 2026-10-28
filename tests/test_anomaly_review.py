"""Anomaly regression uses synthetic messages, without patient records."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from nle import build_nle, collect_cut_deltas
from parser import classify_events, filter_events, parse_log_lines, summarize
from spec import Spec

START = "Oberon Application Startup version 2.9.0"
LOAD = "start load plan uuid: {11111111-1111-1111-1111-111111111111}"
TARGET = "ras coordinate plan anteversion:20 , inclination:40"
POSE = "ras coordinate realtime anteversion:25 , inclination:45, depth:-2"
MANUAL = "manual rebooting sirius triggerred ..."


def analyze(messages, levels=None, spec=None):
    levels = levels or ["I"] * len(messages)
    lines = [
        f"[10:00:00 +0800] [Daily_logger] [---{level}---] [thread 1] {msg}"
        for msg, level in zip(messages, levels)
    ]
    events = classify_events(parse_log_lines(lines, None), spec or Spec())
    nle = build_nle(events, lines)
    return events, nle


class AnomalyReviewTests(unittest.TestCase):
    def test_normal_actions_and_snapshot_are_not_faults(self):
        events, nle = analyze(
            [
                START,
                LOAD,
                "start operation",
                TARGET,
                "switch polish hip step",
                "send kuka cmd: fixLine",
                POSE,
                "robot no motion joint, a1:0 a2:1",
                "switch install hip cup step",
                "standby cmd called by step change",
                POSE,
            ]
        )
        self.assertEqual(summarize(events)["anomaly"], 0)
        self.assertEqual(nle["ticks"]["anomaly"], [])
        metric = events[-1]["metrics"][0]
        self.assertEqual(metric["threshold_level"], "anomaly")
        self.assertEqual(metric["assessment"], "process_snapshot")
        self.assertEqual(metric["delta"], 5)
        self.assertEqual(events[-1]["mark"], "key")
        self.assertEqual(events[-1]["metrics"][2]["measured"], -2)

    def test_snapshot_in_verify_page_is_still_process_measurement(self):
        events, _ = analyze(
            [
                START,
                LOAD,
                "start operation",
                TARGET,
                "switch verify hip cup install step",
                POSE,
            ]
        )
        self.assertEqual(events[-1]["context"]["step_id"], "hip_verify")
        self.assertNotEqual(events[-1]["mark"], "anomaly")

    def test_snapshot_never_downgrades_error_level(self):
        for level in ("E", "C"):
            events, nle = analyze([START, TARGET, POSE], ["I", "I", level])
            self.assertEqual(events[-1]["mark"], "anomaly")
            self.assertEqual(nle["ticks"]["anomaly"], [3])

    def test_angle_thresholds_survive_hot_reload(self):
        src = Spec().path.read_text()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rules.md"
            p.write_text(src)
            spec = Spec(p)
            first, _ = analyze([START, TARGET, POSE], spec=spec)
            self.assertTrue(first[-1]["metrics"][0]["over2"])
            p.write_text(
                src.replace("threshold:angle_anomaly=2", "threshold:angle_anomaly=6")
            )
            spec.reload(force=True)
            second, _ = analyze([START, TARGET, POSE], spec=spec)
            self.assertFalse(second[-1]["metrics"][0]["over2"])
            self.assertEqual(second[-1]["mark"], "key")

    def test_mxio_fallback_requires_explicit_following_evidence(self):
        events, _ = analyze(
            ["connect mxio failed", "use custom module control robot teach", START]
        )
        self.assertEqual(events[0]["mark"], "key")
        self.assertIn("行 2", events[0]["notes"])
        self.assertIn("不代表", events[0]["notes"])
        for boundary in (
            START,
            LOAD,
            "start operation",
            "Oberon Application Exit",
            "connect mxio sucess",
            "connect mxio failed",
        ):
            with self.subTest(boundary=boundary):
                events, _ = analyze(
                    [
                        "connect mxio failed",
                        boundary,
                        "use custom module control robot teach",
                    ]
                )
                self.assertEqual(events[0]["mark"], "anomaly")
        events, _ = analyze(["connect mxio failed"])
        self.assertEqual(events[0]["mark"], "anomaly")
        events, _ = analyze(
            [
                "connect mxio failed",
                "read plan path /use custom module control robot teach/p from external sucess",
            ]
        )
        self.assertEqual(events[0]["mark"], "anomaly")

    def test_mxio_error_level_and_failed_fallback_remain_red(self):
        for levels in (["E", "I"], ["C", "I"], ["I", "E"]):
            events, _ = analyze(
                ["connect mxio failed", "use custom module control robot teach"], levels
            )
            self.assertEqual(events[0]["mark"], "anomaly")

    def test_manual_restart_first_disconnect_is_reminder_only(self):
        events, nle = analyze(
            [
                START,
                LOAD,
                "start operation",
                MANUAL,
                "rebooting sirius ...",
                "kuka app is disconnected",
                "kuka app is disconnected",
            ]
        )
        self.assertEqual(events[3]["event_id"], "sirius_manual_restart")
        self.assertEqual(events[5]["mark"], "key")
        self.assertIn("行 4", events[5]["notes"])
        self.assertEqual(events[6]["mark"], "anomaly")
        self.assertEqual(nle["ticks"]["anomaly"], [7])

    def test_automatic_restart_is_not_proof_disconnect_was_planned(self):
        events, _ = analyze(
            [
                START,
                LOAD,
                "start operation",
                "rebooting sirius ...",
                "kuka app is disconnected",
            ]
        )
        self.assertEqual(events[-1]["mark"], "anomaly")

    def test_restart_context_does_not_leak(self):
        for boundary in (
            LOAD,
            START,
            "kuka app is connected",
            "ndi states are fault",
            "kuka states are fault",
        ):
            tail = [boundary]
            if boundary in (START, LOAD):
                tail.append("start operation")
            events, _ = analyze(
                [START, LOAD, "start operation", MANUAL]
                + tail
                + ["kuka app is disconnected"]
            )
            self.assertEqual(events[-1]["mark"], "anomaly")

    def test_disconnect_and_emergency_without_start_stay_visible(self):
        events, _ = analyze(
            [
                START,
                "click start operation",
                "kuka app is disconnected",
                "robot emergency stop button external is pressed",
            ]
        )
        for ev in events[-2:]:
            self.assertEqual(ev["mark"], "key")
            self.assertIn(ev, filter_events(events))
        events, _ = analyze(
            [
                START,
                "start operation",
                "robot emergency stop button external is pressed",
            ]
        )
        self.assertEqual(events[-1]["mark"], "anomaly")

    def test_error_disconnect_and_emergency_stay_red_without_start(self):
        for message in (
            "kuka app is disconnected",
            "robot emergency stop button external is pressed",
        ):
            events, _ = analyze([message], ["E"])
            self.assertEqual(events[0]["mark"], "anomaly")

    def test_failure_words_in_successful_paths_are_not_faults(self):
        for name in (
            "failure backup",
            "CRASH DETECTED",
            "Caught signal 6",
            "marker data is invalid",
            "kuka app is disconnected",
            "connect mxio failed",
            "probe calibration error 3",
            "ras coordinate realtime",
            "app coordinate plan",
            "can't read config",
        ):
            events, nle = analyze(
                [START, f"read plan path /synthetic/{name}/plan from external sucess"]
            )
            self.assertEqual(summarize(events)["anomaly"], 0, name)
            self.assertEqual(nle["ticks"]["anomaly"], [], name)
        events, _ = analyze(["send kuka cmd: setTarget marker data is invalid"])
        self.assertEqual(events[0]["mark"], "key")

    def test_actual_failures_keep_identity_and_severity(self):
        for message, eid in (
            ("read plan path /synthetic/plan from external fail", "plan_read_failed"),
            ("can't read settings.ini", "config_failed"),
            ("marker data is invalid, pausing fix-line motion", "marker_invalid"),
            ("cart marker offset is too big, fix point motion stops", "marker_offset"),
            ("kuka and ndi states are fault", "devices_fault"),
            (
                "robot command response exception catched: Motion Failed.",
                "motion_failed",
            ),
            ("probe compensate reamer fail", "compensate_failed"),
        ):
            events, _ = analyze([message])
            self.assertEqual(
                (events[0]["event_id"], events[0]["mark"]), (eid, "anomaly")
            )

    def test_crash_filename_does_not_merge_with_empty_error_header(self):
        lines = [
            "[10:00:00 +0800] [Daily_logger] [---E---] [thread 1] ",
            "[10:00:01 +0800] [Daily_logger] [---I---] [thread 1] read plan path /CRASH DETECTED/p from external sucess",
        ]
        events = classify_events(parse_log_lines(lines, None), Spec())
        self.assertEqual(len(events), 2)
        self.assertEqual(summarize(events)["anomaly"], 1)
        self.assertNotEqual(events[1]["event_id"], "crash")

    def test_error_threshold_boundaries_and_invalid_values(self):
        for prefix, eid in (
            ("probe calibration error", "probe_error"),
            ("effector calibration error", "effector_error"),
            ("hip register calculate error", "hip_error"),
        ):
            for token, mark in (
                ("0", "key"),
                ("1", "key"),
                ("1.0001", "anomaly"),
                ("-0.1", "anomaly"),
                ("nan", "anomaly"),
                ("-nan", "anomaly"),
                ("inf", "anomaly"),
                ("-Infinity", "anomaly"),
                ("1e309", "anomaly"),
                ("bad0", "anomaly"),
            ):
                with self.subTest(prefix=prefix, token=token):
                    events, nle = analyze(
                        [START, LOAD, "start operation", f"{prefix} {token}"]
                    )
                    self.assertEqual(events[-1]["mark"], mark)
                    invalid = token in (
                        "-0.1",
                        "nan",
                        "-nan",
                        "inf",
                        "-Infinity",
                        "1e309",
                        "bad0",
                    )
                    self.assertEqual(
                        events[-1]["event_id"], eid + ("_invalid" if invalid else "")
                    )
                    json.dumps(nle, allow_nan=False)
                    if invalid and eid == "probe_error":
                        self.assertFalse(
                            next(
                                s
                                for s in nle["summaries"][0]["steps"]
                                if s["id"] == "probe_cal"
                            )["ok"]
                        )

    def test_invalid_coordinate_does_not_make_json_nonfinite(self):
        for coordinate in ("ras", "app"):
            for token in ("nan", "inf", "-inf", "1e309", "invalid"):
                for field in ("anteversion", "inclination", "depth"):
                    values = {"anteversion": "20", "inclination": "40", "depth": "1"}
                    values[field] = token
                    msg = f"{coordinate} coordinate realtime anteversion:{values['anteversion']} , inclination:{values['inclination']}, depth:{values['depth']}"
                    events, nle = analyze([START, msg])
                    self.assertEqual(
                        events[-1]["event_id"], f"measured_{coordinate}_invalid"
                    )
                    self.assertEqual(nle["ticks"]["anomaly"], [2])
                    json.dumps(nle, allow_nan=False)

    def test_invalid_target_discards_previous_target_on_reanalysis(self):
        events, _ = analyze(
            [
                START,
                TARGET,
                "ras coordinate plan anteversion:nan , inclination:40",
                POSE,
            ]
        )
        collect_cut_deltas(events)
        self.assertEqual(events[-2]["event_id"], "target_ras_invalid")
        self.assertIsNone(events[-1]["metrics"][0]["delta"])

    def test_invalid_legacy_target_is_not_plan_completion(self):
        for token in ("nan", "1e309", "invalid"):
            events, nle = analyze(
                [
                    START,
                    LOAD,
                    "start operation",
                    f"planviewer hand over,plan inclination: {token}, plan anterversion: 20",
                    POSE,
                ]
            )
            self.assertEqual(events[-2]["event_id"], "plan_legacy_invalid")
            self.assertEqual(events[-2]["mark"], "anomaly")
            collect_cut_deltas(events)
            self.assertIsNone(events[-1]["metrics"][0]["plan"])
            self.assertFalse(
                next(
                    s for s in nle["summaries"][0]["steps"] if s["id"] == "plan_target"
                )["ok"]
            )
            json.dumps(nle, allow_nan=False)

    def test_overflowing_difference_is_invalid(self):
        events, nle = analyze(
            [
                START,
                "ras coordinate plan anteversion:1e308 , inclination:40",
                "ras coordinate realtime anteversion:-1e308 , inclination:40, depth:1",
            ]
        )
        self.assertEqual(events[-1]["event_id"], "measured_ras_invalid")
        json.dumps(nle, allow_nan=False)

    def test_invalid_latest_error_does_not_show_old_current_result(self):
        events, nle = analyze(
            [
                START,
                LOAD,
                "start operation",
                "enter device prepare page",
                "probe calibration error 0.2",
                "probe calibration error nan",
            ]
        )
        sp = next(s for s in nle["tracks"]["l1"] if s["event_id"] == "page_prepare")
        self.assertFalse(sp.get("errors"))
        self.assertIn("无效", sp["result_state"])
        self.assertTrue(
            next(s for s in nle["summaries"][0]["steps"] if s["id"] == "probe_cal")[
                "ok"
            ]
        )

    def test_invalid_latest_pose_does_not_show_old_current_snapshot(self):
        events, nle = analyze(
            [
                START,
                TARGET,
                "switch polish hip step",
                POSE,
                "ras coordinate realtime anteversion:nan , inclination:45, depth:1",
            ]
        )
        sp = next(s for s in nle["tracks"]["l2"] if s["event_id"] == "hip_polish")
        self.assertTrue(all(m.get("missing") for m in sp["cut_deltas"]))
        self.assertIn("无效", sp["result_state"])


if __name__ == "__main__":
    unittest.main()
