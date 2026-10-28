"""Generate reproducible BOLSIG+ console reference conditions, without collision data.

The default preset is the *published fourth example* from the official
BOLSIG+ 07/2024 manual: Ar/He/N2/O2 = 0.70/0.20/0.08/0.02.

A two-component Ar/O2 benchmark is explicitly project-defined, NEVER
mislabelled as a BOLSIG+ program default.

The caller owns the externally obtained collision text; this tool neither
downloads, copies, embeds, nor redistributes third-party cross sections.
No BOLSIG+ execution or scientific parity is claimed by this generator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

DOCUMENTATION_URL = (
    "https://www.bolsig.laplace.univ-tlse.fr/wp-content/uploads/"
    "2024/07/bolsigdoc0724.pdf"
)
OFFICIAL_PRESETS: dict[str, tuple[tuple[str, float], ...]] = {
    "official_example1": (("Ar", 0.70), ("N2", 0.30)),
    "official_example4": (
        ("Ar", 0.70), ("He", 0.20), ("N2", 0.08), ("O2", 0.02)
    ),
}
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_.-]+$")


class ReferencePresetError(ValueError):
    pass


def _validate_input_file(source: Path) -> tuple[Path, str]:
    try:
        actual = source.resolve(strict=True)
    except OSError as exc:
        raise ReferencePresetError("collision source file does not exist") from exc
    if not actual.is_file() or actual.is_symlink() or not SAFE_FILENAME.fullmatch(actual.name):
        raise ReferencePresetError("collision source must be a regular file with a safe filename")
    if any(ch.isspace() for ch in str(actual)):
        raise ReferencePresetError("BOLSIG+ text path must not contain spaces")
    source_bytes = actual.read_bytes()
    if not source_bytes:
        raise ReferencePresetError("collision source is empty")
    return actual, hashlib.sha256(source_bytes).hexdigest()


def _mixture(preset: str, ar_fraction: float | None) -> tuple[tuple[str, float], ...]:
    if preset in OFFICIAL_PRESETS:
        if ar_fraction is not None:
            raise ReferencePresetError("official examples have immutable published fractions")
        return OFFICIAL_PRESETS[preset]
    if preset != "project_ar_o2_binary":
        raise ReferencePresetError("unknown gas mixture preset")
    if ar_fraction is None or not math.isfinite(ar_fraction) or not 0.0 < ar_fraction < 1.0:
        raise ReferencePresetError("project Ar/O2 requires explicit 0<--ar-fraction<1")
    return (("Ar", ar_fraction), ("O2", 1.0 - ar_fraction))


def make_reference_preset(
    source: Path, out_dir: Path, *,
    preset: str = "official_example4", ar_fraction: float | None = None
) -> dict:
    actual, digest = _validate_input_file(source)
    mixture = _mixture(preset, ar_fraction)
    if abs(sum(frac for _, frac in mixture) - 1.0) > 1e-12:
        raise ReferencePresetError("gas fractions do not sum to one")
    # BOLSIG+ text syntax: one READCOLLISIONS block loads all gas species.
    # All 21 ordered CONDITIONS fields match v07/2024 manual, example 4.
    # Numerical/physical defaults are *reference scenario settings*, not
    # assumptions silently made by the independent C++ solver.
    conditions = [
        "10.", "0.", "0.", "300.", "300.", "0.", "0.", "3e22",
        "1.", "1.", "1", "1", "1", "0.", "200", "0",
        "200.", "1e-10", "1e-4", "1000",
        " ".join(f"{frac:.17g}" for _, frac in mixture), "1"
    ]
    # Specifically 22 fields (numbered in official CLI reference, including
    # normalize-fractions). This test prevents accidental field-order drift.
    if len(conditions) != 22:
        raise RuntimeError("internal BOLSIG+ reference field count mismatch")
    script_name = f"{preset}_bolsigminus.txt"
    results_name = f"{preset}_raw_run_by_run.dat"
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ReferencePresetError("output directory must be new or empty; no overwrite")
    out_resolved = out_dir.resolve()
    if any(ch.isspace() for ch in str(out_resolved)):
        raise ReferencePresetError("output path must not contain spaces")
    script = "\n".join([
        "! Provenance-controlled original-script derivative; see manifest.",
        "! This file is NOT a BOLSIG+ numerical result.",
        "CLEARCOLLISIONS",
        "READCOLLISIONS",
        str(actual),
        "  ".join(species for species, _ in mixture),
        "0",  # Never permit undocumented source-energy extrapolation.
        "CONDITIONS",
        *conditions,
        "RUN",
        "SAVERESULTS",
        str(out_resolved / results_name),
        "1",  # Run by run: needed for independent EEDF/EEPF oracle extraction.
        "1", "1", "1", "1", "1", "1", "0",
        "END",
        "",
    ])
    out_dir.mkdir(parents=True, exist_ok=True)
    script_path = out_dir / script_name
    manifest_path = out_dir / f"{preset}_manifest.json"
    if script_path.exists() or manifest_path.exists():
        raise ReferencePresetError("refusing to overwrite BOLSIG+ reference files")
    sha_script = hashlib.sha256(script.encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": 1,
        "status": "REFERENCE_INPUT_ONLY_NOT_EXECUTED",
        "preset": preset,
        "is_official_manual_example": preset in OFFICIAL_PRESETS,
        "manual_version": "07/2024",
        "manual_url": DOCUMENTATION_URL,
        "mixture": dict(mixture),
        "collision_source_path": str(actual),
        "collision_source_sha256": digest,
        "script_file": script_name,
        "script_sha256": sha_script,
        "expected_raw_output": str(out_resolved / results_name),
        "conditions": {
            "E_over_N_Td": 10.0,
            "gas_temperature_K": 300.0,
            "excitation_temperature_K": 300.0,
            "electron_to_neutral_ratio": 0.0,
            "neutral_number_density_m3": 3e22,
            "energy_sharing": "equal",
            "growth_model": "temporal",
            "number_of_grid_points": 200,
            "automatic_energy_grid": True,
        },
        "important_overrides_from_manual": {
            "collision_extrapolation": (
                "0 (strict: off); manual example 4 uses 1 (on)"
            )
        },
        "requirements": [
            "BOLSIG+ CLI executed separately by user in authorized environment",
            "Complete cross-section coverage for every named gas species",
            "Independently verify all chemistry processes, including ROTATION and EFFECTIVE",
            "BOLSIG+ raw numerical output, not just an input script, required for parity",
            "No full-physics production approval without P2/P3 validation",
        ],
    }
    script_path.write_text(script, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cross-sections", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--preset", choices=(*OFFICIAL_PRESETS, "project_ar_o2_binary"),
        default="official_example4"
    )
    p.add_argument("--ar-fraction", type=float)
    a = p.parse_args()
    try:
        print(json.dumps(make_reference_preset(
            a.cross_sections, a.out, preset=a.preset, ar_fraction=a.ar_fraction
        ), sort_keys=True))
    except (OSError, ReferencePresetError) as exc:
        print("BOLSIG_REFERENCE_PRESET_HOLD:", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
