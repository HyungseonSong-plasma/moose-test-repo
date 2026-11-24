"""Freeze the exact historical input bytes used by Issues #197 and #199.

The original Issue #1 experiment directory is *optional*: removing it later
must not make either diagnostic caller or these structural tests fail.
"""
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "experiments/historical_issue1_diagnostic_replays"

SNAPSHOTS = (
    (
        "issue197_h3",
        "migration_only_exact_phi_ic.i",
        "9906040c450e28b3f1de8628c3936cf3ad1dec74",
        ".github/scripts/issue197_h3_migration_audit.py",
        "experiments/Issue1_reactor_o2plus_integration/migration_only_exact_phi_ic/migration_only_exact_phi_ic.i",
        "QPXIonWallFluxMaterial",
    ),
    (
        "issue199_h5",
        "poisson_analytic.i",
        "5b20df8337828f74d40b122d2745310d46aa1b71",
        ".github/scripts/issue199_h5_known_charge.py",
        "experiments/Issue1_reactor_o2plus_integration/poisson_analytic/poisson_analytic.i",
        "QPXPlasmaChargeDensityMaterial",
    ),
)


def git_blob_sha(payload: bytes) -> str:
    prefix = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(prefix + payload).hexdigest()


@pytest.mark.parametrize("fixture_dir,filename,blob_sha,script,original,legacy_type", SNAPSHOTS)
def test_standalone_historical_diagnostic_fixture(
    fixture_dir: str,
    filename: str,
    blob_sha: str,
    script: str,
    original: str,
    legacy_type: str,
) -> None:
    payload = (FIXTURE_ROOT / fixture_dir / filename).read_bytes()
    assert git_blob_sha(payload) == blob_sha
    assert legacy_type.encode("ascii") in payload

    caller = (ROOT / script).read_text()
    assert (
        f"SOURCE = ROOT / 'experiments/historical_issue1_diagnostic_replays/{fixture_dir}'"
        in caller
    )
    assert "experiments/Issue1_reactor_o2plus_integration" not in caller
    assert not (ROOT / "tests/fixtures/issue1_legacy_consumers").exists()

    # Once history is retired, this file may be absent. The snapshot must
    # continue to work without it; while present, guard source identity.
    historical_path = ROOT / original
    if historical_path.is_file():
        assert historical_path.read_bytes() == payload


@pytest.mark.parametrize("fixture_dir,filename,blob_sha", [row[:3] for row in SNAPSHOTS])
def test_snapshot_identity_detects_a_mutation(
    fixture_dir: str, filename: str, blob_sha: str
) -> None:
    payload = (FIXTURE_ROOT / fixture_dir / filename).read_bytes()
    assert git_blob_sha(payload + b"\n# mutated") != blob_sha
