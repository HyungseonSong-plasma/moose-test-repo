"""Assert unused custom vector-postprocessing helpers remain retired.

The built-in MOOSE VectorPostprocessor support is unaffected by this cleanup.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED = (
    "CreateChangeMarker",
    "FilterForwardInterpolate",
    "InterpolationByFilteredVector",
)


def test_retired_vectorpostprocessor_sources_absent():
    for cls in RETIRED:
        for directory, suffix in (
            ("src", ".C"),
            ("include", ".h"),
        ):
            path = ROOT / "physics_app" / directory / "vectorpostprocessors" / (cls + suffix)
            assert not path.exists(), f"Unused vector postprocessor reintroduced: {path}"
