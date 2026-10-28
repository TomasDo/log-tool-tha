"""Aftersales evidence must not be hidden by transfer/dump noise rules."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from parser import classify_events, filter_events, parse_log_lines, summarize
from nle import build_nle
from spec import Spec


def line(message, level="I"):
    return f"[10:00:00 +08:00] [Daily_logger] [---{level}---] [thread 1] {message}"


class NoiseReviewTests(unittest.TestCase):
    def setUp(self):
        self.spec = Spec()

    def test_observed_commands_have_specific_visible_request_types(self):
        expected = {
            "compensateGravity_0": ("gravity_request", "key"),
            "compensateGravity_4": ("gravity_request", "key"),
            "fixLine": ("fix_line_request", "key"),
            "fixPoint": ("fix_point_request", "key"),
            "moveToolHandGuiding 0 0 0 0 0 1 0": ("tool_hand_guiding_request", "key"),
            "moveKukaToPatientDirection": ("align_direction_request", "key"),
            "moveKukaToPatientPosition": ("move_patient_request", "key"),
            "moveToRecord": ("move_preset_request", "key"),
            "moveToStorage": ("move_storage_request", "key"),
            "teachStop": ("teach_stop_request", "key"),
            "specialTeachStop": ("special_teach_stop_request", "key"),
            "braketest": ("brake_test_request", "key"),
            "braketestCurrent": ("brake_current_request", "key"),
            "standbyMarkerOffsetted": ("marker_standby_request", "anomaly"),
            "standbyStepChange": ("step_standby_request", "none"),
            "standby": ("standby_request", "key"),
            "stopMotion": ("stop_motion_request", "key"),
            "stop": ("stop_request", "key"),
            "Register": ("device_register_request", "key"),
        }
        for command, (identity, mark) in expected.items():
            for prefix in ("send kuka cmd: ", "handle kuka instruct "):
                with self.subTest(command=prefix + command):
                    out = self.spec.classify(prefix + command, "", "I")
                    self.assertEqual(
                        (out["event_id"], out["timeline"], out["mark"]),
                        (identity, "show", mark),
                    )
                    self.assertEqual(out["track"], "device")
                    self.assertNotEqual(out["category"], "noise")
                    self.assertIn("请求", out["step"])

    def test_unknown_commands_are_visible_but_not_success(self):
        for message in (
            "send kuka cmd: futureMotion 1",
            "handle kuka instruct futureCalibration 2",
        ):
            out = self.spec.classify(message, "", "I")
            self.assertEqual(out["timeline"], "show")
            self.assertIn(
                out["event_id"], ("robot_command_request", "robot_command_handle")
            )
            self.assertNotIn("成功", out["step"])
            self.assertEqual(out["mark"], "key")

    def test_pedal_ui_feedback_is_distinct_from_physical_signal(self):
        for message, event in (
            ("pedal-pressed UI is displayed", "pedal_ui_pressed"),
            ("pedal-released UI is displayed", "pedal_ui_released"),
        ):
            out = self.spec.classify(message, "", "I")
            self.assertEqual(out["event_id"], event)
            self.assertEqual(out["timeline"], "show")
            self.assertIn("界面反馈", out["step"])
        physical = self.spec.classify("physical q-key/pedal is pressed", "", "I")
        self.assertEqual(physical["event_id"], "pedal_pressed")

    def test_robot_stop_feedback_is_visible_but_not_a_fault(self):
        out = self.spec.classify("robot no motion joint, a1:0 a2:1", "", "I")
        self.assertEqual(
            (out["event_id"], out["timeline"], out["mark"]),
            ("robot_stopped", "show", "key"),
        )
        self.assertIn("停止状态反馈", out["step"])
        self.assertNotIn("请求", out["step"])

    def test_page_standby_is_visible_normal_reason(self):
        for message in (
            "send kuka cmd: standbyStepChange",
            "standby cmd called by step change",
        ):
            out = self.spec.classify(message, "", "I")
            self.assertEqual((out["timeline"], out["mark"]), ("show", "none"))
            self.assertIn("切页", out["step"])

    def test_matrix_records_are_not_error_readings_or_completion_evidence(self):
        matrices = [
            "calibration reamer2effector matrix 1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1",
            "hipmarker2ct: 1,0,0,2,0,1,0,0,0,0,1,0,0,0,0,1",
            "femurmarker2ct: 1,0,0,2,0,1,0,0,0,0,1,0,0,0,0,1",
        ]
        for message in matrices:
            out = self.spec.classify(message, "", "I")
            self.assertEqual((out["timeline"], out["mark"]), ("show", "key"))
            self.assertIsNone(out.get("value_mm"))
            self.assertNotIn(
                out["event_id"], ("hip_error", "probe_error", "effector_error")
            )
        messages = [
            "Oberon Application Startup version 2.9",
            "start load plan uuid: 11111111-1111-1111-1111-111111111111",
            "start operation",
            "switch register hip step",
        ] + matrices
        ls = list(map(line, messages))
        events = classify_events(parse_log_lines(ls, None), self.spec)
        n = build_nle(events, ls)
        self.assertFalse(
            next(s for s in n["summaries"][0]["steps"] if s["id"] == "hip_register")[
                "ok"
            ]
        )
        self.assertEqual(summarize(events)["anomaly"], 0)

    def test_environment_and_config_are_ordinary_visible_evidence(self):
        for message, event in (
            ("detect net ip 127.0.0.1", "network_address"),
            ("QCoreApplication applicationDirPath /opt/Oberon/bin", "application_path"),
            (" read Example_Cup_50 offset 0.7", "config_echo"),
        ):
            out = self.spec.classify(message, "", "I")
            self.assertEqual(
                (out["event_id"], out["timeline"], out["mark"]), (event, "show", "none")
            )
        self.assertEqual(
            self.spec.classify("can't read hip cup offset config txt", "", "I")["mark"],
            "anomaly",
        )

    def test_warning_dump_is_not_hidden_and_errors_keep_priority(self):
        for message in (
            "current torque, t1:1",
            "record torque, t1:2",
            "current joint, a1:0",
            "hipmarker2ndi NDIDATA:1,2,3,4,5,6,7",
            "ras coordinate realtime anteversion:0 , inclination:0, depth:0",
            "app coordinate realtime anteversion:0.00 , inclination:0, depth:0",
        ):
            for level, mark in (("W", "key"), ("E", "anomaly"), ("C", "anomaly")):
                with self.subTest(message=message, level=level):
                    ls = [line(message, level)]
                    events = classify_events(parse_log_lines(ls, None), self.spec)
                    n = build_nle(events, ls)
                    self.assertEqual(
                        (events[0]["mark"], events[0]["timeline"]), (mark, "show")
                    )
                    self.assertEqual(len(filter_events(events)), 1)
                    self.assertEqual(n["lines"][0]["mark"], mark)
                    self.assertFalse(events[0].get("metrics"))

    def test_regular_continuous_dumps_and_zero_placeholders_stay_hidden(self):
        for message in (
            "current torque, t1:1",
            "record torque, t1:2",
            "current joint, a1:0",
            "hipmarker2ndi NDIDATA:1,2,3,4,5,6,7",
            "app coordinate realtime anteversion:0 , inclination:0, depth:0",
        ):
            ls = [line(message)]
            events = classify_events(parse_log_lines(ls, None), self.spec)
            n = build_nle(events, ls)
            self.assertEqual(
                (events[0]["category"], events[0]["timeline"]), ("noise", "hide")
            )
            self.assertEqual(filter_events(events), [])
            self.assertFalse(events[0].get("metrics"))

    def test_failure_semantics_precede_generic_requests(self):
        for message in (
            "marker data is invalid, pausing fix-line motion",
            "robot command response exception catched: Motion Failed.",
        ):
            self.assertEqual(self.spec.classify(message, "", "I")["mark"], "anomaly")
        self.assertEqual(
            self.spec.classify("send kuka cmd: moveToStorage", "", "E")["mark"],
            "anomaly",
        )

    def test_names_and_visibility_hot_reload(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spec.md"
            text = self.spec.path.read_text()
            path.write_text(text)
            spec = Spec(path)
            path.write_text(text.replace("移动到预设位请求", "预设位置移动指令"))
            spec.reload(force=True)
            out = spec.classify("send kuka cmd: moveToRecord", "", "I")
            self.assertEqual(out["step"], "预设位置移动指令")
            self.assertEqual(out["event_id"], "move_preset_request")


if __name__ == "__main__":
    unittest.main()
