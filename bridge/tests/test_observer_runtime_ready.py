from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from work.observer_runtime_ready import wait_runtime_ready


class FakeSession:
    def __init__(self, root: Path, *, final_status: str = "ready"):
        self.directory = root
        self.session_id = "runtime-ready-session"
        self.record = {"pid": 463486}
        self.game_exe = root / "eu4.exe"
        self.final_status = final_status
        self.health_calls = 0
        self.initial_health = {
            "status": "unready", "state_id": None, "date_raw": None,
            "reasons": [{"code": "SESSION_UNREADY"}], "complete": False,
        }

    def health(self) -> dict:
        self.health_calls += 1
        if self.health_calls >= 2:
            return {"status": self.final_status, "state_id": "verified",
                    "date_raw": 42, "reasons": [],
                    "complete": self.final_status == "ready"}
        return self.initial_health


def heartbeat(session_id: str, *, frames: int = 2, player: str = "POR",
              date_raw: int = 42, thread: int | None = 7,
              state_readable: bool = True, thread_changed: bool = False) -> dict:
    return {
        "event": "diplomacy_observer_health", "session_id": session_id,
        "state_readable": state_readable, "thread_changed": thread_changed,
        "frames": frames, "player": player, "date_raw": date_raw,
        **({"thread": thread} if thread is not None else {}),
    }


class ObserverRuntimeReadyTests(unittest.TestCase):
    def test_delayed_matching_heartbeat_triggers_one_final_health_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "control-probe.jsonl"
            log.write_text("{malformed\n", encoding="utf-8")
            session = FakeSession(root)

            def publish_heartbeat() -> None:
                time.sleep(0.06)
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(heartbeat(session.session_id, frames=2)) + "\n")
                    stream.write(json.dumps(heartbeat(session.session_id, frames=3)) + "\n")

            writer = threading.Thread(target=publish_heartbeat)
            writer.start()
            result = wait_runtime_ready(session, timeout=0.8)
            writer.join(timeout=1.0)

            self.assertEqual("ready", result["status"])
            self.assertEqual(2, session.health_calls)

    def test_wrong_session_and_single_heartbeat_do_not_trigger_final_health(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "control-probe.jsonl"
            log.write_text(
                "not-json\n"
                + json.dumps(heartbeat("other-session")) + "\n"
                + json.dumps(heartbeat("runtime-ready-session", frames=2)) + "\n",
                encoding="utf-8",
            )
            session = FakeSession(root)
            result = wait_runtime_ready(session, timeout=0.08)

            self.assertEqual(session.initial_health, result)
            self.assertEqual("unready", result["status"])
            self.assertEqual(1, session.health_calls)

    def test_date_change_needs_two_new_heartbeats(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "control-probe.jsonl"
            log.write_text(
                "\n".join(json.dumps(event) for event in (
                    heartbeat("runtime-ready-session", frames=100, date_raw=41),
                    heartbeat("runtime-ready-session", frames=101, date_raw=42),
                )) + "\n",
                encoding="utf-8",
            )
            session = FakeSession(root)

            result = wait_runtime_ready(session, timeout=0.05)

            self.assertEqual(session.initial_health, result)
            self.assertEqual(1, session.health_calls)

    def test_two_new_heartbeats_ready_below_legacy_frame_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "control-probe.jsonl"
            log.write_text(
                "\n".join(json.dumps(event) for event in (
                    heartbeat("runtime-ready-session", frames=2),
                    heartbeat("runtime-ready-session", frames=3),
                )) + "\n",
                encoding="utf-8",
            )
            session = FakeSession(root)

            result = wait_runtime_ready(session, timeout=0.05)

            self.assertEqual("ready", result["status"])
            self.assertEqual(2, session.health_calls)

    def test_thread_change_and_unready_heartbeat_do_not_form_pair(self) -> None:
        scenarios = {
            "thread-change": (
                heartbeat("runtime-ready-session", frames=2, thread=7),
                heartbeat("runtime-ready-session", frames=3, thread=8),
            ),
            "thread-changed": (
                heartbeat("runtime-ready-session", frames=2),
                heartbeat("runtime-ready-session", frames=3, thread_changed=True),
            ),
            "unreadable": (
                heartbeat("runtime-ready-session", frames=2, state_readable=False),
                heartbeat("runtime-ready-session", frames=3, state_readable=False),
            ),
        }
        for name, events in scenarios.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                log = root / "control-probe.jsonl"
                log.write_text("\n".join(json.dumps(event) for event in events) + "\n",
                               encoding="utf-8")
                session = FakeSession(root)

                result = wait_runtime_ready(session, timeout=0.05)

                self.assertEqual(session.initial_health, result)
                self.assertEqual(1, session.health_calls)

    def test_stale_matching_heartbeat_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "control-probe.jsonl"
            log.write_text("\n".join(json.dumps(event) for event in (
                heartbeat("runtime-ready-session", frames=2),
                heartbeat("runtime-ready-session", frames=3),
            )) + "\n", encoding="utf-8")
            stale = time.time() - 6.0
            os.utime(log, (stale, stale))
            session = FakeSession(root)

            result = wait_runtime_ready(session, timeout=0.05)

            self.assertEqual(session.initial_health, result)
            self.assertEqual(1, session.health_calls)

    def test_already_ready_session_uses_fast_path_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = FakeSession(Path(temporary))
            session.final_status = "ready"
            session.health = lambda: {"status": "ready", "state_id": "already"}

            result = wait_runtime_ready(session, timeout=0.2)

            self.assertEqual("ready", result["status"])

    def test_non_minimized_window_is_not_touched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = FakeSession(root)
            with patch("work.observer_runtime_ready.probe_identity",
                       return_value={"session_id": session.session_id}) as identity, \
                    patch("work.observer_runtime_ready._enumerate_windows_for_pid",
                          return_value=[463486]) as enumerate_windows, \
                    patch("work.observer_runtime_ready._is_iconic", return_value=False), \
                    patch("work.observer_runtime_ready._show_window_async") as show_window:
                wait_runtime_ready(session, timeout=0.0, restore_minimized=True)

            identity.assert_called_once_with(463486, session.game_exe)
            enumerate_windows.assert_called_once_with(463486, "Europa Universalis IV")
            show_window.assert_not_called()

    def test_identity_session_mismatch_does_not_enumerate_or_touch_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = FakeSession(root)
            with patch("work.observer_runtime_ready.probe_identity",
                       return_value={"session_id": "other-session"}), \
                    patch("work.observer_runtime_ready._enumerate_windows_for_pid") as enumerate_windows, \
                    patch("work.observer_runtime_ready._show_window_async") as show_window:
                wait_runtime_ready(session, timeout=0.0, restore_minimized=True)

            enumerate_windows.assert_not_called()
            show_window.assert_not_called()

    def test_unique_minimized_window_uses_shownoactivate_once_and_records_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = FakeSession(root)
            with patch("work.observer_runtime_ready.probe_identity",
                       return_value={"session_id": session.session_id}), \
                    patch("work.observer_runtime_ready._enumerate_windows_for_pid",
                          return_value=[463486]), \
                    patch("work.observer_runtime_ready._is_iconic", return_value=True), \
                    patch("work.observer_runtime_ready._show_window_async",
                          return_value=True) as show_window:
                wait_runtime_ready(session, timeout=0.0, restore_minimized=True)

            show_window.assert_called_once_with(463486, 4)
            evidence = list(root.glob("runtime-window-restore-*.json"))
            self.assertEqual(1, len(evidence))
            recorded = json.loads(evidence[0].read_text(encoding="utf-8"))
            self.assertEqual(463486, recorded["hwnd"])
            self.assertEqual(4, recorded["show_command"])
            self.assertEqual(1, recorded["show_window_async_called"])
            self.assertFalse(recorded["foreground_activation"])


if __name__ == "__main__":
    unittest.main()
