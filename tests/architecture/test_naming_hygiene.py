from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RETIRED_BATCH_A_PATHS = (
    "qpx_harness/analysis/_coerce.py",
    "qpx_harness/analysis/stats_builder.py",
    "qpx_harness/analysis/stats_builder_characterization.py",
    "qpx_harness/evidence/errors.py",
    "qpx_harness/evidence/error_log.py",
)


def test_retired_architecture_cleanup_paths_are_physically_absent() -> None:
    present = [path for path in RETIRED_BATCH_A_PATHS if (ROOT / path).exists()]
    assert present == []
