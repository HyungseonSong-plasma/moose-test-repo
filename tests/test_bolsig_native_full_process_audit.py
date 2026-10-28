"""Synthetic native-to-source process reconciliation P0 controls; no LXCat data."""
from pathlib import Path

import hashlib
import pytest

from physics_app.ci.bolsig_native_full_process_audit import (
    NativeProcessAuditHold, audit_case, integrate_rate, parse_source,
)
from physics_app.ci.bolsig_local_matched_source import prepare_matched_source


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    collision = tmp_path / "invented_collisions.txt"
    collision.write_text(
        "ELASTIC\nAr\n1.37e-5\ninvented\n------\n"
        "0 5e-20\n10 5e-20\n------\n"
        "ATTACHMENT\nO2\ninvented 3-body source\n------\n"
        "0 1e-39\n10 1e-39\n------\n"
        "ATTACHMENT\nO2 -> O-\ninvented two-body source\n------\n"
        "0 1e-20\n10 1e-20\n------\n",
        encoding="utf-8",
    )
    energy = [i * .1 + .001 for i in range(100)]
    density = 1 / ((2 / 3) * (energy[-1]**1.5 - energy[0]**1.5))
    eepf = [(e, density) for e in energy]
    selected_rate = integrate_rate(parse_source(collision)[1], eepf)
    native = tmp_path / "invented_native_output.txt"
    native.write_text(
        "BOLSIG+ version: SYNTHETIC_NOT_BOLSIG\nR1  \n"
        "Rate coefficients (m3/s)\n"
        "C1    Ar    Elastic                      1.0E-14\n"
        f"C2    O2    Attachment                   {selected_rate:.12E}\n"
        "Inverse rate coefficients (m3/s)\n"
        "Energy (eV) EEDF (eV-3/2) Anisotropy\n"
        + "\n".join(f"{e:.9E} {f:.9E} 0.0" for e, f in eepf)
        + "\n",
        encoding="utf-8",
    )
    return collision, native


def test_synthetic_missing_two_body_process_is_not_silent_parity(tmp_path: Path) -> None:
    collision, native = _fixture(tmp_path)
    result = audit_case(collision, native)
    assert result["source_process_count"] == 3
    assert result["native_process_count"] == 2
    assert result["status"] == "HOLD_NATIVE_OMITTED_PROCESS"
    assert result["omission_unique_by_rate_evidence"]
    assert result["inferred_omitted_source_process"]["target"] == "O2 -> O-"
    assert result["scientific_acceptance"].startswith("HOLD_")
    assert len(result["o2_attachment_candidates"]) == 2


def test_extra_native_process_is_fail_closed(tmp_path: Path) -> None:
    collision, native = _fixture(tmp_path)
    native.write_text(native.read_text().replace(
        "Inverse rate coefficients (m3/s)",
        "C3    O2    Ionization    2.0 eV      1.0E-20\n"
        "Inverse rate coefficients (m3/s)",
    ))
    result = audit_case(collision, native)
    assert result["status"] == "HOLD_NATIVE_COLLISION_PROCESS_SEQUENCE_MISMATCH"


def test_source_hash_changes_without_changing_missing_process(tmp_path: Path) -> None:
    collision, native = _fixture(tmp_path)
    original = audit_case(collision, native)
    collision.write_text(collision.read_text().replace("1e-20", "2e-20"))
    modified = audit_case(collision, native)
    assert original["source_sha256"] != modified["source_sha256"]
    assert modified["status"] == "HOLD_NATIVE_OMITTED_PROCESS"
    assert modified["inferred_omitted_source_process"]["target"] == "O2 -> O-"



def test_local_explicit_omission_preserves_only_native_matched_source(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path)
    audited = audit_case(source, native)
    omitted = audited["inferred_omitted_source_process"]["line"]
    out = tmp_path / "PRIVATE_NOT_FOR_REDISRIBUTION.txt"
    kwargs = dict(
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
        excluded_source_line=omitted,
        three_body_convention="as-tabulated-unscaled",
    )
    result = prepare_matched_source(source, native, out, **kwargs)
    assert result["status"] == "LOCAL_MATCHED_INPUT_PREPARED_SCIENCE_HOLD"
    assert result["selected_process_count"] == 2
    assert result["scientific_acceptance"].startswith("HOLD_")
    assert [r.kind for r in parse_source(out)] == ["ELASTIC", "ATTACHMENT"]
    assert result["local_output_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    with pytest.raises(NativeProcessAuditHold, match="caller-specified"):
        prepare_matched_source(source, native, out, **{**kwargs, "excluded_source_line": 1})
    with pytest.raises(NativeProcessAuditHold, match="SHA256"):
        prepare_matched_source(source, native, out, **{**kwargs, "source_sha256": "0"*64})
    with pytest.raises(NativeProcessAuditHold, match="three-body"):
        prepare_matched_source(source, native, out,
                               **{**kwargs, "three_body_convention": "density-corrected"})
    with pytest.raises(NativeProcessAuditHold, match="overwrite"):
        prepare_matched_source(source, native, source, **kwargs)
