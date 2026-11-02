#!/usr/bin/env python3
"""Native Oxygen25 first-run checkpoint harness, parameterized and fail-closed.

Use only the proven prepare/build/check/solve recipe. This module stages the
native first-run time grid and archives complete state; no CSV reconstruction,
no chemistry substitution, no old checkpoint recovery, no private rate export.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import math
from pathlib import Path
import re
import tarfile

SOURCE_SHA = "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
BUILD_REF = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
             "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
EEDF_SHA256 = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
EEDF_REPLACEMENT = Path("experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt")
EEDF_COPY = CHEM / "electron_transport_initial_eedf.txt"
NS = Decimal("1e-9")
MAX_TIME_NS = 100000
MAX_EVENTS = 20001
MIN_INTERVAL_NS = Decimal("0.001")
EXEC = re.compile(r"(?ms)^\[Executioner\]\s*\n(?P<body>.*?)^\[\]\s*$")
OUTPUT = re.compile(r"(?ms)^\[Outputs\]\s*\n(?P<body>.*?)^\[\]\s*$")
END = re.compile(r"(?m)^(\s*end_time\s*=\s*)[^#\n]+$")
SEQ = re.compile(r"(?m)^(\s*time_sequence\s*=\s*)'[^']*'\s*$")
STEPS = re.compile(r"(?m)^Time Step\s+(\d+),\s*time\s*=\s*([0-9.eE+-]+)")

INPUT_PARTS = (
    "rf_elastic_diss_ion_ei20_ei01_{p}w_adjacent_sheath_wall_closed_100us_dt1000ns.i",
    "rf_elastic_multiapp_parent_{p}w_100us_dt1000ns_overlay.i",
    "rf_elastic_multiapp_maxwell_{p}w_100us_dt1000ns_overlay.i",
    "rf_elastic_multiapp_maxwell_{p}w_100us_dt1000ns_child.i",
    "o2_elastic_{p}w_100us_dt1000ns_overlay.i",
    "o_elastic_ei17_{p}w_100us_dt1000ns_overlay.i",
    "full24_{p}w_100us_dt1000ns_overlay.i",
    "issue397_maxwell_steady_abs1e11.i",
    "a0_full_icp.i",
    "baseline_plasma_plus_unstructured_cover_plus_wafer.msh",
    "o2_elastic.txt",
    "o_elastic.txt",
    "electron_transport_initial_eedf.txt",
)


@dataclass(frozen=True)
class FirstCheckpoint:
    power_w: int
    end_ns: int
    interval_ns: str
    source_sha: str = SOURCE_SHA

    def __post_init__(self):
        if type(self.power_w) is not int or self.power_w not in (400, 1000):
            raise ValueError("power_w must be 400 or 1000")
        if type(self.end_ns) is not int or not 1 <= self.end_ns <= MAX_TIME_NS:
            raise ValueError("invalid first-run end_ns")
        if self.source_sha != SOURCE_SHA:
            raise ValueError("unreviewed physics/chemistry source SHA")
        if (Decimal(self.end_ns) / self.interval).to_integral_value(
                rounding=ROUND_CEILING) >= MAX_EVENTS:
            raise ValueError("time-grid event budget exceeded")

    @property
    def interval(self):
        try:
            result = Decimal(str(self.interval_ns))
        except Exception as exc:
            raise ValueError("unparseable interval_ns") from exc
        if not result.is_finite() or result < MIN_INTERVAL_NS:
            raise ValueError("interval_ns must be finite and >= 0.001 ns")
        return result

    @property
    def times(self):
        if self.end_ns == 1000 and self.interval_ns == "1":
            # One continuous 0–1us native MOOSE run (NOT a restart):
            # 0–100ns: 1ns, 100–1000ns: 10ns. Exactly 190 steps.
            sequence = [Decimal(i) for i in range(0,101)]
            sequence += [Decimal(i) for i in range(110,1001,10)]
            assert len(sequence) == 191 and sequence[-1] == Decimal(1000)
            return tuple(sequence)
        n = int((Decimal(self.end_ns) / self.interval).to_integral_value(
            rounding=ROUND_CEILING))
        times = [Decimal(0)]
        for index in range(1, n + 1):
            t = min(Decimal(self.end_ns), index * self.interval)
            if t > times[-1]:
                times.append(t)
        return tuple(times)

    @property
    def input(self):
        return CHEM / INPUT_PARTS[0].format(p=self.power_w)

    @property
    def result(self):
        return CHEM / ("results_rf_elastic_diss_ion_ei20_ei01_"
                       f"{self.power_w}w_adjacent_sheath_wall_closed_100us_dt1000ns")


def _one(regex, source, label):
    found = list(regex.finditer(source))
    if len(found) != 1:
        raise ValueError(f"expected exactly one {label}, got {len(found)}")
    return found[0]


def _seconds(ns):
    return format(ns * NS, ".17g")


def _ns(value):
    return Decimal(value.strip()) / NS


def verify_input(text, spec):
    if re.search(r"(?m)^\[Problem\]\s*$|^\s*restart_file_base\s*=", text):
        raise ValueError("first run cannot use previously restored state")
    body = _one(EXEC, text, "Executioner").group("body")
    if len(re.findall(r"(?m)^\s*type\s*=\s*TimeSequenceStepper\s*$", body)) != 1:
        raise ValueError("first-run TimeSequenceStepper missing")
    end = _ns(_one(END, body, "end_time").group().split("=", 1)[1])
    times = [_ns(s) for s in _one(SEQ, body, "time_sequence").group().split("'", 2)[1].split()]
    tol = Decimal("0.00000001")
    if (abs(end - spec.end_ns) > tol or len(times) != len(spec.times) or
            any(abs(a-b) > tol for a, b in zip(times, spec.times))):
        raise ValueError("staged time sequence/end does not match requested inputs")
    out = _one(OUTPUT, text, "Outputs").group("body")
    if len(re.findall(r"(?m)^\s*checkpoint\s*=\s*true\s*$", out)) != 1:
        raise ValueError("missing/ambiguous native checkpoint=true")


def stage_input(source, spec):
    if re.search(r"(?m)^\[Problem\]\s*$|^\s*restart_file_base\s*=", source):
        raise ValueError("cannot initialize using a restart")
    m = _one(EXEC, source, "Executioner")
    body = m.group("body")
    if len(re.findall(r"(?m)^\s*type\s*=\s*TimeSequenceStepper\s*$", body)) != 1:
        raise ValueError("unexpected source TimeStepper type")
    end = _ns(_one(END, body, "end_time").group().split("=", 1)[1])
    old = [_ns(s) for s in _one(SEQ, body, "time_sequence").group().split("'", 2)[1].split()]
    near = lambda a, b: abs(a-b) < Decimal("0.00000001")
    original = near(end, Decimal(2)) and len(old) == 3 and all(
        near(a, b) for a, b in zip(old, map(Decimal, (0, 1, 2))))
    staged = near(end, Decimal(spec.end_ns)) and old == list(spec.times)
    if not (original or staged):
        raise ValueError("unexpected prepared input time provenance")
    body = END.sub(lambda m: m.group(1) + _seconds(Decimal(spec.end_ns)), body, count=1)
    seq = " ".join(_seconds(t) for t in spec.times)
    body = SEQ.sub(lambda m: m.group(1) + "'" + seq + "'", body, count=1)
    changed = source[:m.start("body")] + body + source[m.end("body"):]
    out = _one(OUTPUT, changed, "Outputs")
    content = out.group("body")
    existing = re.findall(r"(?m)^\s*checkpoint\s*=\s*([^\s#]+)", content)
    if not existing:
        changed = changed[:out.start("body")] + "  checkpoint = true\n" + content + changed[out.end("body"):]
    elif existing != ["true"]:
        raise ValueError("checkpoint output already owned/disabled")
    verify_input(changed, spec)
    return changed


def _sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024*1024), b""):
            h.update(data)
    return h.hexdigest()


def _inventory(paths, root):
    rows = []
    for p in paths:
        if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(root):
            raise ValueError(f"unsafe/missing checkpoint member {p}")
        rel = p.relative_to(root).as_posix()
        if "private_rates" in rel or "OXYGEN24_RATES_TAR_XZ_B64" in rel:
            raise ValueError("protected rates must not appear in archive")
        rows.append({"path": rel, "bytes": p.stat().st_size, "sha256": _sha(p)})
    return sorted(rows, key=lambda row: row["path"])


def _archive(out, paths, inventory, root):
    with tarfile.open(out, "w:gz", dereference=False) as tar:
        for p in paths:
            tar.add(p, arcname=p.relative_to(root).as_posix(), recursive=False)
    with tarfile.open(out, "r:gz") as tar:
        members = tar.getmembers()
        expected = {r["path"]: r for r in inventory}
        if len(members) != len(expected) or set(m.name for m in members) != set(expected):
            raise ValueError("artifact member inventory changed")
        for member in members:
            if not member.isfile():
                raise ValueError("invalid archive member kind")
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError("empty archive stream")
            raw = stream.read()
            row = expected[member.name]
            if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("archived checkpoint hash/size changed")


def verify_and_archive(root, spec):
    root = root.resolve()
    if spec.end_ns != 1000 or spec.interval_ns != "1":
        raise ValueError("Research variant requires exact 0–1000 ns staged sequence")
    if _sha(root / EEDF_REPLACEMENT) != EEDF_SHA256 or _sha(root / EEDF_COPY) != EEDF_SHA256:
        raise ValueError("EEDF transport table identity mismatch (must be installed for plasma and RF)")
    result = root / spec.result
    run = result / "run"
    verify_input((root / spec.input).read_text(), spec)
    must = [run / "plasma.csv", run / "plasma.e",
            result / "runtime.log", result / "check_input.log",
            root / CHEM / "chem24_manifest.json"]
    if any(not p.is_file() or p.stat().st_size == 0 for p in must):
        raise ValueError("missing native runtime evidence")
    with (run / "plasma.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 2:
        raise ValueError("no native physical steps")
    times = [float(x["time"]) for x in rows]
    end_s = float(Decimal(spec.end_ns)*NS)
    if (any(not math.isfinite(t) for t in times) or
            any(y <= x for x,y in zip(times, times[1:])) or
            not math.isclose(times[0], 0, abs_tol=1e-16) or
            not math.isclose(times[-1], end_s, rel_tol=1e-12, abs_tol=1e-16)):
        raise ValueError("CSV native time history/end invalid")
    for name in ("n_O_ex_avg", "n_O_3P_avg", "chem24_monitor_R_936"):
        if name not in rows[-1] or not math.isfinite(float(rows[-1][name])):
            raise ValueError("missing/nonfinite O(ex) monitor: " + name)
    log = (result / "runtime.log").read_text(errors="replace")
    events = [(int(n), float(t)) for n,t in STEPS.findall(log)]
    if (not events or events[-1][0] < 1 or
            not math.isclose(events[-1][1], end_s, abs_tol=1e-16, rel_tol=1e-12) or
            re.search(r"(?i)\brecovering\b|\brestarting\b", log)):
        raise ValueError("native first-run solver final time absent or checkpoint restored")
    step_no = events[-1][0]
    cp = run / "plasma_cp"
    prefix = cp / f"{step_no:04d}"
    for p in (Path(str(prefix)+"-restart-0.rd/data"),
              Path(str(prefix)+"-restart-0.rd/header"),
              Path(str(prefix)+"-mesh.cpa.gz/1/header.gz")):
        if not p.is_file() or p.stat().st_size == 0:
            raise ValueError(f"missing native full-state checkpoint {p}")
    rates = json.loads((root / CHEM / "chem24_manifest.json").read_text())
    hashes = rates["lookup_sha256"]
    if (rates["active"] != 25 or rates["atoms_charge_mass"] != "PASS" or
            rates["ei936_rate_mode"] not in ("lookup", "analytic_maxwellian_fallback") or
            len(hashes) not in (19,20) or
            (("936" in hashes) != (rates["ei936_rate_mode"] == "lookup"))):
        raise ValueError("chemistry identity/rate hash inventory changed")
    inputs = [root / CHEM / name.format(p=spec.power_w) for name in INPUT_PARTS]
    run_files = sorted(p for p in run.rglob("*") if p.is_file() or p.is_symlink())
    if len(run_files) < 5:
        raise ValueError("full native run outputs incomplete")
    inv_run = _inventory(run_files, root)
    inv_inputs = _inventory(inputs, root)
    inv_cp = _inventory(sorted(p for p in cp.rglob("*") if p.is_file()), root)
    result.mkdir(parents=True, exist_ok=True)
    n = spec.end_ns
    run_tar = result / f"restart_run_{n}ns.tar.gz"
    inputs_tar = result / f"restart_inputs_{n}ns.tar.gz"
    _archive(run_tar, run_files, inv_run, root)
    _archive(inputs_tar, inputs, inv_inputs, root)
    manifest = {
        "schema": 5, "harness": "oxygen25-initial-checkpoint-v1",
        "power_w": spec.power_w, "source_sha": spec.source_sha,
        "final_time_s": end_s, "time_sequence_s": [float(t*NS) for t in spec.times],
        "interval_ns": str(spec.interval), "actual_moose_step": step_no,
        "chemistry": "25-effective-O(ex)-EI936",
        "ei936_mode": rates["ei936_rate_mode"], "ei936_energy_loss_eV": 4.19,
        "rate_sha256_private_rehydrate_required": hashes,
        "physics_build_base": BUILD_REF,
        "restart_output_base_relative": (run / "plasma").relative_to(root).as_posix(),
        "checkpoint_prefix": prefix.relative_to(root).as_posix(),
        "checkpoint_files": inv_cp, "run_files": inv_run, "input_files": inv_inputs,
        "archives": {p.name: {"bytes": p.stat().st_size, "sha256": _sha(p)}
                     for p in (run_tar, inputs_tar)},
        "recovery_requirements": {
            "same_source_sha": True, "same_container_image_and_native_app": True,
            "verify_private_rates_against_hashes": True,
            "restore_all_run_outputs_including_plasma_e": True,
            "same_input_overlays_and_mesh_paths": True,
            "no_prepare_after_restoring_state": True,
            "native_recover_prefix": prefix.relative_to(root).as_posix(),
            "note": "25-reaction state cannot be mixed with 24-reaction restart",
        },
        "scientific_acceptance": "HOLD",
        "electron_transport_variant": {
            "name": "initial_mix_23xsec_EEDF",
            "cross_section_selection": "19 rate-matched reaction ids + 4 momentum-transfer ids",
            "neutral_initial_mole_fractions": {"O2": 0.99997, "O2a": 1e-5, "O": 1e-5, "Os": 1e-5},
            "lookup_sha256": EEDF_SHA256,
            "lookup_path": "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt",
            "replaces_only": "electron transport table (also used by Maxwell RF coupling)",
            "source_type": "computed two-term EEDF research-only 23 cross sections",
            "table_mean_energy_range_eV": [1.658212908, 22.3312233],
            "timestep_plan_ns": [
                {"start":0,"end":100,"step":1},
                {"start":100,"end":1000,"step":10}
            ],
            "actual_native_run": "one_initialization_no_restart",
            "scientific_status": "SCIENCE_HOLD"
        },
    }
    (result / f"restart_{n}ns_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    print("OXYGEN25_INITIAL_NATIVE_CHECKPOINT_ARCHIVE_PASS", spec.power_w, n)
    return manifest


def self_test():
    old = ("[Executioner]\n  type = Transient\n  end_time = 2.0000000000000001e-9\n"
           "  [TimeStepper]\n    type = TimeSequenceStepper\n"
           "    time_sequence = '0 1e-9 2e-9'\n  []\n[]\n"
           "[Outputs]\n  csv = true\n  exodus = true\n[]\n")
    for power in (400,1000):
        for n,step in ((1,"1"),(2,"1"),(5,"0.5")):
            c = FirstCheckpoint(power,n,step)
            staged = stage_input(old,c)
            verify_input(staged,c)
            assert stage_input(staged,c) == staged
    research = FirstCheckpoint(400, 1000, "1")
    assert len(research.times) == 191
    assert research.times[100] == 100 and research.times[101] == 110
    assert research.times[-1] == 1000
    staged = stage_input(old, research)
    verify_input(staged, research)
    for bad in ("0","-1","NaN","Infinity","0.0001"):
        try:
            FirstCheckpoint(400,1,bad)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe input accepted")
    for bad in (old.replace("type = TimeSequenceStepper","type = ConstantDT"),
                old+"\n[Problem]\n  restart_file_base = 'x'\n[]\n",
                old.replace("time_sequence =","wrong_grid =")):
        try:
            stage_input(bad,FirstCheckpoint(400,1,"1"))
        except ValueError:
            pass
        else:
            raise AssertionError("unreviewed source accepted")
    print("OXYGEN25_PARAMETERIZED_FIRST_CHECKPOINT_SELFTEST_PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--stage-input", action="store_true")
    mode.add_argument("--verify-and-archive", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--power-w", type=int)
    parser.add_argument("--end-ns", type=int)
    parser.add_argument("--interval-ns", default="1")
    parser.add_argument("--source-sha", default=SOURCE_SHA)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.root is None or args.power_w is None or args.end_ns is None:
        parser.error("root, power-w, end-ns are required")
    spec = FirstCheckpoint(args.power_w, args.end_ns, args.interval_ns,
                           args.source_sha)
    root = args.root.resolve()
    if args.stage_input:
        target = root / spec.input
        target.write_text(stage_input(target.read_text(), spec))
        print("OXYGEN25_INITIAL_NATIVE_CHECKPOINT_INPUT_STAGED", spec.power_w, spec.end_ns)
    else:
        verify_and_archive(root, spec)


if __name__ == "__main__":
    main()
