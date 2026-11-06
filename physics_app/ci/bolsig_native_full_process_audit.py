"""User-local independent LXCat-to-native BOLSIG+ process/rate audit.

Original source tables and native output are never copied into repository
artifacts. This validates input/source identity and printed-output rates,
NOT numerical parity of the independent C++ solver.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median

GASES = frozenset({"Ar", "He", "N2", "O2"})
KINDS = frozenset({"ELASTIC", "EFFECTIVE", "MOMENTUM", "EXCITATION",
                   "IONIZATION", "ATTACHMENT", "ROTATION"})
GAMMA = math.sqrt(2 * 1.602176634e-19 / 9.1093837139e-31)
PROCESS = re.compile(
    r"^C(\d+)\s+(\S+)\s+(Effective \(momentum\)|Excitation|Ionization|Elastic|Attachment)"
    r"\s*(?:(\d+(?:\.\d+)?)\s+eV)?\s+"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[+-]?\d+)?)\s*$"
)


class NativeProcessAuditHold(ValueError):
    pass


@dataclass(frozen=True)
class CrossSection:
    line: int
    gas: str
    kind: str
    target: str
    energies: tuple[float, ...]
    values: tuple[float, ...]
    labelled_three_body: bool


@dataclass(frozen=True)
class Rate:
    number: int
    gas: str
    kind: str
    coefficient: float


def _separator(text: str) -> bool:
    value = text.strip()
    return len(value) >= 5 and set(value) == {"-"}


def parse_source(source: Path) -> list[CrossSection]:
    lines = source.read_text(encoding="utf-8").splitlines()
    processes = []
    for i, raw in enumerate(lines):
        kind = raw.strip()
        if kind not in KINDS:
            continue
        if i + 1 >= len(lines):
            raise NativeProcessAuditHold("missing collision target")
        target = lines[i + 1].strip()
        gas = target.split("<->", 1)[0].split("->", 1)[0].strip()
        if gas not in GASES:
            continue
        j = i + 2
        while j < len(lines) and not _separator(lines[j]):
            j += 1
        if j == len(lines):
            raise NativeProcessAuditHold("missing collision table delimiter")
        comments = " ".join(lines[i + 2:j]).lower()
        j += 1
        energies, values = [], []
        while j < len(lines) and not _separator(lines[j]):
            pair = lines[j].split()
            if len(pair) != 2:
                raise NativeProcessAuditHold(f"malformed cross-section row {j+1}")
            try:
                e, v = (float(s.replace("D", "E")) for s in pair)
            except ValueError as exc:
                raise NativeProcessAuditHold(f"non-numeric cross-section row {j+1}") from exc
            if not (math.isfinite(e) and math.isfinite(v) and e >= 0 and v >= 0):
                raise NativeProcessAuditHold(f"nonphysical cross section at line {j+1}")
            if energies and e <= energies[-1]:
                raise NativeProcessAuditHold(f"nonascending source energies at line {j+1}")
            energies.append(e)
            values.append(v)
            j += 1
        if j == len(lines) or len(energies) < 2:
            raise NativeProcessAuditHold("incomplete/power-law collision table")
        processes.append(CrossSection(
            i + 1, gas, kind, target, tuple(energies), tuple(values),
            "3-body" in comments or "3 body" in comments))
    if not processes:
        raise NativeProcessAuditHold("no gas collision processes")
    return processes


def parse_native(native: Path) -> tuple[list[Rate], list[tuple[float, float]], float]:
    lines = native.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("BOLSIG+ version:"):
        raise NativeProcessAuditHold("not a native BOLSIG+ run-by-run output")
    if sum(bool(re.fullmatch(r"R\d+\s*", line)) for line in lines) != 1:
        raise NativeProcessAuditHold("expected one native run")
    try:
        first = lines.index("Rate coefficients (m3/s)") + 1
        last = lines.index("Inverse rate coefficients (m3/s)")
    except ValueError as exc:
        raise NativeProcessAuditHold("native rate section absent") from exc
    rates = []
    for row in lines[first:last]:
        match = PROCESS.fullmatch(row.strip())
        if match:
            kind = ("EFFECTIVE" if match.group(3) == "Effective (momentum)"
                    else match.group(3).upper())
            value = float(match.group(5))
            if not math.isfinite(value) or value < 0:
                raise NativeProcessAuditHold("nonphysical native rate")
            rates.append(Rate(int(match.group(1)), match.group(2), kind, value))
    if not rates or [r.number for r in rates] != list(range(1, len(rates) + 1)):
        raise NativeProcessAuditHold("native process IDs incomplete/out of order")
    header = "Energy (eV) EEDF (eV-3/2) Anisotropy"
    if header not in lines:
        raise NativeProcessAuditHold("native printed EEPF section absent")
    eepf = []
    for row in lines[lines.index(header) + 1:]:
        parts = row.split()
        if len(parts) != 3:
            break
        try:
            energy, value, anisotropy = map(float, parts)
        except ValueError:
            break
        if not all(math.isfinite(x) for x in (energy, value, anisotropy)):
            raise NativeProcessAuditHold("nonfinite native distribution")
        if energy <= 0 or value < 0 or (eepf and energy <= eepf[-1][0]):
            raise NativeProcessAuditHold("nonphysical native energy/EEPF")
        eepf.append((energy, value))
    if len(eepf) < 8:
        raise NativeProcessAuditHold("too few native printed EEPF points")
    norm = sum((b[0] - a[0]) * (math.sqrt(a[0]) * a[1] +
                                  math.sqrt(b[0]) * b[1]) / 2
               for a, b in zip(eepf, eepf[1:]))
    if abs(norm - 1) > 0.02:
        raise NativeProcessAuditHold("native printed EEPF not normalized")
    return rates, eepf, norm


def _linear(x: tuple[float, ...], y: tuple[float, ...], e: float) -> float:
    if e < x[0] or e > x[-1]:
        return 0.0
    i = min(max(0, bisect_right(x, e) - 1), len(x) - 2)
    t = (e - x[i]) / (x[i + 1] - x[i])
    return y[i] * (1 - t) + y[i + 1] * t


def integrate_rate(process: CrossSection, distribution: list[tuple[float, float]]) -> float:
    """Integrate epsilon*sigma*f0 with cubic-exact Simpson at all source/EEPF knots."""
    energies = tuple(e for e, _ in distribution)
    values = tuple(f for _, f in distribution)
    low, high = energies[0], energies[-1]
    mesh = sorted(set(energies + tuple(e for e in process.energies if low < e < high)))
    def flux(e: float) -> float:
        return e * _linear(process.energies, process.values, e) * _linear(energies, values, e)
    area = 0.0
    for a, b in zip(mesh, mesh[1:]):
        area += (b - a) / 6 * (flux(a) + 4 * flux((a+b)/2) + flux(b))
    return GAMMA * area


def audit_case(source: Path, native: Path) -> dict:
    processes = parse_source(source)
    rates, eepf, normalization = parse_native(native)
    if len(processes) == len(rates):
        omitted_options: list[int | None] = [None]
    elif len(processes) == len(rates) + 1:
        omitted_options = list(range(len(processes)))
    else:
        omitted_options = []
    candidates = []
    for omission in omitted_options:
        aligned = [p for i, p in enumerate(processes) if i != omission]
        if any((p.gas, p.kind) != (r.gas, r.kind) for p, r in zip(aligned, rates)):
            continue
        errors, score = [], 0.0
        for p, r in zip(aligned, rates):
            estimate = integrate_rate(p, eepf)
            if r.coefficient > 0:
                if estimate <= 0:
                    score += 20
                else:
                    errors.append(abs(estimate / r.coefficient - 1))
                    score += abs(math.log10(estimate / r.coefficient))
        candidates.append((score, omission, errors))
    result = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "native_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
        "source_process_count": len(processes),
        "native_process_count": len(rates),
        "scientific_acceptance": "HOLD_REAL_COLLISION_PROCESS_EQUIVALENCE",
    }
    if not candidates:
        return {**result, "status": "HOLD_NATIVE_COLLISION_PROCESS_SEQUENCE_MISMATCH"}
    candidates.sort(key=lambda c: c[0])
    score, omission, errors = candidates[0]
    distinct = len(candidates) == 1 or candidates[1][0] - score > 3
    omitted = processes[omission] if omission is not None and distinct else None
    attachments = [p for p in processes if p.gas == "O2" and p.kind == "ATTACHMENT"]
    o2_native = [r for r in rates if r.gas == "O2" and r.kind == "ATTACHMENT"]
    maximum = max(errors) if errors else None
    return {
        **result,
        "status": ("HOLD_NATIVE_OMITTED_PROCESS" if omission is not None else
                   "HOLD_SOURCE_NATIVE_RATE_DISAGREEMENT" if maximum is None or maximum > .05
                   else "PROCESS_SEQUENCE_AND_PRINTED_RATES_AUDITED_NOT_PARITY"),
        "printed_eepf_points": len(eepf),
        "printed_eepf_bounds_eV": [eepf[0][0], eepf[-1][0]],
        "printed_eepf_normalization": normalization,
        "positive_rate_comparison_count": len(errors),
        "median_rate_relative_error": median(errors) if errors else None,
        "maximum_rate_relative_error": maximum,
        "predeclared_printed_rate_max_relative_tolerance": .05,
        "omission_unique_by_rate_evidence": distinct,
        "inferred_omitted_source_process": (
            {"gas": omitted.gas, "kind": omitted.kind, "line": omitted.line,
             "target": omitted.target} if omitted else None),
        "o2_attachment_candidates": [
            {"line": p.line, "target": p.target, "labelled_three_body": p.labelled_three_body,
             "unscaled_printed_eepf_integral_m3_per_s": integrate_rate(p, eepf),
             "native_attachment_m3_per_s": (o2_native[0].coefficient if len(o2_native) == 1 else None)}
            for p in attachments
        ],
        "limitations": [
            "Integrals restricted to printed EEPF energy interval",
            "Source-original data are not re-exported",
            "Missing process is never silently removed from a solver",
            "Three-body attachment density normalization requires independent review",
            "Matched source/native rates are NOT independent C++ solver EEPF parity",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cross-sections", type=Path, required=True)
    parser.add_argument("--native-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_case(args.cross_sections, args.native_output)
    except (OSError, UnicodeError, NativeProcessAuditHold) as exc:
        print("BOLSIG_NATIVE_PROCESS_PREFLIGHT_HOLD:", exc)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["status"].startswith("HOLD_") else 0


if __name__ == "__main__":
    raise SystemExit(main())
