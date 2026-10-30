#!/usr/bin/env python3
"""Acquire only four process-matched e + O numeric candidates from Zenodo.

Source: Schmalzried (2023), https://doi.org/10.5281/zenodo.8192503
Data: BOLSIG+ 'Cross section.txt' (2.7MB; includes many other species).
Published MD5: c0c1073f5ea940568ce4925b8b242e1a

CANDIDATE DATA only: different source fits than HPEM, not solver acceptance.
Do NOT publish underlying Zenodo numeric data without verifying source licensing.

Usage:
  python acquire_zenodo_atomic_o_cross_sections.py \
    --download --output-dir /private/path/oxygen_o_candidates
  python acquire_zenodo_atomic_o_cross_sections.py \
    --source "/private/path/Cross section.txt" --output-dir /private/path/processed
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.request import urlopen

URL = "https://zenodo.org/records/8192503/files/Cross%20section.txt?download=1"
DOI = "https://doi.org/10.5281/zenodo.8192503"
EXPECTED_MD5 = "c0c1073f5ea940568ce4925b8b242e1a"
EXPECTED = {
    "KIN-EL-O": ("ELASTIC", "O -> O", "E + O -> E + O, Momentum", 0.0),
    "EI-935": ("EXCITATION", "O -> O*((2p4)1D)",
               "E + O -> E + O*((2p4)1D), Electronic", 1.967),
    "EI-936": ("EXCITATION", "O -> O*((2p4)1S)",
               "E + O -> E + O*((2p4)1S), Electronic", 4.19),
    "EI-941": ("IONIZATION", "O -> O+", "E + O -> E + O+, Total", 13.6),
}
assert len(EXPECTED) == 4

FLOAT2 = re.compile(r"^\s*([-+]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)\s+"
                    r"([-+]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)\s*$")
ETH = re.compile(r"\bEth\s*=\s*([-+]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)")


def select(source_text: str) -> dict:
    """Parse EXACT expected e/O process labels; reject absent/duplicate sections."""
    lines = source_text.splitlines()
    matches: dict[str, dict] = {}
    for i, line in enumerate(lines):
        if line.strip() != "SPECIES: e / O" or i + 1 >= len(lines):
            continue
        if not lines[i + 1].startswith("PROCESS: "):
            raise ValueError("malformed source e/O process line")
        process = lines[i + 1][len("PROCESS: "):].strip()
        for key, (category, product, expected_process, threshold) in EXPECTED.items():
            if process != expected_process:
                continue
            if key in matches:
                raise ValueError(f"{key}: duplicate source section")
            # Category + process title precede the species marker in the source.
            before = [x.strip() for x in lines[max(0, i - 6):i]]
            if category not in before or product not in before:
                raise ValueError(f"{key}: category/title mismatch")
            param = next((x for x in lines[i + 2:i + 7] if x.startswith("PARAM.: ")), "")
            m = ETH.search(param)
            if not m or abs(float(m.group(1)) - threshold) > 1e-8:
                raise ValueError(f"{key}: source threshold mismatch")
            col_idx = next((j for j in range(i + 2, min(i + 12, len(lines)))
                            if lines[j].startswith("COLUMNS:  Energy (eV)")), None)
            if col_idx is None or col_idx + 1 >= len(lines):
                raise ValueError(f"{key}: missing COLUMNS metadata")
            if not lines[col_idx + 1].strip().startswith("----"):
                raise ValueError(f"{key}: missing numeric data delimiter")
            points: list[tuple[float, float]] = []
            for raw in lines[col_idx + 2:]:
                if raw.strip().startswith("----"):
                    break
                if not raw.strip():
                    continue
                parsed = FLOAT2.fullmatch(raw)
                if not parsed:
                    raise ValueError(f"{key}: malformed numeric row")
                energy, sigma = (float(parsed.group(1)), float(parsed.group(2)))
                if not (energy >= 0 and sigma >= 0):
                    raise ValueError(f"{key}: negative values")
                if points and energy <= points[-1][0]:
                    raise ValueError(f"{key}: nonincreasing energy")
                points.append((energy, sigma))
            if len(points) < 3 or points[0][0] < threshold - 1e-8:
                raise ValueError(f"{key}: insufficient or invalid energy data")
            matches[key] = {"points": points, "threshold_eV": threshold,
                            "source_process": process, "source_category": category,
                            "source_parameter": param, "num_points": len(points)}
    missing = sorted(set(EXPECTED) - set(matches))
    if missing:
        raise ValueError(f"Missing source-matched e/O data: {missing}")
    return matches


def acquire(*, source: Path | None, output_dir: Path, download: bool) -> dict:
    """Download/parse only locally; never commit raw source vectors to GitHub."""
    if (source is None) == (not download):
        raise ValueError("supply exactly one of --source and --download")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("output directory not empty; refuse overwrite")
    if source is not None:
        raw = source.read_bytes()
    else:
        # This is an EXPLICIT CLI action in the user's environment, not automated server access.
        with urlopen(URL, timeout=40) as response:
            raw = response.read(8_000_000)
        if len(raw) >= 8_000_000:
            raise ValueError("unexpectedly large source file")
    md5 = hashlib.md5(raw).hexdigest()
    if md5 != EXPECTED_MD5:
        raise ValueError("Source MD5 mismatch: Zenodo record may have changed")
    selected = select(raw.decode("utf-8-sig"))
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "status": "EXTERNAL_NUMERIC_CANDIDATE_NOT_HPEM_EQUIVALENT_NOT_SOLVER_ACCEPTED",
        "doi": DOI, "download_url": URL, "zenodo_md5": EXPECTED_MD5,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "retrieved_on": date.today().isoformat(),
        "source_units": {"energy": "eV", "cross_section": "m2"},
        "excluded_reactions_not_imported": ["KIN-R01", "KIN-E01", "KIN-E02",
            "KIN-EL-O2", "attachment_three_body"],
        "licensing_needs_manual_check": True,
        "entries": {},
    }
    for key, record in selected.items():
        out = output_dir / f"{key}_zenodo_candidate.csv"
        data = io.StringIO()
        writer = csv.writer(data, lineterminator="\n")
        writer.writerow(["energy_eV", "cross_section_m2"])
        writer.writerows(record["points"])
        b = data.getvalue().encode("ascii")
        out.write_bytes(b)
        manifest["entries"][key] = {
            "source_process": record["source_process"],
            "threshold_eV": record["threshold_eV"],
            "points": record["num_points"],
            "min_energy_eV": record["points"][0][0],
            "max_energy_eV": record["points"][-1][0],
            "source_parameter": record["source_parameter"],
            "sha256": hashlib.sha256(b).hexdigest(),
            "filename": out.name,
            "solver_ready": False,
            "hpem_equivalent": False,
        }
    (output_dir / "zenodo_atomic_o_candidate_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    exclusive = cli.add_mutually_exclusive_group(required=True)
    exclusive.add_argument("--source", type=Path)
    exclusive.add_argument("--download", action="store_true")
    cli.add_argument("--output-dir", required=True, type=Path)
    args = cli.parse_args()
    result = acquire(source=args.source, output_dir=args.output_dir,
                     download=args.download)
    print(f"NUMERIC_CANDIDATES={len(result['entries'])}, NOT_SOLVER_READY")
    print("SOURCE_SHA256=" + result["source_sha256"])


if __name__ == "__main__":
    main()
