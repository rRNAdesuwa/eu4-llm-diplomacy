"""Regressions from native Start/Stop evidence, including diplomat return."""
import json
from pathlib import Path

import pytest

from work.run_improve_relations_execution import (
    _query_task_transition,
    _snapshot_baseline,
    _task_observation,
)
from work.validate_alliance_reload import _diplomat_semantics


CASES = json.loads((Path(__file__).parent / "fixtures" /
    "improve_relations_r28_native_observations.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
@pytest.mark.parametrize("when", ("before", "after"))
def test_task_observation_agrees_with_native_result(case, when):
    observed = case[when]
    expected = case["native_result"]["task_" + when]
    task = _task_observation(observed["diplomats_snapshot"], "FRA", "SAV")
    assert task["task"] is expected
    assert _query_task_transition(observed["queries"], expected)
    diplomat = {
        "task": task,
        "semantics": _diplomat_semantics(observed["diplomats_snapshot"]),
        "snapshot_completeness": observed["diplomat_snapshot_completeness"],
    }
    checks = _snapshot_baseline(
        observed["health"], observed["control"], observed["probes"],
        diplomat, observed["queries"], case["action_id"], expected,
        case["native_result"]["date_raw"], require_selected_available=False,
    )
    assert all(checks.values()), checks


def test_recalled_diplomat_is_returning_while_start_is_unavailable():
    after = CASES["stop"]["after"]
    observed = _task_observation(after["diplomats_snapshot"], "FRA", "SAV")
    assert observed["matched_entries"][0]["entry"]["active_raw_18"] == 1
    assert observed["task"] is False
    assert after["queries"]["improve_relations"]["visibility"]["status"] == "visible"
    assert after["queries"]["improve_relations"]["legality"]["status"] == "unavailable"
