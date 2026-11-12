"""Static contract checks for the full S6-417/941 public native P2 gate.

The separate GitHub Actions OCI job executes the real 4-way --check-input.
These pytest checks never run the time-dependent native solver.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments" / "Issue402_plasma_dsl_g1"
PUBLIC = ROOT / "experiments" / "Issue493_s6_boltzmann"
EXPECTED_OVERLAY = "3c28bcc79e3ec17b7ceab858160a48150b78e37385f9d56725ae0e3cb22baaef"


def extract_overlay():
    text = (PILOT / "public_option_s6_p2.py").read_text()
    tree = ast.parse(text)
    matches = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "OVERLAY"
                for target in node.targets)
    ]
    assert len(matches) == 1
    return ast.literal_eval(matches[0].value)


def test_pinned_new_option_overlay_uses_canonical_species_provider_names():
    overlay = extract_overlay()
    assert hashlib.sha256(overlay.encode()).hexdigest() == EXPECTED_OVERLAY
    assert "fem_species = 'e'" in overlay
    assert "fvm_species = 'O2p Om Op'" in overlay
    assert "legacy_s6_state_names" not in overlay
    assert overlay.count("type = SpeciesTransportAliasMaterial") == 3
    assert "mobility_source = ion_mobility" in overlay
    assert "diffusivity_source = ion_diffusion" in overlay
    assert "fem_charge_numbers = '-1'" in overlay
    assert "fvm_charge_numbers = '1 -1 1'" in overlay
    # Provider names are derived in ContinuityEq, not user input.
    assert "fem_potential = potential" in overlay
    for forbidden in ("variables =", "fem_kernel_names", "fvm_kernel_names",
                      "fem_mobility =", "fem_diffusion =", "mobility =", "diffusivity ="):
        assert forbidden not in overlay



def test_canonical_s6_migration_changes_scratch_only(tmp_path):
    """Exercise the actual migration function without Docker or S6 solves."""
    import re

    script = (PILOT / "public_option_s6_p2.py").read_text()
    tree = ast.parse(script)
    declarations = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in
                {"CANONICAL_STATE_NAMES", "_STATE_TOKEN"} for t in node.targets)
    ]
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "canonicalize_staged_D_inputs"
    ]
    assert len(declarations) == 2 and len(functions) == 1
    namespace = {
        "re": re,
        "hashlib": hashlib,
        "Path": Path,
        "sha_file": lambda p: hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    exec(compile(ast.Module(body=declarations + functions, type_ignores=[]),
                 str(PILOT / "public_option_s6_p2.py"), "exec"), namespace)

    archived = tmp_path / "source"
    staged = tmp_path / "scratch"
    archived.mkdir()
    staged.mkdir()
    ordered = []
    sample = ("variable = log_ne\n"
              "coupled = 'log_ni log_nm log_nop'\n"
              "similar_name = log_ne_custom\n"
              "  [ne_time]\n"
              "    type = PhysicsFEMLogMolarTimeDerivative\n"
              "    variable = log_ne\n"
              "    block = plasma\n"
              "  []\n")
    for index in range(10):
        name = f"layer_{index}.i"
        content = sample if index == 0 else f"# original {index}\\n"
        (archived / name).write_text(content)
        (staged / name).write_text(content)
        ordered.append(f"chem/{name}")
    (staged / "migrated_continuity.i").write_text("PINNED_SIDECAR")
    ordered.append("chem/migrated_continuity.i")

    report = namespace["canonicalize_staged_D_inputs"](staged, ordered)
    assert report["status"] == "SCRATCH_ONLY_CANONICAL_STATE_AND_TIME_OWNER_REWRITE"
    assert report["removed_native_time"]["source_layer"] == "layer_0.i"
    assert report["removed_native_time"]["old_name"] == "ne_time"
    assert report["removed_native_time"]["generated_name"] == "e_time"
    assert report["removed_native_time"]["kernel_type"] == "PhysicsFEMLogMolarTimeDerivative"
    assert report["changed_reference_count"] == 4
    assert report["files"]["layer_0.i"]["original_sha256"] == (
        hashlib.sha256(sample.encode()).hexdigest())
    assert (archived / "layer_0.i").read_text() == sample
    assert (staged / "migrated_continuity.i").read_text() == "PINNED_SIDECAR"
    migrated = (staged / "layer_0.i").read_text()
    assert "variable = log_e" in migrated
    assert "coupled = 'log_O2p log_Om log_Op'" in migrated
    assert "similar_name = log_ne_custom" in migrated
    assert "[ne_time]" not in migrated
    assert "PhysicsFEMLogMolarTimeDerivative" not in migrated
    assert report["files"]["layer_0.i"]["staged_sha256"] == (
        hashlib.sha256(migrated.encode()).hexdigest())
    # A malformed, absent, or duplicated Native time term must fail BEFORE
    # any scratch file is rewritten. Never turn an ambiguous input into PASS.
    from pytest import raises
    time_block = ("  [ne_time]\n"
                  "    type = PhysicsFEMLogMolarTimeDerivative\n"
                  "    variable = log_ne\n"
                  "    block = plasma\n"
                  "  []\n")
    for fault, defective, extra in (
        ("missing", sample.replace(time_block, ""), ""),
        ("changed", sample.replace("    block = plasma\n", "    block = other\n"), ""),
        ("duplicate", sample, time_block),
    ):
        damaged = tmp_path / fault
        damaged.mkdir()
        for index in range(10):
            name = f"layer_{index}.i"
            body = defective if index == 0 else f"# original {index}\n"
            if index == 1:
                body += extra
            (damaged / name).write_text(body)
        (damaged / "migrated_continuity.i").write_text("PINNED_SIDECAR")
        snapshot = {name.name: name.read_bytes() for name in damaged.iterdir()}
        with raises(ValueError):
            namespace["canonicalize_staged_D_inputs"](damaged, ordered)
        assert snapshot == {name.name: name.read_bytes() for name in damaged.iterdir()}

    # The original decks are still byte-identical and cannot be confused
    # with the scratch-only canonical migration.
    assert all((archived / f"layer_{i}.i").read_text() ==
               (sample if i == 0 else f"# original {i}\\n") for i in range(10))


def test_full_s6_p2_provenance_and_no_solver_execution():
    script = (PILOT / "public_option_s6_p2.py").read_text()
    shell = PILOT / "run_public_option_s6_p2.sh"
    bash = shell.read_text()
    public = (PUBLIC / "public_p2_check.py").read_text()
    native = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert "29d1acc6ef7969908b86719e4b95c73a1565136d" in bash
    assert "export OXYGEN_RESEARCH_400=1" in bash
    assert "export OXYGEN_RESEARCH_FULL24=0" in bash
    assert "export OXYGEN_RESEARCH_EI2738_FORMULA=0" in bash
    assert "export OXYGEN_RESEARCH_QUICK_5MIN=0" in bash
    assert "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b" in bash
    assert "OVERLAY_SHA256" in script
    assert "p2.preflight(ROOT)" in script and "p2.stage(ROOT, historical, case" in script
    assert 'VARIANTS = ("B", "D")' in script
    assert " --check-input -i " in script
    assert '"--network", "none"' in script
    # The Native binary is linked from /workspace in the OCI build. Preserve
    # that mount path for runtime so libphysics_test-opt.so.0 is discoverable.
    assert '/workspace/physics_app/physics-opt --check-input -i ' in script
    assert 'trap \'rm -rf /case/.jitcache\' EXIT' in script
    assert "dst=/workspace,readonly" in script
    assert "NATIVE_RUNTIME_LINKER_ERROR" in script
    assert '"P3": "NOT_RUN"' in script and '"P4": "NOT_RUN"' in script
    assert "SCIENCE_HOLD" in script
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "preflight_public_option_s6.sh" in workflow
    assert "run_public_option_s6_p2.sh" in workflow
    assert "P0 - Public S6 environment and scratch-permission preflight" in workflow
    assert "P1 - Build PhysicsApp and verify generated and native solver operators" in workflow
    assert "P2 - Public S6-417 and S6-941 four-way Native input checks" in workflow
    assert "run_public_option_s6_p2.sh" not in native  # Independent P2 CI step
    assert "native_p1_identity.json" in native
    assert '"schema": "issue402.native_p1.job_local.v1"' in native
    assert "persist_report(evidence, report)" in script
    assert '"cleanup"] = "HOLD"' in script
    assert 'result.get("cleanup") == "PASS"' in script
    assert "option_s6_environment.json" in script
    assert "same_exact_head_ci_job_only" in script
    gate = PILOT / "preflight_public_option_s6.sh"
    gate_text = gate.read_text()
    assert "OXYGEN_RESEARCH" not in gate_text or "400" in gate_text
    assert "public_p2_check.py --control . --mode preflight" in gate_text
    assert "root_scratch_create_and_cleanup" in gate_text
    subprocess.run(["bash", "-n", str(gate)], check=True)
    assert "public_p2_decks.tar.xz.b64" in public
    assert "PACK_SHA" in public and "PINNED_SOURCE" in public
    assert "issue493_option_only" not in bash  # no secret runner or alternate old-rate owner
    subprocess.run(["bash", "-n", str(shell)], check=True)
    subprocess.run(["bash", "-n", str(PILOT / "run_native_binding_smoke.sh")], check=True)


def test_p2_case_verdict_survives_cleanup_failure(tmp_path):
    """Execute actual P2 control flow with a fault-injected cleanup failure.

    Four simulated, isolated Native PASS results must survive unchanged while
    the overall gate remains HOLD. No Docker, rate data or solver is invoked.
    """
    import json
    import os
    import tempfile
    from types import SimpleNamespace

    script = (PILOT / "public_option_s6_p2.py").read_text()
    tree = ast.parse(script)
    names = {"execute", "persist_report"}
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {fn.name for fn in functions} == names
    module = ast.Module(body=functions, type_ignores=[])

    root = tmp_path / "control"
    root.mkdir()
    (root / "manifest.json").write_text("{}")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    source = "a" * 40
    image = "pinned-ci-image@sha256:" + "b" * 64
    evidence.joinpath("option_s6_environment.json").write_text(json.dumps({
        "source_sha": source,
        "image": image,
        "public_p0": "PASS",
        "docker_mount": "PASS",
        "root_scratch_create_and_cleanup": "PASS",
        "host_cleanup": "PASS",
    }))

    def stage(_root, _historical, case, old_variant, staged, _manifest):
        staged.mkdir(parents=True)
        directory = staged / "chem"
        directory.mkdir()
        if old_variant == "C":
            directory.joinpath("migrated_continuity.i").write_text("OLD")
        return [f"{case}.i"]

    class CleanupFault:
        def __enter__(self):
            path = tmp_path / "scratch"
            path.mkdir()
            return str(path)

        def __exit__(self, *_args):
            raise PermissionError("simulated root-owned .jitcache")

    options = {
        "Path": Path,
        "os": os,
        "json": json,
        "hashlib": hashlib,
        "ROOT": root,
        "OCI": image,
        "OVERLAY": "new option input",
        "OVERLAY_SHA256": EXPECTED_OVERLAY,
        "CASES": ("417", "941"),
        "VARIANTS": ("B", "D"),
        "validate_overlay": lambda: None,
        "canonicalize_staged_D_inputs": lambda *_args: {"status": "SYNTHETIC_MIGRATION"},
        "check_source": lambda *_args: {"binary_sha256": "123"},
        "sha_file": lambda path: EXPECTED_OVERLAY if str(path).endswith("migrated_continuity.i") else "manifest-hash",
        "p2": SimpleNamespace(
            preflight=lambda _root: {"P0": "PASS"},
            DECKS=Path("."),
            PINNED_CANDIDATE="legacy-pinned",
            CHEM=Path("chem"),
            stage=stage,
        ),
        "run_one": lambda *_args: {"P2": "PASS", "exit_code": 0, "syntax_ok": True},
        "tempfile": SimpleNamespace(TemporaryDirectory=lambda **_kwargs: CleanupFault()),
    }
    exec(compile(module, str(PILOT / "public_option_s6_p2.py"), "exec"), options)
    report = options["execute"](tmp_path, tmp_path / "physics-opt", source, evidence)
    assert report["P2"] == "PASS"
    assert report["cleanup"] == "HOLD"
    assert report["status"] == "HOLD_INFRASTRUCTURE_CLEANUP"
    assert report["cleanup_error_class"] == "PermissionError"
    assert all(report["checks"][case][variant]["P2"] == "PASS"
               for case in ("417", "941") for variant in ("B", "D"))
    durable = json.loads((evidence / "issue402_option_s6_p2_status.json").read_text())
    assert durable["P2"] == "PASS"
    assert durable["status"] == "HOLD_INFRASTRUCTURE_CLEANUP"
    assert durable["P3"] == "NOT_RUN"
