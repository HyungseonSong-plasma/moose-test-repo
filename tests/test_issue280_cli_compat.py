"""Issue #280 compatibility tests for the SOL transition CLI."""
from __future__ import annotations

from types import SimpleNamespace

from physics_harness.cli import app


def test_internal_architecture_regression_all_aliases(monkeypatch):
    commands = []
    def fake_run(value):
        commands.append(value)
        return 0
    monkeypatch.setattr(app, "_run_commands", fake_run)
    for target in ("architecture", "regression", "all"):
        assert app.main(["-i", target]) == 0
    assert "physics_sol_adapter_boundary_guard.py" in " ".join(commands[0][0])
    assert "--self-test" in commands[0][0]
    assert commands[1] == [[app.sys.executable, "-m", "pytest", "-q"]]
    assert commands[2] == commands[0] + commands[1]


def test_help_alias_preserved(capsys):
    assert app.main(["help"]) == 0
    output = capsys.readouterr().out
    assert "architecture" in output and "all" in output


def test_lower_explicitly_blocked_without_moose_fallback(capsys):
    assert app.main(["lower", "unused.json"]) == 3
    assert "LOWER_RETIRED" in capsys.readouterr().err


def test_run_never_infers_sol_model_or_dispatches_adapter(monkeypatch, capsys):
    planned = SimpleNamespace(
        semantic=SimpleNamespace(intent=SimpleNamespace(experiment_id="exp.test")),
        policy=SimpleNamespace(policy_id="policy.test"),
        execution_plan=SimpleNamespace(plan_id="plan.test"),
    )
    monkeypatch.setattr(app, "plan_experiment", lambda _: planned)
    assert app.main(["run", "unused.json"]) == 3
    result = capsys.readouterr()
    assert "PHYSICS_RUN_PREPARED: PASS" in result.out
    assert "EXPERIMENT=exp.test" in result.out
    assert "SOL_REQUEST: BLOCKED" in result.err
    assert "TARGET_EXECUTION" not in result.err
