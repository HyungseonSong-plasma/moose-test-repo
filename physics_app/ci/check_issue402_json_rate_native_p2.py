#!/usr/bin/env python3
"""Exact-head syntax-only Native P2 owner of retired JSON-rate one-shot inputs.

Reuse the PhysicsApp binary built by run_native_binding_smoke.sh; never
compile here, execute timesteps, or claim original-rate scientific parity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "physics_app/ci"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_check(executable: Path, source: Path, working_dir: Path) -> None:
    result = subprocess.run(
        [str(executable), "--check-input", "-i", source.name],
        cwd=working_dir, capture_output=True, text=True, check=False,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0 or "Syntax OK" not in output:
        raise AssertionError(
            f"ISSUE402_RATE_NATIVE_P2_REJECTED:{source.name}:"
            f" exit={result.returncode} output={output[-3000:]}"
        )


def require_h05_canonical_energy(source: str) -> str:
    """Validate the canonical H05 Material inputs without rewriting the deck."""
    expected = """  [h05_log_molar_density]
    type = ADParsedFunctorMaterial
    property_name = h05_log_molar_density
    functor_names = 'n_e'
    functor_symbols = 'ne'
    expression = 'log(ne/6.02214076e23)'
  []
  [h05_log_molar_energy]
    type = ADParsedFunctorMaterial
    property_name = h05_log_molar_energy
    functor_names = 'mean_en'
    functor_symbols = 'energy'
    expression = 'log(energy/6.02214076e23)'
  []
  [mean_energy]
    type = ElectronEnergyMaterial
    electron_energy_density = h05_log_molar_energy
    electron_density = h05_log_molar_density
    state_form = log_molar_eV
  []"""
    if (source.count(expected) != 1
            or source.count("state_form = log_molar_eV") != 1
            or "physical_eV" in source):
        raise AssertionError("H05_CANONICAL_ENERGY_CONTRACT_CHANGED")
    return source


def self_test() -> None:
    import math
    from physics_app.ci.check_stage5_h05_runtime import runtime_input
    original = runtime_input()
    canonical = require_h05_canonical_energy(original)
    assert canonical == original
    assert "state_form = log_molar_eV" in canonical
    assert "type = FVCoupledForce" in canonical
    assert "v = S_e_h05" in canonical
    assert "coef = 1" in canonical
    for number_density, energy_density in ((1e15, 3e15), (2e19, 8e19)):
        actual = math.exp(
            math.log(energy_density / 6.02214076e23)
            - math.log(number_density / 6.02214076e23)
        )
        assert math.isclose(actual, energy_density / number_density, rel_tol=1e-13)
    try:
        require_h05_canonical_energy(
            original.replace("state_form = log_molar_eV", "state_form = physical_eV")
        )
    except AssertionError:
        pass
    else:
        raise AssertionError("H05_BRIDGE_MUTATION_NOT_REJECTED")
    # Mutation control for a fake executable: syntax acceptance must be
    # explicit, not inferred from process exit 0 or output-file existence.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "control.i"
        source.write_text("[Mesh]\n  type = GeneratedMesh\n[]\n")
        for expected, text in ((True, "Syntax OK"), (False, "Silently skipped syntax")):
            exe = root / "mock"
            exe.write_text("#!/usr/bin/env python3\nprint(" + repr(text) + ")\n")
            exe.chmod(0o755)
            try:
                run_check(exe, source, root)
            except AssertionError:
                if expected:
                    raise
            else:
                if not expected:
                    raise AssertionError("MUTATION_ACCEPTED_WITHOUT_SYNTAX_OK")
    print("ISSUE402_JSON_RATE_P2_MUTATION_SELF_TEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--p1-identity", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        if args.executable is None and args.p1_identity is None:
            return
    if not args.executable or not args.p1_identity:
        parser.error("both --executable and --p1-identity are required")

    expected_head = os.environ.get("EXPECTED_HEAD")
    expected_oci = os.environ.get("PINNED_BASE")
    if not expected_head or not expected_oci:
        raise AssertionError("REQUIRE_EXACT_HEAD_AND_PINNED_OCI")
    identity = json.loads(args.p1_identity.read_text())
    if (
        identity.get("source_sha") != expected_head
        or identity.get("oci_image") != expected_oci
        or identity.get("binary_sha256") != digest(args.executable)
        or identity.get("P1") != "PASS"
    ):
        raise AssertionError("ISSUE402_RATE_P1_BINARY_IDENTITY_CHANGED")

    # Exact obligations of old issue402-json-rate-native-once.yml, reused
    # rather than running a second MOOSE build in an independent workflow.
    from physics_app.ci.check_stage5_s5d_heavy_reactions import input_text
    from physics_app.ci.check_stage5_h05_runtime import runtime_input

    with tempfile.TemporaryDirectory(prefix="issue402-rate-p2-") as tmp:
        root = Path(tmp)
        for label, source in (
            ("H01_H04", input_text(600.0)),
            ("H05", require_h05_canonical_energy(runtime_input())),
        ):
            candidate = root / (label + ".i")
            candidate.write_text(source)
            run_check(args.executable, candidate, root)
            print(label + "_JSON_NATIVE_P2_PASS")
            if label == "H05":
                print("H05_CANONICAL_ENERGY_P2_PASS")
    run_check(args.executable, CI / "json_surface_rate_p2.i", CI)
    print("JSON_SURFACE_RATE_NATIVE_P2_PASS")
    print("ISSUE402_JSON_RATE_SHARED_NATIVE_P2_PASS_P3_NOT_RUN")


if __name__ == "__main__":
    main()
