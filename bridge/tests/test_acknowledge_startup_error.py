from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from work import acknowledge_startup_error as subject


def _dialog_windows(*, title: str = subject.ERROR_DIALOG_TITLE,
                    button_text: str = subject.ERROR_BUTTON_TEXT,
                    button_id: int = subject.ERROR_BUTTON_ID,
                    pid: int = 21652) -> list[subject.WindowInfo]:
    return [
        subject.WindowInfo(100, 0, pid, subject.ERROR_DIALOG_CLASS, title),
        subject.WindowInfo(101, 100, pid, "Static", subject.ERROR_STATIC_TEXT),
        subject.WindowInfo(102, 100, pid, "Button", button_text, button_id),
    ]


class AcknowledgeStartupErrorTests(unittest.TestCase):
    def test_exact_dialog_posts_parent_command_and_records_evidence_once(self):
        calls: list[tuple[int, int, int, int]] = []
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)

            def post(parent: int, message: int, wparam: int, button: int) -> bool:
                calls.append((parent, message, wparam, button))
                return True

            first = subject.acknowledge_collected_windows(
                21652, _dialog_windows(), directory, post)
            second = subject.acknowledge_collected_windows(
                21652, _dialog_windows(), directory, post)

            self.assertTrue(first["acknowledged"])
            self.assertEqual(first, second)
            self.assertEqual(calls, [(100, subject.WM_COMMAND, 2, 102)])
            evidence = json.loads((directory / "startup-error-ack.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["dialog"]["title"], subject.ERROR_DIALOG_TITLE)
            self.assertEqual(evidence["button"]["control_id"], 2)

    def test_wrong_button_does_not_post_or_record(self):
        calls: list[tuple[int, int, int, int]] = []
        with tempfile.TemporaryDirectory() as temporary:
            result = subject.acknowledge_collected_windows(
                21652,
                _dialog_windows(button_text="确定", button_id=3),
                Path(temporary),
                lambda *args: calls.append(args) or True,
            )
            self.assertIsNone(result)
            self.assertEqual(calls, [])
            self.assertFalse((Path(temporary) / "startup-error-ack.json").exists())

    def test_other_title_does_not_post_or_record(self):
        calls: list[tuple[int, int, int, int]] = []
        with tempfile.TemporaryDirectory() as temporary:
            result = subject.acknowledge_collected_windows(
                21652,
                _dialog_windows(title="DLL autoupdate succeeded"),
                Path(temporary),
                lambda *args: calls.append(args) or True,
            )
            self.assertIsNone(result)
            self.assertEqual(calls, [])
            self.assertFalse((Path(temporary) / "startup-error-ack.json").exists())

    def test_other_pid_does_not_post(self):
        calls: list[tuple[int, int, int, int]] = []
        with tempfile.TemporaryDirectory() as temporary:
            result = subject.acknowledge_collected_windows(
                21652,
                _dialog_windows(pid=21653),
                Path(temporary),
                lambda *args: calls.append(args) or True,
            )
            self.assertIsNone(result)
            self.assertEqual(calls, [])

    def test_posted_message_does_not_acknowledge_a_hung_dialog(self):
        calls: list[tuple[int, int, int, int]] = []
        with tempfile.TemporaryDirectory() as temporary:
            result = subject.acknowledge_collected_windows(
                21652, _dialog_windows(), Path(temporary),
                lambda *args: calls.append(args) or True,
                probe_dialog=lambda _pid, _hwnd: "hung",
                settle_seconds=2.0,
            )
            self.assertEqual(len(calls), 1)
            self.assertIsNotNone(result)
            self.assertFalse(result["acknowledged"])
            self.assertTrue(result["attempted"])
            self.assertTrue(result["terminal"])
            self.assertEqual(result["reason"], "STARTUP_ERROR_DIALOG_HUNG_NO_RETRY")
            saved = json.loads((Path(temporary) / "startup-error-ack.json").read_text(
                encoding="utf-8"))
            self.assertFalse(saved["acknowledged"])

    def test_responsive_dialog_is_waited_once_until_it_disappears(self):
        states = iter(("responsive", "responsive", "gone"))
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as temporary:
            result = subject.acknowledge_collected_windows(
                21652, _dialog_windows(), Path(temporary),
                lambda *_args: True,
                probe_dialog=lambda _pid, _hwnd: next(states),
                sleep=lambda seconds: sleeps.append(seconds),
                settle_seconds=2.0,
            )
            self.assertTrue(result["acknowledged"])
            self.assertFalse(result["terminal"])
            self.assertEqual(result["probe_history"], ["responsive", "responsive", "gone"])
            self.assertEqual(len(sleeps), 2)


if __name__ == "__main__":
    unittest.main()
