"""Fail-closed, source-backed approximations for the frozen 33 oxygen collisions.

REVIEW CANDIDATES ONLY: no kinetic source term, solver EEDF, or runtime reaction
activation is allowed merely because a tabulated approximation is generated.
User-licensed numeric parent tables are not bundled here.

Source ids 401/407/412/415 from user-owned local Cantera/Phelps candidate files;
935/941 from separately sourced Zenodo 8192503 data.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
from pathlib import Path

K_B_EV_K = 8.617333262145e-5
BURROW_O2A_ATTACHMENT_PEAK_M2 = 4.6e-22  # 4.6e-18 cm2 ±1.3e-18 cm2
SIGMA_METHODS = {
    "EI-2067": ("DB", "EI-407", .977, 1.5, "DERIVED_REVIEW"),
    "EI-943": ("DB", "EI-935", 1.967, 1.8, "DERIVED_REVIEW"),
    "EI-2058": ("SHIFT_PEAK", "EI-401", (4.90, 3.50), None, "PROVISIONAL_REVIEW"),
    "EI-2069": ("SHIFT", "EI-412", (6.00, 5.02), 1., "PROVISIONAL_PRODUCT_HOLD"),
    "EI-2072": ("SHIFT", "EI-415", (12.06, 11.08), 1., "PROVISIONAL_REVIEW"),
    "EI-944": ("SHIFT", "EI-941", (13.60, 11.65), 1., "PROVISIONAL_REVIEW"),
}
RATE_ONLY = {"EI-417", "EI-2259"}
BENCHMARK_RATE_ONLY = {"EI-2058", "EI-2072"}
HOLD = {
    "EI-2068": "3.52eV threshold O+O product energetics not resolved",
    "EI-2073": "13.72eV 130nm associated source branching not resolved",
    "EI-2074": "EI-417 O+ partial ionization sigma not validated",
    "EI-2738": "O- detachment amplitude and threshold shape not fitted",
}
assert len(SIGMA_METHODS) == 6 and len(HOLD) == 4


def validate(points):
    if len(points) < 3:
        raise ValueError("at least three knots required")
    if any(not math.isfinite(e) or not math.isfinite(s) or e < 0 or s < 0 for e, s in points):
        raise ValueError("nonfinite/negative electron sigma or energy")
    if any(points[i][0] <= points[i - 1][0] for i in range(1, len(points))):
        raise ValueError("strictly increasing electron energies required")
    return points


def trim_unphysical_zero_anchor(points):
    """Avoid interpolating an artificial 10keV zero after a 10-50eV curve."""
    validate(points)
    if points[-1][1] == 0 and points[-1][0] > 10 * points[-2][0]:
        return validate(points[:-1])
    return points


def detailed_balance(points, delta, statistical_ratio):
    """sigma_reverse(E)=g_lower/g_upper*(E+delta)/E*sigma_forward(E+delta).

    At E=0 only, use the linear near-threshold interpolant's limiting value.
    This is a numerical convention rather than a measured cross section.
    """
    points = validate(points)
    if delta <= 0 or statistical_ratio <= 0:
        raise ValueError("invalid excitation energy or statistical ratio")
    idx = next((i for i, (en, sig) in enumerate(points)
                if abs(en - delta) < .001 and sig == 0), None)
    if idx is None or idx + 1 >= len(points):
        raise ValueError("parent threshold zero knot unavailable")
    above = [(en, sig) for en, sig in points[idx + 1:] if en > delta]
    e0, s0 = above[0]
    out = [(0., statistical_ratio * delta * s0 / (e0 - delta))]
    out += [(en - delta, statistical_ratio * en * sig / (en - delta))
            for en, sig in above]
    return validate(out)


def threshold_shift(points, source_threshold, target_threshold, scale=1.):
    """Energy-axis shift, with explicit zero threshold and NO extrapolation."""
    points = validate(points)
    if target_threshold <= 0 or source_threshold <= target_threshold or scale <= 0:
        raise ValueError("invalid source/target threshold or scaling")
    # The shifted source must have zero cross section at the chosen threshold.
    if not (points[0][0] <= source_threshold <= points[-1][0]):
        raise ValueError("source threshold outside numeric support")
    for (e0, s0), (e1, s1) in zip(points, points[1:]):
        if e0 <= source_threshold <= e1:
            y = s0 + (s1 - s0) * (source_threshold - e0) / (e1 - e0)
            if y > 1e-27:
                raise ValueError("source cross section nonzero at threshold")
            break
    offset = source_threshold - target_threshold
    out = [(target_threshold, 0.)]
    out += [(e - offset, scale * sig) for e, sig in points if e > source_threshold]
    return validate(out)


def derive(reaction_id, parent):
    if reaction_id in HOLD or reaction_id in RATE_ONLY:
        raise ValueError(f"{reaction_id} cannot produce sigma(E): HOLD or rate-only")
    kind, parent_id, param, ratio, status = SIGMA_METHODS[reaction_id]
    parent = trim_unphysical_zero_anchor(validate(parent))
    if kind == "DB":
        points = detailed_balance(parent, param, ratio)
        scale = 1.
    else:
        source_threshold, target_threshold = param
        scale = (BURROW_O2A_ATTACHMENT_PEAK_M2 / max(s for _, s in parent)
                 if kind == "SHIFT_PEAK" else ratio)
        points = threshold_shift(parent, source_threshold, target_threshold, scale)
    return points, {"reaction_id": reaction_id, "parent_id": parent_id,
                    "method": kind, "scale": scale, "status": status,
                    "solver_accepted": False, "boltzmann_eedf_verified": False,
                    "points": len(points), "max_eV": points[-1][0]}


def maxwellian_rate_m3_s(reaction_id, Te_eV):
    """Independent thermal benchmarks; NEVER substitute for non-Maxwellian rates."""
    if Te_eV <= 0 or not math.isfinite(Te_eV):
        raise ValueError("Te must be positive and finite")
    if reaction_id == "EI-2259":
        Te_K = Te_eV / K_B_EV_K
        if Te_K <= 200:
            raise ValueError("Peverall rate requires Te > 200K")
        # Extrapolation beyond approximately 5000K must be labelled invalid.
        return 2.4e-13 * (300 / Te_K)**.70
    if reaction_id == "EI-417":
        return 1.88e-16 * Te_eV**1.699 * math.exp(-16.81 / Te_eV)
    if reaction_id == "EI-2058":
        return 4.19e-15 * Te_eV**(-1.376) * math.exp(-5.19 / Te_eV)
    if reaction_id == "EI-2072":
        return 2.34e-15 * Te_eV**1.03 * math.exp(-11.31 / Te_eV)
    raise ValueError("no documented Maxwellian benchmark for "+reaction_id)


def derive_local_csv(reaction_id: str, parent_csv: Path, target_csv: Path,
                     manifest_path: Path):
    """Use locally acquired source arrays; do not commit source/output numbers."""
    files = [p.resolve() for p in (parent_csv, target_csv, manifest_path)]
    if len(set(files)) != 3 or target_csv.exists() or manifest_path.exists():
        raise ValueError("distinct source, output, manifest; output must not exist")
    with parent_csv.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        e_key = next((key for key in ("energy_eV", "electron_energy_eV")
                      if key in (reader.fieldnames or [])), None)
        if e_key is None or "cross_section_m2" not in reader.fieldnames:
            raise ValueError("parent requires energy_eV/cross_section_m2 columns")
        parent = [(float(row[e_key]), float(row["cross_section_m2"])) for row in reader]
    points, meta = derive(reaction_id, parent)
    target_csv.parent.mkdir(parents=True, exist_ok=True)
    with target_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("electron_energy_eV", "cross_section_m2"))
        writer.writerows(points)
    meta["source_sha256"] = hashlib.sha256(parent_csv.read_bytes()).hexdigest()
    meta["data_sha256"] = hashlib.sha256(target_csv.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(meta, indent=2, sort_keys=True)+"\n")
    return meta
