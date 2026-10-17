from unittest.mock import Mock, patch

from work.advance_diplomacy_context import _completion_health


def test_completion_accepts_a_delayed_heartbeat_without_another_control_request():
    stale = {"status": "ready", "date_raw": 100}
    current = {"status": "ready", "date_raw": 124}
    session = Mock(spec=["health"])
    session.health.return_value = current
    with patch("work.advance_diplomacy_context.wait_runtime_ready", return_value=stale), \
            patch("work.advance_diplomacy_context.time.sleep"), \
            patch("work.advance_diplomacy_context.time.monotonic", return_value=0):
        assert _completion_health(session, 124) == current
    session.health.assert_called_once_with()


def test_completion_does_not_accept_a_ready_heartbeat_from_the_wrong_date():
    stale = {"status": "ready", "date_raw": 100}
    session = Mock(spec=["health"])
    with patch("work.advance_diplomacy_context.wait_runtime_ready", return_value=stale), \
            patch("work.advance_diplomacy_context.time.monotonic", side_effect=[0, 4]):
        result = _completion_health(session, 124)
    assert result["date_raw"] != 124
    session.health.assert_not_called()
