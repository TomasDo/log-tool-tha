"""Settings and switch actions stay visible without losing business identity."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from parser import classify_events, filter_events, parse_log_lines, summarize
from nle import build_nle
from spec import Spec


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.spec = Spec()

    def test_real_setting_and_switch_messages_default_visible(self):
        messages = [
            "set tool type: 2",
            "set tool type 2",
            "set tool side 1",
            "set effector side: 1",
            "set tool type new metal tool",
            "set tool side left",
            "set reamer rod: right rod",
            "set cup rod: long rod",
            "switch app coordinate",
            "switch ras coordinate",
            "switch drill rod 1",
            "switch install rod 2",
            "send teach cmd and try to open hard switch",
            "RobotTeachState::IN_TEACHING send stop cmd and try to close hard switch",
            "RobotTeachState::WAIT_OPEN_HARD_SWITCH send stop cmd and try to close hard switch",
            "RobotTeachState::WAIT_CLOSE_HARD_SWITCH send stop cmd and try to close hard switch",
            "reading handguding button is pressed so hard switch has open sucess",
            "reading handguding button is released so hard switch has close sucess",
            "send open soft switch cmd to robot app",
            "reading hard switch is closed",
            "soft switch state changed",
        ]
        for msg in messages:
            with self.subTest(message=msg):
                out = self.spec.classify(msg, "", "I")
                self.assertNotEqual(out["source"], "noise")
                self.assertEqual(out["timeline"], "show")
                self.assertEqual(out["mark"], "key")
                self.assertEqual(out["track"], "device")

    def test_page_and_step_mappings_are_preserved(self):
        for msg, event, track in [
            ("switch planviewer page", "page_plan", "l1"),
            ("switch register hip step", "hip_register", "l2"),
            ("switch polish hip step", "hip_polish", "l2"),
            ("switch cup type: 50/42", "cup_type", ""),
            ("set cup rod: long rod", "tool", "device"),
        ]:
            with self.subTest(message=msg):
                out = self.spec.classify(msg, "", "I")
                self.assertEqual(out["event_id"], event)
                self.assertEqual(out["track"], track)

    def test_transport_noise_cannot_swallow_setting_commands(self):
        for msg in [
            "send kuka cmd: setTarget 1 2 3",
            "send kuka cmd: switchMode 2",
            "handle kuka instruct setWorkingFrame 0 0 0",
            "handle kuka instruct: switchMode 1",
            "setCustomOption 2",
            "switch custom mode",
        ]:
            with self.subTest(message=msg):
                out = self.spec.classify(msg, "", "I")
                self.assertEqual(out["timeline"], "show")
                self.assertEqual(out["mark"], "key")
                self.assertNotEqual(out["source"], "noise")

    def test_failure_and_error_levels_keep_priority(self):
        msg = "marker data is invalid, pausing fix-line motion"
        self.assertEqual(self.spec.classify(msg, "", "I")["mark"], "anomaly")
        for level in ("E", "C"):
            out = self.spec.classify("switch app coordinate", "", level)
            self.assertEqual(out["mark"], "anomaly")
            self.assertEqual(out["event_id"], "coordinate_app")

    def test_request_and_feedback_are_distinct(self):
        request = self.spec.classify(
            "send teach cmd and try to open hard switch", "", "I"
        )
        feedback = self.spec.classify(
            "reading handguding button is pressed so hard switch has open sucess",
            "",
            "I",
        )
        self.assertEqual(request["event_id"], "hard_switch_open_request")
        self.assertEqual(feedback["event_id"], "hard_switch_opened")

    def test_continuous_dumps_remain_noise_and_no_substring_false_hits(self):
        for msg in (
            "current torque, t1:1",
            "record torque, t1:1",
            "current joint, a1:0",
        ):
            with self.subTest(message=msg):
                self.assertEqual(self.spec.classify(msg, "", "I")["source"], "noise")
        for msg in (
            "offset 2",
            "setup completed",
            "setting file loaded",
            "switches listed",
            "send kuka cmd: setup completed",
        ):
            with self.subTest(message=msg):
                self.assertNotIn(
                    self.spec.classify(msg, "", "I")["event_id"],
                    {
                        "setting_change",
                        "switch_change",
                        "setting_command",
                        "switch_command",
                    },
                )

    def test_default_filter_terminal_and_tracks_agree(self):
        lines = [
            f"[10:00:00 +08:00] [Daily_logger] [---I---] [thread 1] {msg}"
            for msg in (
                "Oberon Application Startup version 2.9",
                "set tool type: 2",
                "switch app coordinate",
                "send open soft switch cmd to robot app",
                "reading hard switch is closed",
                "soft switch state changed",
                "current torque, t1:0",
            )
        ]
        events = classify_events(parse_log_lines(lines, None), self.spec)
        nle = build_nle(events, lines)
        self.assertEqual([e["line"] for e in filter_events(events)], [1, 2, 3, 4, 5, 6])
        self.assertTrue(
            all(
                row["timeline"] == "show" and not row["noise"]
                for row in nle["lines"][1:6]
            )
        )
        self.assertEqual(
            [span["start"] for span in nle["tracks"]["device"]], [2, 3, 4, 5, 6]
        )
        self.assertEqual(summarize(events)["noise"], 1)

    def test_operation_rules_hot_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spec.md"
            path.write_text(self.spec.path.read_text())
            spec = Spec(path)
            path.write_text(
                path.read_text().replace("切换 APP 坐标系", "更换 APP 参考系")
            )
            spec.reload(force=True)
            out = spec.classify("switch app coordinate", "", "I")
            self.assertEqual(out["step"], "更换 APP 参考系")
            self.assertEqual(out["event_id"], "coordinate_app")
            self.assertEqual(out["timeline"], "show")


if __name__ == "__main__":
    unittest.main()
