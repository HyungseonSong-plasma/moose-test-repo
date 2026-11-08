"""Research Mode v0.1: objective, scope, human confirmation, provenance and CLI gates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from physics_harness.application import research_session as research
from physics_harness.cli.commands import research as research_cli
from physics_harness.specification.research_objective import ResearchObjective


@pytest.fixture
def files(tmp_path):
    data = tmp_path / "experiment.csv"
    data.write_text("z,n_e\n23,1e17\n", encoding="utf-8")
    return data, tmp_path / "session.json"


def test_data_first_questions_scope_and_explicit_confirmation(files):
    data, session = files
    started = research.start(data, session)
    assert started["status"] == "AWAITING_GOAL"
    assert started["next_question"]["code"] == "ASK_RESEARCH_GOAL"
    assert started["ready_for_analysis"] is False
    with pytest.raises(research.ResearchNotReady, match="UNCONFIRMED"):
        research.require_analysis_ready(session)

    goal = research.submit_goal(session, "HPEM과 전자 밀도를 비슷하게 만든다")
    assert goal["status"] == "AWAITING_SCOPE"
    assert goal["next_question"]["code"] == "ASK_EVALUATION_SCOPE"
    assert {x["id"] for x in goal["next_question"]["options"]} == {
        "full_field", "representative_profiles", "key_features", "combined", "custom",
    }
    with pytest.raises(research.ResearchModeError, match="fully specified"):
        research.confirm(session, approve=True)

    refined = research.clarify_scope(session, "representative_profiles")
    assert refined["status"] == "AWAITING_CONFIRMATION"
    assert refined["next_question"]["code"] == "CONFIRM_RESEARCH_GOAL"
    assert refined["ready_for_analysis"] is False
    confirmed = research.confirm(session, approve=True)
    assert confirmed["status"] == "GOAL_CONFIRMED"
    assert confirmed["ready_for_analysis"] is True
    assert confirmed["data_integrity"] == "MATCH"
    assert confirmed["confirmation"]["source"] == "explicit_operator_confirmation"
    assert confirmed["evaluation_scope"] == "representative_profiles"
    assert research.require_analysis_ready(session)["ready_for_analysis"] is True
    saved = json.loads(session.read_text())
    assert [x["type"] for x in saved["events"]] == [
        "DATA_RECEIVED", "GOAL_PROPOSED", "SCOPE_CLARIFIED", "GOAL_CONFIRMED",
    ]


def test_direct_precise_goal_still_requires_explicit_human_approval(files):
    data, session = files
    research.start(data, session)
    got = research.submit_goal(
        session, "Compare reference electron density on full 2D domain",
        scope="full_field",
    )
    assert got["status"] == "AWAITING_CONFIRMATION"
    assert got["ready_for_analysis"] is False
    with pytest.raises(research.ResearchNotReady):
        research.require_analysis_ready(session)
    research.confirm(session, approve=True)
    with pytest.raises(research.ResearchModeError, match="immutable"):
        research.submit_goal(session, "change purpose", scope="key_features")


def test_rejection_returns_to_goal_question_and_revokes_analysis(files):
    data, session = files
    research.start(data, session)
    research.submit_goal(session, "Compare HPEM", scope="full_field")
    rejected = research.confirm(session, approve=False)
    assert rejected["status"] == "AWAITING_GOAL"
    assert rejected["objective"] is None
    assert rejected["confirmation"] is None
    assert rejected["ready_for_analysis"] is False
    assert rejected["next_question"]["code"] == "ASK_RESEARCH_GOAL"


def test_session_reuse_requires_new_confirmation_and_keeps_original_immutable(files, tmp_path):
    data, first = files
    research.start(data, first)
    research.submit_goal(first, "reproduce peak location", scope="key_features")
    research.confirm(first, approve=True)
    copy = tmp_path / "experiment_2.csv"
    copy.write_text("z,n_e\n23,1.2e17\n", encoding="utf-8")
    second = tmp_path / "session_2.json"
    proposed = research.start(copy, second, reuse_from=first)
    assert proposed["status"] == "AWAITING_CONFIRMATION"
    assert proposed["reused_from"] == research.status(first)["session_id"]
    assert proposed["objective"] == "reproduce peak location"
    assert proposed["ready_for_analysis"] is False
    with pytest.raises(research.ResearchNotReady):
        research.require_analysis_ready(second)
    research.confirm(second, approve=True)
    assert research.require_analysis_ready(second)["ready_for_analysis"] is True
    assert research.require_analysis_ready(first)["ready_for_analysis"] is True


def test_reuse_rejects_unconfirmed_previous_session(files, tmp_path):
    data, first = files
    research.start(data, first)
    new = tmp_path / "other.json"
    with pytest.raises(research.ResearchModeError, match="previously confirmed"):
        research.start(data, new, reuse_from=first)
    assert not new.exists()


def test_dataset_change_fail_closed_after_human_approval(files):
    data, session = files
    research.start(data, session)
    research.submit_goal(session, "compare spatial profile", scope="representative_profiles")
    research.confirm(session, approve=True)
    data.write_text("z,n_e\n24,9e12\n", encoding="utf-8")
    status = research.status(session)
    assert status["data_integrity"] == "MISSING_OR_CHANGED"
    assert status["ready_for_analysis"] is False
    with pytest.raises(research.ResearchNotReady, match="changed"):
        research.require_analysis_ready(session)


def test_custom_scope_requires_detail_and_no_unknown_option(files):
    data, session = files
    research.start(data, session)
    research.submit_goal(session, "characterize model error")
    with pytest.raises(ValueError, match="explicit human scope detail"):
        research.clarify_scope(session, "custom")
    with pytest.raises(ValueError, match="unknown evaluation scope"):
        research.clarify_scope(session, "cheapest_result")
    refined = research.clarify_scope(
        session, "custom",
        scope_detail="Match radial uniformity in the plasma operating region",
    )
    assert refined["scope_detail"].startswith("Match radial")
    assert research.confirm(session, approve=True)["ready_for_analysis"] is True
    with pytest.raises(ValueError, match="non-empty"):
        ResearchObjective("", "full_field")


def test_session_is_not_silently_overwritten(files):
    data, session = files
    research.start(data, session)
    with pytest.raises(research.ResearchModeError, match="already exists"):
        research.start(data, session)


def test_tampered_or_unversioned_confirmation_cannot_open_gate(files):
    data, session = files
    research.start(data, session)
    record = json.loads(session.read_text())
    record["status"] = "GOAL_CONFIRMED"
    record["objective"] = "make the plots look good"
    record["evaluation_scope"] = "full_field"
    record["confirmation"] = {"accepted": True, "source": "explicit_operator_confirmation",
                              "revision": 0, "at_utc": "2026-01-01T00:00:00Z"}
    session.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(research.ResearchModeError, match="transition missing"):
        research.require_analysis_ready(session)


def test_research_cli_gate_blocks_actual_analysis_command(files, monkeypatch, capsys):
    from physics_harness.cli import app as app_module

    data, session = files
    called = []
    monkeypatch.setattr(app_module, "main", lambda argv: called.append(argv) or 0)
    assert research_cli.main(["start", str(data), "--session", str(session)]) == 0
    assert research_cli.main(
        ["execute", str(session), "default-plot", "--help"]
    ) == 3
    assert called == []
    assert research_cli.main([
        "goal", str(session), "--objective", "compare electron profiles",
        "--scope", "representative_profiles",
    ]) == 0
    assert research_cli.main(["check", str(session)]) == 3
    assert research_cli.main(["confirm", str(session), "--approve"]) == 0
    assert research_cli.main(["check", str(session)]) == 0
    assert research_cli.main(
        ["execute", str(session), "default-plot", "--help"]
    ) == 0
    assert called == [["default-plot", "--help"]]
    assert "RESEARCH_MODE_BLOCKED" in capsys.readouterr().err
