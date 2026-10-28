"""Source-backed recognition without turning arbitrary text into evidence."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from parser import parse_log_lines, classify_events, filter_events, summarize
from spec import Spec
from nle import build_nle

START = "Oberon Application Startup version 2.9.0"
LOAD = "start load plan uuid: 11111111-1111-1111-1111-111111111111"


def line(message, level="I"):
    return f"[10:00:00 +08:00] [Daily_logger] [---{level}---] [thread 1] {message}"


class UnmappedReviewTests(unittest.TestCase):
    def setUp(self):
        self.spec = Spec()

    def test_module_query_and_version_are_specific_visible_events(self):
        for message, identity, mark in (
            (
                "custom module version query attempt: 3",
                "teach_module_version_query",
                "none",
            ),
            ("custom module version: V1.2.1", "teach_module_version", "key"),
        ):
            out = self.spec.classify(message, "", "I")
            self.assertEqual(
                (out["event_id"], out["timeline"], out["mark"]),
                (identity, "show", mark),
            )
            self.assertEqual(out["track"], "device")
            self.assertIsNone(out.get("threshold"))
        self.assertNotEqual(
            self.spec.classify("custom module version query attempt: 99", "", "I")[
                "mark"
            ],
            "anomaly",
        )

    def test_protection_warnings_have_device_causes_even_at_info_level(self):
        warnings = {
            "teach module reported that teach mode is closed; teach stop command sent": "teach_module_unexpected_close",
            "teach module connection lost; teach stop command sent": "teach_module_lost_stop",
            "custom module teach mode is open after heartbeat recovery; sending close command": "teach_module_recovery_close",
        }
        for message, identity in warnings.items():
            for level in ("I", "W", "E", "C"):
                with self.subTest(message=message, level=level):
                    ls = [line(message, level)]
                    events = classify_events(parse_log_lines(ls, None), self.spec)
                    n = build_nle(events, ls)
                    e = events[0]
                    self.assertEqual(
                        (e["event_id"], e["mark"], e["timeline"]),
                        (identity, "anomaly", "show"),
                    )
                    self.assertEqual(len(filter_events(events)), 1)
                    self.assertEqual(len(n["tracks"]["device"]), 1)
                    self.assertEqual(summarize(events)["anomaly"], 1)
                    self.assertNotIn("成功", e["step"])
                    self.assertNotEqual(e["event_id"], "robot_stopped")

    def test_context_record_does_not_prove_registration_or_calibration(self):
        messages = [
            START,
            LOAD,
            "start operation",
            "prepar step register terminal tool, send robot cmd: Register",
        ]
        ls = list(map(line, messages))
        es = classify_events(parse_log_lines(ls, None), self.spec)
        n = build_nle(es, ls)
        self.assertEqual(es[-1]["event_id"], "prepare_command_context")
        self.assertEqual(es[-1]["timeline"], "show")
        self.assertEqual(n["tracks"]["l1"], [])
        steps = {s["id"]: s["ok"] for s in n["summaries"][0]["steps"]}
        self.assertFalse(steps["device_prepare"])
        self.assertFalse(steps["probe_cal"])
        self.assertFalse(steps["hip_register"])
        # Preserve the emitted source typo and a repeated formatter argument without inventing a command.
        out = self.spec.classify(
            "prepar step register robot, send robot cmd: register robot", "", "I"
        )
        self.assertEqual(out["event_id"], "prepare_command_context")

    def test_module_version_does_not_restart_software_or_override_software_version(
        self,
    ):
        messages = [
            START,
            LOAD,
            "custom module version: V9.8.7",
            "custom module version query attempt: 1",
            "robot is not teaching state and manual close mask",
        ]
        ls = list(map(line, messages))
        es = classify_events(parse_log_lines(ls, None), self.spec)
        n = build_nle(es, ls)
        self.assertEqual(len({e["session_id"] for e in es}), 1)
        self.assertEqual(len(n["tracks"]["markers"]), 1)
        self.assertTrue(all(s["version"] == "2.9.0" for s in n["tracks"]["sessions"]))
        self.assertEqual(len(n["summaries"]), 1)
        self.assertFalse(n["summaries"][0]["started"])
        self.assertEqual(es[-1]["event_id"], "teach_mask_closed")
        self.assertNotEqual(es[-1]["event_id"], "robot_stopped")

    def test_femur_raw_pose_is_noise_but_sample_action_and_warning_are_visible(self):
        msg = "femurmarker2ndi NDIDATA:1,2,3,4,5,6,7"
        es = classify_events(
            parse_log_lines(
                [
                    line(msg),
                    line("probe2femurmarker sparse point:x:1, y:2, z:3"),
                    line(msg, "W"),
                ],
                None,
            ),
            self.spec,
        )
        self.assertEqual(
            (es[0]["event_id"], es[0]["category"], es[0]["timeline"]),
            ("femur_ndi_pose", "noise", "hide"),
        )
        self.assertEqual(es[1]["event_id"], "sparse_sample")
        self.assertEqual(es[1]["track"], "l3")
        self.assertEqual((es[2]["mark"], es[2]["timeline"]), ("key", "show"))
        self.assertEqual([e["line"] for e in filter_events(es)], [3])
        self.assertEqual(len(filter_events(es, show_all=True)), 3)

    def test_unrelated_or_stdout_only_messages_remain_unmapped(self):
        messages = [
            "custom module temperature sample: 23",
            "custom module connection recovery verified by teach status response",
            "local host listen custom robot teach module fail",
            "preparation completed",
            "ordinary new product event 42",
        ]
        for msg in messages:
            with self.subTest(message=msg):
                out = self.spec.classify(msg, "", "I")
                self.assertEqual(out["source"], "unmatched")
                self.assertEqual(out["event_id"], "")
        es = classify_events(
            parse_log_lines(
                [
                    line("ordinary new product event 42"),
                    "unrecognized raw diagnostic block",
                ],
                None,
            ),
            self.spec,
        )
        self.assertEqual(summarize(es)["unmatched"], 2)
        self.assertEqual(filter_events(es), [])
        self.assertEqual(len(filter_events(es, show_all=True)), 2)
        self.assertEqual(es[1]["raw"], "unrecognized raw diagnostic block")

    def test_unknown_warnings_are_visible_without_fake_domain_identity(self):
        e = classify_events(
            parse_log_lines([line("custom module new warning detail", "W")], None),
            self.spec,
        )[0]
        self.assertEqual(
            (e["source"], e["mark"], e["timeline"]), ("level", "key", "show")
        )
        self.assertEqual(e["event_id"], "")
        self.assertEqual(len(filter_events([e])), 1)

    def test_source_backed_rules_hot_reload(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spec.md"
            text = self.spec.path.read_text()
            path.write_text(text)
            spec = Spec(path)
            path.write_text(
                text.replace("自定义示教模块版本查询尝试", "模块版本查询记录")
            )
            spec.reload(force=True)
            out = spec.classify("custom module version query attempt: 2", "", "I")
            self.assertEqual(out["step"], "模块版本查询记录")
            self.assertEqual(out["event_id"], "teach_module_version_query")


if __name__ == "__main__":
    unittest.main()
