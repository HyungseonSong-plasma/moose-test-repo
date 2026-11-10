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
EXPECTED_OVERLAY = "a64ed0f6acbb9b96bdf0de31a977de496c01cb1eccca3badfe1fe97682818831"


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


def test_pinned_new_option_overlay_keeps_existing_material_and_functor_names():
    overlay = extract_overlay()
    assert hashlib.sha256(overlay.encode()).hexdigest() == EXPECTED_OVERLAY
    assert "fem_species = 'e'" in overlay
    assert "fvm_species = 'O2p Om Op'" in overlay
    assert "fem_charge_numbers = '-1'" in overlay
    assert "fvm_charge_numbers = '1 -1 1'" in overlay
    assert "mobility = 'electron_mobility ion_mobility negative_ion_mobility atomic_positive_ion_mobility'" in overlay
    assert "diffusivity = 'electron_diffusion ion_diffusion negative_ion_diffusion atomic_positive_ion_diffusion'" in overlay
    for forbidden in ("variables =", "fem_kernel_names", "fvm_kernel_names",
                      "fem_mobility =", "fem_diffusion =", "electron_diffusivity"):
        assert forbidden not in overlay


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
    assert "exec /workspace/physics_app/physics-opt --check-input -i " in script
    assert "dst=/workspace,readonly" in script
    assert "NATIVE_RUNTIME_LINKER_ERROR" in script
    assert '"P3": "NOT_RUN"' in script and '"P4": "NOT_RUN"' in script
    assert "SCIENCE_HOLD" in script
    assert "run_public_option_s6_p2.sh" in native
    assert "public_p2_decks.tar.xz.b64" in public
    assert "PACK_SHA" in public and "PINNED_SOURCE" in public
    assert "issue493_option_only" not in bash  # no secret runner or alternate old-rate owner
    subprocess.run(["bash", "-n", str(shell)], check=True)
    subprocess.run(["bash", "-n", str(PILOT / "run_native_binding_smoke.sh")], check=True)
