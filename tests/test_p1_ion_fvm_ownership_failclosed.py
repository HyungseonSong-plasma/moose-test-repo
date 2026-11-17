"""P1/P04-A static contract: reserve FV physics ownership without activating it.

The C++ runtime negative test and the actual New-only kernel generation belong
to later P04/P05/P14 gates.  These tests do not certify a Native build.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTINUITY = ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C"
S6 = ROOT / "experiments/Issue402_plasma_dsl_g1"


def test_legacy_hybrid_keeps_external_fv_kernel_owners_by_default():
    source = CONTINUITY.read_text(encoding="utf-8")
    assert '"fvm_kernel_ownership"' in source
    assert 'MooseEnum("external physics", "external")' in source
    for case in ("417", "941"):
        template = (S6 / f"s6_{case}_chemistry_run.template.i").read_text(
            encoding="utf-8"
        )
        assert "fvm_species = 'O2p Om Op'" in template
        assert "fvm_kernel_ownership" not in template


def test_physics_mode_fails_closed_until_fv_kernel_implementation():
    source = CONTINUITY.read_text(encoding="utf-8")
    mode_check = 'if (getParam<MooseEnum>("fvm_kernel_ownership") == "physics")'
    assert source.count(mode_check) == 1
    assert 'paramError("fvm_kernel_ownership",' in source
    assert "physics FVM Kernel ownership is not implemented yet" in source
    assert source.index(mode_check) < source.index("bind_json_initial(fem,")
    assert 'registerMooseAction("PhysicsApp", DDContinuityEq, "add_fv_kernel")' not in source
