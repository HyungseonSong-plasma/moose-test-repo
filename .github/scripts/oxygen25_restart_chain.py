#!/usr/bin/env python3
"""Validate, stage and repackage genuine Oxygen25 EI936 cross-CI MOOSE checkpoints.

Never reconstruct solver state from CSV; never package private rate tables.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import shutil
import tarfile
from pathlib import Path

CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
BUILD_REF = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
             "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
EXEC_RE = re.compile(r"(?ms)^\[Executioner\]\n(?P<body>.*?)^\[\]\s*$")
OUTPUT_RE = re.compile(r"(?ms)^\[Outputs\]\n(?P<body>.*?)^\[\]\s*$")
END_RE = re.compile(r"(?m)^(\s*end_time\s*=\s*)[^#\n]+$")
SEQ_RE = re.compile(r"(?m)^(\s*time_sequence\s*=\s*)'[^']*'\s*$")

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def safe_path(root: Path, name: str) -> Path:
    rel = Path(name)
    if (not name or rel.is_absolute() or ".." in rel.parts or
            rel.parts[0] != "experiments" or "\\" in name):
        raise ValueError(f"unsafe artifact member: {name!r}")
    out = root / rel
    if not out.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"unsafe artifact destination: {name!r}")
    return out

def extract_checked(tar_path: Path, expected_sha: str, rows: list[dict], root: Path) -> None:
    if sha(tar_path) != expected_sha:
        raise ValueError(f"archive SHA256 mismatch: {tar_path.name}")
    with tarfile.open(tar_path, "r:gz") as archive:
        members = archive.getmembers()
        inventory = {row["path"]: row for row in rows}
        if len(members) != len(inventory) or set(m.name for m in members) != set(inventory):
            raise ValueError("archive member inventory mismatch")
        for member in members:
            if not member.isfile():
                raise ValueError(f"non-file archive member: {member.name}")
            target = safe_path(root, member.name)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("missing tar stream")
            data = stream.read()
            expected = inventory[member.name]
            if (len(data) != expected["bytes"] or
                    hashlib.sha256(data).hexdigest() != expected["sha256"]):
                raise ValueError(f"archive file SHA/size mismatch: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    print("OXYGEN25_RESTART_ARCHIVE_ROUNDTRIP_PASS", tar_path.name, len(rows))

def time_grid(text: str) -> tuple[int, list[int]]:
    matches = list(EXEC_RE.finditer(text))
    if len(matches) != 1:
        raise ValueError("nonunique Executioner")
    body = matches[0].group("body")
    ends, grids = list(END_RE.finditer(body)), list(SEQ_RE.finditer(body))
    if len(ends) != 1 or len(grids) != 1:
        raise ValueError("nonunique time grid")
    values = [float(ends[0].group().split("=", 1)[1])]
    values += [float(x) for x in grids[0].group().split("'", 2)[1].split()]
    def ns(value):
        if not math.isfinite(value):
            raise ValueError("nonfinite time")
        n = round(value / 1e-9)
        if not math.isclose(value, n * 1e-9, rel_tol=1e-12, abs_tol=1e-16):
            raise ValueError("time is not an integer ns")
        return n
    return ns(values[0]), [ns(v) for v in values[1:]]

def extend_input(text: str, start: int, end: int) -> str:
    if not 1 <= start < end <= 100 or time_grid(text) != (start, list(range(start + 1))):
        raise ValueError("wrong start checkpoint or time grid")
    outputs = list(OUTPUT_RE.finditer(text))
    if len(outputs) != 1 or len(re.findall(
            r"(?m)^\s*checkpoint\s*=\s*true\s*$", outputs[0].group("body"))) != 1:
        raise ValueError("missing/duplicate checkpoint output")
    match = next(EXEC_RE.finditer(text))
    body = match.group("body")
    body = END_RE.sub(lambda m: m.group(1) + format(end * 1e-9, ".17g"), body, count=1)
    grid = " ".join("0" if t == 0 else format(t * 1e-9, ".17g") for t in range(end + 1))
    body = SEQ_RE.sub(lambda m: m.group(1) + "'" + grid + "'", body, count=1)
    result = text[:match.start("body")] + body + text[match.end("body"):]
    if time_grid(result) != (end, list(range(end + 1))):
        raise ValueError("extended time grid did not round-trip")
    return result

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))

def verify_csv(path: Path, end: int, exact_rows: bool) -> list[dict[str, str]]:
    rows = read_csv(path)
    if not rows:
        raise ValueError("empty native CSV")
    times = [float(row["time"]) for row in rows]
    if any(not math.isfinite(t) for t in times):
        raise ValueError("nonfinite CSV time")
    if not math.isclose(times[-1], end * 1e-9, rel_tol=1e-12, abs_tol=1e-16):
        raise ValueError(f"wrong endpoint {times[-1]} vs {end} ns")
    if exact_rows:
        # Native recovery may introduce sub-nanosecond steps while preserving
        # every requested ns boundary.  Never equate CSV row index with ns.
        if (len(rows) < end + 1 or
                not math.isclose(times[0], 0.0, rel_tol=0, abs_tol=1e-16) or
                any(b <= a for a, b in zip(times, times[1:]))):
            raise ValueError("upstream CSV history not strictly time-ordered")
        for ns in range(end + 1):
            if not any(math.isclose(t, ns * 1e-9, rel_tol=1e-12, abs_tol=1e-16)
                       for t in times):
                raise ValueError(f"upstream CSV missing {ns} ns boundary")
    for key in ("n_O_ex_avg", "n_O_3P_avg", "chem24_monitor_R_936",
                "P_rf_raw_W_t6", "chem24_monitor_S_charge_closure_chem24",
                "chem24_monitor_S_mass_closure_chem24"):
        if key not in rows[-1] or not math.isfinite(float(rows[-1][key])):
            raise ValueError(f"nonfinite/missing chemistry monitor {key}")
    return rows

def result_path(power: int) -> Path:
    return CHEM / f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"

def restore(root: Path, artifact: Path, power: int, start: int, end: int, source_sha: str) -> None:
    matches = list(artifact.rglob(f"restart_{start}ns_manifest.json"))
    if len(matches) != 1:
        raise ValueError("missing/ambiguous exact upstream manifest")
    manifest = json.loads(matches[0].read_text())
    if (manifest["source_sha"] != source_sha or manifest["power_w"] != power or
            manifest["chemistry"] != "25-effective-O(ex)-EI936" or
            manifest["ei936_mode"] not in ("lookup", "analytic_maxwellian_fallback") or
            manifest["physics_build_base"] != BUILD_REF or
            not math.isclose(manifest["final_time_s"], start * 1e-9, abs_tol=1e-16)):
        raise ValueError("upstream source/power/chemistry/time/build identity mismatch")
    for kind in ("run", "inputs"):
        filename = f"restart_{kind}_{start}ns.tar.gz"
        tar_paths = list(artifact.rglob(filename))
        if len(tar_paths) != 1:
            raise ValueError(f"missing/ambiguous archive {filename}")
        extract_checked(tar_paths[0], manifest["archives"][filename]["sha256"],
                        manifest["run_files" if kind == "run" else "input_files"], root)
    result = result_path(power)
    run = root / result / "run"
    verify_csv(run / "plasma.csv", start, exact_rows=True)
    # Checkpoint prefixes are native MOOSE step IDs, not physical nanoseconds.
    # A recovered 2 ns run may end at step 7 after 1 ps substeps.
    actual_step = manifest.get("actual_moose_step")
    if type(actual_step) is not int or actual_step < start:
        raise ValueError("upstream actual MOOSE step missing or invalid")
    prefix = run / "plasma_cp" / f"{actual_step:04d}"
    expected_prefix = prefix.relative_to(root).as_posix()
    if manifest.get("recovery_requirements", {}).get("native_recover_prefix") != expected_prefix:
        raise ValueError("upstream recovery prefix does not match actual native step")
    for p in (Path(str(prefix) + "-restart-0.rd/data"),
              Path(str(prefix) + "-restart-0.rd/header"),
              Path(str(prefix) + "-mesh.cpa.gz/1/header.gz"),
              run / "plasma.e"):
        if not p.is_file() or not p.stat().st_size:
            raise ValueError(f"genuine upstream checkpoint/Exodus missing: {p}")
    (root / result / "recovery_prefix.txt").write_text(expected_prefix + "\n")
    inp = root / CHEM / f"rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"
    inp.write_text(extend_input(inp.read_text(), start, end))
    (root / result / "upstream_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    (root / result / "upstream_plasma.csv").write_bytes((run / "plasma.csv").read_bytes())
    print("OXYGEN25_EXACT_SOURCE_RESTORED_AND_INPUT_EXTENDED_PASS", power, start, end)

def verify_rates(root: Path, power: int, rate_dir: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "oxygen25", root / CHEM / "build_oxygen_24_source_overlay.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    files = module.validate_files(rate_dir)
    upstream = json.loads((root / result_path(power) / "upstream_manifest.json").read_text())
    expected = upstream["rate_sha256_private_rehydrate_required"]
    if set(map(str, files)) != set(expected):
        raise ValueError("private rate set changed")
    for rid, path in files.items():
        if sha(path) != expected[str(rid)]:
            raise ValueError(f"private rate hash mismatch: {rid}")
    if module.validate_network(936 in files)["ei936_rate_mode"] != upstream["ei936_mode"]:
        raise ValueError("EI936 lookup/fallback mode changed")
    destination = root / CHEM / "private_rates"
    destination.mkdir(parents=True, exist_ok=True)
    for rid, path in files.items():
        target = destination / path.name
        if target.exists() and sha(target) != expected[str(rid)]:
            raise ValueError(f"conflicting staged rate {rid}")
        if not target.exists():
            shutil.copyfile(path, target)
        if sha(target) != expected[str(rid)]:
            raise ValueError(f"staged private rate hash mismatch {rid}")
    print("OXYGEN25_PRIVATE_RATE_REHYDRATION_SHA256_PASS", len(files), upstream["ei936_mode"])

def native_final_step(log: str, end: int, previous_step: int) -> int:
    """Bind checkpoint numbering to the actual native final step and time."""
    matches = re.findall(
        r"(?m)^Time Step\s+(\d+),\s*time\s*=\s*([0-9.eE+-]+)", log)
    if not matches:
        raise ValueError("native solver log contains no time-step records")
    step, time_s = int(matches[-1][0]), float(matches[-1][1])
    if (step <= previous_step or not math.isfinite(time_s) or
            not math.isclose(time_s, end * 1e-9, rel_tol=1e-12, abs_tol=1e-16)):
        raise ValueError(
            f"native final step/time inconsistent: step={step} time={time_s}, "
            f"previous={previous_step}, expected={end} ns")
    return step


def verify_recovery(root: Path, power: int, start: int, end: int, source_sha: str) -> None:
    result = result_path(power)
    run = root / result / "run"
    upstream = json.loads((root / result / "upstream_manifest.json").read_text())
    before = read_csv(root / result / "upstream_plasma.csv")
    after = verify_csv(run / "plasma.csv", end, exact_rows=False)
    if not any(float(row["time"]) > start * 1e-9 + 1e-16 for row in after):
        raise ValueError("no post-checkpoint time advancement")
    if len(after) < len(before) or any(row != after[i] for i, row in enumerate(before)):
        raise ValueError("upstream CSV history lost or changed")
    log = (root / result / "recovery_runtime.log").read_text(errors="replace")
    if not re.search(r"(?i)\brecover(?:y|ing|ed)?\b", log):
        raise ValueError("no native recovery log evidence")
    if not re.search(r"Time Step\s+\d+,\s*time\s*=", log):
        raise ValueError("no native recovered time step evidence")
    last_step = native_final_step(log, end, upstream["actual_moose_step"])
    cp = run / "plasma_cp"
    checkpoint_prefix = cp / f"{last_step:04d}"
    for p in (Path(str(checkpoint_prefix) + "-restart-0.rd/data"),
              Path(str(checkpoint_prefix) + "-restart-0.rd/header"),
              Path(str(checkpoint_prefix) + "-mesh.cpa.gz/1/header.gz")):
        if not p.is_file() or not p.stat().st_size:
            available = sorted(x.name for x in cp.iterdir()) if cp.is_dir() else []
            raise ValueError(
                f"new native checkpoint absent: {p}; native step={last_step}; "
                f"available prefixes={available}")
    input_files = [root / row["path"] for row in upstream["input_files"]]
    run_files = sorted(p for p in run.rglob("*") if p.is_file())
    def inventory(paths):
        return sorted([{"path": p.relative_to(root).as_posix(),
                        "bytes": p.stat().st_size, "sha256": sha(p)}
                       for p in paths], key=lambda r: r["path"])
    archives = {}
    for kind, paths in (("run", run_files), ("inputs", input_files)):
        filename = f"restart_{kind}_{end}ns.tar.gz"
        destination = root / result / filename
        with tarfile.open(destination, "w:gz") as tar:
            for path in paths:
                if path.is_symlink():
                    raise ValueError("symlink in archived restart files")
                tar.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
        archives[filename] = {"bytes": destination.stat().st_size, "sha256": sha(destination)}
    manifest = {
        "schema": 2, "power_w": power, "source_sha": source_sha,
        "final_time_s": end * 1e-9, "time_sequence_s": [i*1e-9 for i in range(end+1)],
        "actual_moose_step": last_step,
        "checkpoint_prefix": checkpoint_prefix.relative_to(root).as_posix(),
        "chemistry": "25-effective-O(ex)-EI936",
        "ei936_mode": upstream["ei936_mode"], "ei936_energy_loss_eV": 4.19,
        "rate_sha256_private_rehydrate_required": upstream["rate_sha256_private_rehydrate_required"],
        "physics_build_base": BUILD_REF,
        "run_files": inventory(run_files), "input_files": inventory(input_files),
        "archives": archives, "upstream_archive_hashes": upstream["archives"],
        "recovery_requirements": {
            **upstream["recovery_requirements"],
            "native_recover_prefix": checkpoint_prefix.relative_to(root).as_posix(),
        },
        "upstream_time_ns": start, "recovered_time_ns": end,
        "last_monitors": {key: float(after[-1][key]) for key in
                          ("n_O_ex_avg", "n_O_3P_avg", "chem24_monitor_R_936", "P_rf_raw_W_t6")},
        "scientific_acceptance": "HOLD",
    }
    (root / result / f"restart_{end}ns_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    print("OXYGEN25_GENUINE_CROSS_RUN_RECOVERY_PASS", power, start, end, len(after))

def self_test() -> None:
    sample = ("[Executioner]\n  type = Transient\n  end_time = 1e-9\n"
              "  [TimeStepper]\n    type = TimeSequenceStepper\n"
              "    time_sequence = '0 1e-9'\n  []\n[]\n"
              "[Outputs]\n  checkpoint = true\n[]\n")
    assert time_grid(extend_input(sample, 1, 2)) == (2, [0, 1, 2])
    for bad in (sample.replace("checkpoint = true", "checkpoint = false"),
                sample.replace("1e-9'", "2e-9'")):
        try:
            extend_input(bad, 1, 2)
        except ValueError:
            continue
        raise AssertionError("invalid grid/checkpoint accepted")
    assert native_final_step("Time Step 7, time = 2e-09\n", 2, 1) == 7
    for bad_log in ("Time Step 2, time = 1e-09\n",
                    "Time Step 1, time = 2e-09\n"):
        try:
            native_final_step(bad_log, 2, 1)
        except ValueError:
            continue
        raise AssertionError("wrong native step/time accepted")
    # Native 1->2 ns evidence contains 1.001..1.005 ns substeps.
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "native.csv"
        fields = ("time", "n_O_ex_avg", "n_O_3P_avg", "chem24_monitor_R_936",
                  "P_rf_raw_W_t6", "chem24_monitor_S_charge_closure_chem24",
                  "chem24_monitor_S_mass_closure_chem24")
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for time_s in (0.0, 1e-9, 1.001e-9, 2e-9):
                writer.writerow({key: (time_s if key == "time" else 1.0)
                                 for key in fields})
        assert len(verify_csv(path, 2, exact_rows=True)) == 4
    print("OXYGEN25_RESTART_CHAIN_P0_SELFTEST_PASS")

def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--restore", type=Path)
    mode.add_argument("--verify-rates", type=Path)
    mode.add_argument("--verify-recovery", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--power-w", type=int, choices=(400, 1000))
    parser.add_argument("--start-ns", type=int)
    parser.add_argument("--end-ns", type=int)
    parser.add_argument("--source-sha")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if None in (args.power_w, args.start_ns, args.end_ns, args.source_sha):
        parser.error("--power-w, --start-ns, --end-ns, --source-sha required")
    root = args.root.resolve()
    if args.restore:
        restore(root, args.restore, args.power_w, args.start_ns, args.end_ns, args.source_sha)
    elif args.verify_rates:
        verify_rates(root, args.power_w, args.verify_rates)
    else:
        verify_recovery(root, args.power_w, args.start_ns, args.end_ns, args.source_sha)

if __name__ == "__main__":
    main()
