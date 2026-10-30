#!/usr/bin/env python3
"""Fail-closed, local-only extraction of SELECTED Phelps O2 collision channels.

No Phelps numeric data or protected tables are bundled.  This program accepts
a locally obtained source PDF (or faithful pdftotext -layout text) and writes
local-only, source-hashed SI tables. Three-body attachment is excluded by the
canonical 25-reaction Chemistry Registry. It does NOT claim solver readiness.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess

SOURCE = "https://us.lxcat.net/notes/index.php?download=phelps5"
SCALE = 1e-20  # Phelps 1e-16 cm^2 to m^2; printed QSCALE ALREADY applied.
NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
INDEXED = re.compile(rf"^\s*(\d+)\s+({NUM})\s+({NUM})\s*$")


@dataclass(frozen=True)
class Channel:
    name: str
    heading: str
    count: int
    loss: float | None
    qscale: float | None
    kind: str
    threshold_anchor: float | None = None


# Select 17 of the 18 sections in the original Phelps O2 1978 collection.
# Explicit user decision: Three-body attachment is NOT in canonical 25-row
# Chemistry Registry, therefore no source extraction, no output CSV, no
# Boltzmann active channel, no rate calculation or O2- species addition.
# Other kinetic-only diagnostics are data candidates, NOT authorized chemistry
# reactions; no new chemistry reaction is activated by this extractor.
# Cosby (1993) O2 DISSOCIATION remains a separate, non-additive alternative.
FORBIDDEN_CHEMISTRY_CHANNELS = frozenset({"attachment_three_body"})
CHANNELS = (
    Channel("momentum_effective", "O2 MOMENTUM-TRANSFER CROSS SECTION",
            66, None, None, "EFFECTIVE_MOMENTUM"),
    Channel("attachment_two_body", "O2 TWO-BODY ATTACHMENT",
            20, 0., 1.2, "ATTACHMENT_TWO_BODY", 4.4),
    Channel("rotation_300K", "O2 SINGL LEVEL ROT PKQ FOR 300K",
            48, .020, 1., "ROTATION_WITH_SOURCE_DUPLICATE_KNOT"),
    Channel("v1_low", "O2 V=1 LINDER AND SCHMIDT WITH SPLIT PK",
            48, .190, 2.5, "VIBRATION"),
    Channel("v2_low", "O2 V=2 LINDER AND SCHMIDT X2",
            42, .380, 1.25, "VIBRATION"),
    Channel("v3_low", "O2 V=3 LINDER AND SCHMIDT X2 WITH 9EV RES FRM WONG-TRAJMAR",
            48, .570, 1.25, "VIBRATION"),
    Channel("v4_low", "O2 V=4 LINDER AND SCHMIDT X2 WITH 9EV RES FRM WONG-TRAJMAR",
            40, .750, 1.25, "VIBRATION"),
    Channel("v1_9eV", "O2 V=1 9V RES OF WONG ET AL NORM TO TRAJMAR ET AL",
            16, .190, 1., "VIBRATION_HIGH_ENERGY_CONTRIBUTION", 4.0),
    Channel("v2_9eV", "O2 V=2 9V RES OF WONG ET AL NORM TO TRAJMAR ET AL",
            16, .380, 1., "VIBRATION_HIGH_ENERGY_CONTRIBUTION", 4.0),
    Channel("a1delta", "O2 SING DELTA FROM LINDER-SCHMIDT AND TRAJMAR ET AL",
            26, .977, 1., "ELECTRONIC_O2_a1Delta", .977),
    Channel("b1sigma", "O2 B SINGLET SIGMA FROM LINDER-SCHMIDT AND TRAJMAR ET AL",
            26, 1.627, 1., "ELECTRONIC_O2_b1Sigma", 1.627),
    Channel("loss_4p5", "O2 4.5 LOSS", 16, 4.5, 1., "ENERGY_LOSS_ONLY", 4.5),
    Channel("loss_6", "O2 6.0 LOSS", 12, 6., 1., "ENERGY_LOSS_ONLY", 6.),
    Channel("loss_8p4", "O2 8.4 LOSS HAYASHI ABOVE 20EV - CHANTRY BELOW",
            18, 8.4, 1., "EFFECTIVE_EXCITATION", 8.4),
    Channel("loss_10", "O2 9.97 LOSS TRAJMAR",
            24, 10., 1., "EFFECTIVE_EXCITATION", 10.),
    Channel("ionization", "O2 IONIZATION",
            24, 12.06, 1., "IONIZATION", 12.06),
    Channel("line_130nm", "O2 130 NM LINE MUMMA-ZIPF",
            12, 14.7, 1., "EMISSION_LINE_EFFECTIVE", 14.7),
)
assert len(CHANNELS) == 17
assert not {ch.name for ch in CHANNELS} & FORBIDDEN_CHEMISTRY_CHANNELS


def load_source(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            x = subprocess.run(
                ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
                capture_output=True, text=True, check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("pdftotext -layout failed") from exc
        return x.stdout
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8")
    raise ValueError("Only original .pdf or faithful -layout .txt is accepted")


def extract(text: str, channel: Channel) -> tuple[list[tuple[float, float]], list[dict]]:
    title = re.compile(rf"(?m)^[ \t]*{re.escape(channel.heading)}[ \t]*$")
    matches = list(title.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"{channel.name}: expected one exact heading; got {len(matches)}")
    after = text[matches[0].end():]
    marker = (r"(?m)^[ \t]*ENERGY[ \t]+Effective[ \t]+Qm\b[^\n]*"
              if channel.kind == "EFFECTIVE_MOMENTUM" else
              r"(?m)^[ \t]*ENERGY[ \t]+CROSS[ \t]+SECTION(?:[ \t]+ENERGY[ \t]+CROSS[ \t]+SECTION)?[ \t]*$")
    m = re.search(marker, after)
    if m is None or m.start() > 1200:
        raise ValueError(f"{channel.name}: source column heading absent")
    head = after[:m.start()]
    if channel.loss is not None:
        loss = re.search(rf"ENERGY\s+LOSS\s*=\s*({NUM})", head)
        qscale = re.search(rf"QSCALE\s*=\s*({NUM})", head)
        if loss is None or qscale is None:
            raise ValueError(f"{channel.name}: source energy loss / QSCALE missing")
        if not math.isclose(float(loss.group(1)), channel.loss, abs_tol=1e-7):
            raise ValueError(f"{channel.name}: loss has changed")
        if not math.isclose(float(qscale.group(1)), channel.qscale, abs_tol=1e-7):
            raise ValueError(f"{channel.name}: QSCALE has changed")
    points: list[tuple[float, float]] = []
    for raw in after[m.end():].splitlines():
        line = raw.strip().replace("\f", "")
        if not line or re.fullmatch(r"Page\s+\d+\s+of\s+\d+", line):
            continue
        v = INDEXED.fullmatch(line)
        if v is None:
            if len(points) < channel.count:
                raise ValueError(f"{channel.name}: interrupted at {len(points)} points")
            break
        idx, e, sig = v.groups()
        if int(idx) != len(points) + 1:
            raise ValueError(f"{channel.name}: discontinuous source indices")
        energy, sigma = float(e), float(sig) * SCALE
        if not math.isfinite(energy) or not math.isfinite(sigma) or energy < 0 or sigma < 0:
            raise ValueError(f"{channel.name}: non-finite/negative source entry")
        points.append((energy, sigma))
        if len(points) == channel.count:
            break
    if len(points) != channel.count or points[0][0] != 0:
        raise ValueError(f"{channel.name}: count or initial energy differs")
    if channel.kind != "EFFECTIVE_MOMENTUM" and points[0][1] != 0:
        raise ValueError(f"{channel.name}: nonzero initial cross section")
    if channel.threshold_anchor is not None:
        if not math.isclose(points[1][0], channel.threshold_anchor, abs_tol=1e-8) or points[1][1] != 0:
            raise ValueError(f"{channel.name}: threshold anchor differs")
    duplicate_knots: list[dict] = []
    for j in range(1, len(points)):
        if points[j][0] < points[j - 1][0]:
            raise ValueError(f"{channel.name}: descending energies")
        if points[j][0] == points[j - 1][0]:
            if channel.kind != "ROTATION_WITH_SOURCE_DUPLICATE_KNOT":
                raise ValueError(f"{channel.name}: duplicate energy unsupported")
            duplicate_knots.append({"indices_1_based": [j, j + 1],
                                    "energy_eV": points[j][0]})
    if channel.kind == "ROTATION_WITH_SOURCE_DUPLICATE_KNOT" and not duplicate_knots:
        raise ValueError("rotation_300K: source duplicate knot disappeared, review required")
    return points, duplicate_knots


def collect(source: Path, out: Path, retrieved_on: str) -> dict:
    retrieved = date.fromisoformat(retrieved_on)
    if retrieved > date.today():
        raise ValueError("future retrieval date")
    source = source.resolve(strict=True)
    out = out.resolve()
    if source == out or out in source.parents:
        raise ValueError("original input/output directory overlap")
    text = load_source(source)
    # All-or-nothing parse BEFORE writing any output.
    selected = {ch.name for ch in CHANNELS}
    if selected & FORBIDDEN_CHEMISTRY_CHANNELS:
        raise ValueError("UNREGISTERED_CHEMISTRY: three-body attachment forbidden")
    processed = {ch.name: extract(text, ch) for ch in CHANNELS}
    paths = [out / f"o2_{ch.name}_sigma.csv" for ch in CHANNELS]
    manifest_path = out / "phelps_o2_core_manifest.json"
    if any(p.exists() for p in paths + [manifest_path]):
        raise FileExistsError("refusing to overwrite existing local source outputs")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "status": "EXTRACTED_SOURCE_ONLY_NOT_BOLTZMANN_READY",
        "source_url": SOURCE, "source_revision": "2008-06-24",
        "retrieved_on": retrieved.isoformat(),
        "source_filename": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_units": "1e-16 cm2",
        "conversion_to_m2": SCALE,
        "published_qscale_already_applied": True,
        "interpolation": "linear only on strictly increasing energy segments",
        "1978_original_source_sections": 18,
        "selected_source_sections": len(CHANNELS),
        "canonical_chemistry_table_reactions": 25,
        "excluded_unregistered_source_channels": sorted(FORBIDDEN_CHEMISTRY_CHANNELS),
        "chemistry_eligibility_policy": "ONLY_25_REGISTERED_REACTIONS; nonchemistry support is not chemistry activation",
        "excluded_outside_1978": "Cosby 1993 dissociation, available as separate alternative in PR #420",
        "scientific_gates": [
            "effective momentum includes inelastic scattering; do not use as elastic recoil",
            "rotation 300 K source duplicate energy must be adjudicated before interpolation",
            "three-body attachment excluded: not in canonical 25-reaction Chemistry Table",
            "v1/v2 low and 9eV resonance channels have the same product; audit combined accounting",
            "4.5-eV loss not established as 2O(3P) dissociation",
            "6-eV loss and Cosby dissociation are not additive without source reconciliation",
            "state/fragment branching in 8.4/10 eV and 130 nm effective channels unresolved",
            "full energy-domain/EEDF Boltzmann and production Physics validation not performed",
        ],
        "channels": {},
    }
    for ch, path in zip(CHANNELS, paths):
        points, duplicate = processed[ch.name]
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        column = "cross_section_m2"
        writer.writerow(("electron_energy_eV", column))
        for e, sigma in points:
            writer.writerow((f"{e:.17g}", f"{sigma:.17g}"))
        raw = buf.getvalue().encode("utf-8")
        path.write_bytes(raw)
        manifest["channels"][ch.name] = {
            "heading": ch.heading, "kind": ch.kind, "source_rows": ch.count,
            "source_qscale": ch.qscale, "energy_loss_eV": ch.loss,
            "path": path.name, "sha256": hashlib.sha256(raw).hexdigest(),
            "duplicate_knots": duplicate,
            "registry_chemistry_activation": False,
            "unregistered_attachment": False,
            "use_as_elastic_momentum": False,
            "solver_accepted": False,
        }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--retrieved-on", required=True)
    args = p.parse_args()
    r = collect(args.source, args.output_dir, args.retrieved_on)
    print(f"PHELPS_O2_SOURCE_EXTRACTED_ONLY count={len(r['channels'])}")
    print(f"source_sha256={r['source_sha256']}")
    print("UNREGISTERED_THREE_BODY_ATTACHMENT_EXCLUDED=true")
    print("SOLVER_READY=false (momentum, rotation, and chemistry gates remain)")


if __name__ == "__main__":
    main()
