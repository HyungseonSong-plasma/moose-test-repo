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


# Restart seeding is never permitted to overwrite the archived 2 ns plasma fields.
# Verified against both 400W/1000W source-input tarballs (15 parent variables).
EXPECTED_IC_VARIABLES = frozenset((
    "u", "v", "p", "w_O2s", "w_O", "w_Os", "log_ne", "log_ni",
    "log_nm", "log_nop", "log_energy", "potential", "sigma_s",
    "sigma_wafer", "sigma_focus_ring",
))
VARIABLE_BLOCK_RE = re.compile(r"(?ms)^\[Variables\][ \t]*\n(?P<body>.*?)^\[\][ \t]*$")
VARIABLE_CHILD_RE = re.compile(r"(?ms)^  \[(?P<name>[A-Za-z_][A-Za-z_0-9]*)\][ \t]*\n(?P<body>.*?)^  \[\][ \t]*$")
INLINE_IC_RE = re.compile(r"(?m)^[ \t]+initial_condition[ \t]*=[^\n]*(?:\n|$)")

def suppress_parent_restart_ics(text: str) -> str:
    """Only discard 15 declared parent variable seeds in an advanced restart.

    Advanced restart obtains field state from the full native checkpoint; keeping
    [Variables] initial_condition creates MOOSE ConstantIC objects that fail P2.
    Never turn on allow_initial_conditions_with_restart: that risks clobbering
    checkpointed plasma state. The original input remains in the upstream bundle.
    """
    if re.search(r"(?m)^\[ICs\][ \t]*$", text):
        raise ValueError("unreviewed explicit ICs block in parent restart input")
    blocks = list(VARIABLE_BLOCK_RE.finditer(text))
    if len(blocks) != 1:
        raise ValueError("missing/nonunique parent Variables block")
    block = blocks[0]
    body = block.group("body")
    configured = []
    for child in VARIABLE_CHILD_RE.finditer(body):
        count = len(INLINE_IC_RE.findall(child.group("body")))
        if count > 1:
            raise ValueError("duplicate variable IC: " + child.group("name"))
        if count:
            configured.append(child.group("name"))
    if (set(configured) != EXPECTED_IC_VARIABLES or
            len(configured) != len(EXPECTED_IC_VARIABLES)):
        raise ValueError("unexpected parent IC inventory: " + repr(sorted(configured)))
    cleaned, removed = INLINE_IC_RE.subn("", body)
    if removed != len(EXPECTED_IC_VARIABLES):
        raise ValueError("unmapped parent initial conditions: " + str(removed))
    result = text[:block.start("body")] + cleaned + text[block.end("body"):]
    if INLINE_IC_RE.search(result):
        raise ValueError("inline IC survived outside parent Variables block")
    return result

# FullSolveMultiApp in the original 0→2ns source uses no_restore=true.
# MOOSE rejects this when its parent is in advanced restart mode; only the
# *staged restart overlay* is changed, preserving the upstream source archive.
PARENT_MAXWELL_BLOCK_RE = re.compile(
    r"(?ms)^  \\[maxwell_t6\\][ \\t]*\\n(?P<body>.*?)^  \\[\\][ \\t]*$"
)
NO_RESTORE_TRUE_RE = re.compile(r"(?m)^(?P<indent>[ \\t]+)no_restore[ \\t]*=[ \\t]*true[ \\t]*$")
NO_RESTORE_ANY_RE = re.compile(r"(?m)^[ \\t]+no_restore[ \\t]*=[^\\n]*$")

def stage_parent_multiapp_restart_overlay(text: str) -> str:
    """Switch exactly the known Maxwell MultiApp to required restart restoration.

    A parent advanced restart must not disable MultiApp restoration. Reject
    unknown or duplicate parameters instead of silently changing physics.
    """
    blocks = list(PARENT_MAXWELL_BLOCK_RE.finditer(text))
    if len(blocks) != 1:
        raise ValueError("missing/nonunique Maxwell parent MultiApp block")
    b = blocks[0]
    body = b.group("body")
    if "type = FullSolveMultiApp" not in body:
        raise ValueError("unexpected Maxwell MultiApp type")
    if len(NO_RESTORE_ANY_RE.findall(text)) != 1:
        raise ValueError("unexpected parent no_restore inventory")
    changed, count = NO_RESTORE_TRUE_RE.subn(
        lambda m: m.group("indent") + "no_restore = false", body)
    if count != 1:
        raise ValueError("expected exactly one no_restore=true in Maxwell MultiApp")
    return text[:b.start("body")] + changed + text[b.end("body"):]


def advanced_restart_input(text: str, prefix: str) -> str:
    """MOOSE 9f388366: recover ignores an extended TimeSequenceStepper sequence.
    
    Problem/restart_file_base activates the genuine advanced *restart* path,
    which checks the saved sequence prefix and appends new future times.
    Keep the original deterministic mesh generator and all MultiApps.
    """
    if re.search(r"(?m)^\[Problem\]\s*$", text):
        raise ValueError("unexpected existing Problem block")
    if not re.fullmatch(
        r"experiments/Issue395_powered_chemistry_ladder/"
        r"results_rf_elastic_diss_ion_ei20_ei01_(400|1000)w_"
        r"adjacent_sheath_wall_closed_100us_dt1000ns/run/"
        r"plasma(?:_restart_\d+to\d+)?_cp/\d{4,}", prefix
    ):
        raise ValueError("invalid exact restart checkpoint prefix")
    cleaned = suppress_parent_restart_ics(text)
    # MOOSE resolves a relative restart base against the *input file folder*;
    # the manifest prefix is repository-root-relative. Use the fixed container
    # workspace root to avoid duplicating experiments/Issue395 in the path.
    return cleaned.rstrip() + "\n\n[Problem]\n  restart_file_base = '/workspace/" + prefix + "'\n[]\n"


def stage_base(start: int, end: int) -> str:
    if not 1 <= start < end <= 100:
        raise ValueError("invalid bounded stage")
    return f"plasma_restart_{start}to{end}"


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
    expected_prefix = manifest.get("recovery_requirements", {}).get("native_recover_prefix")
    if not isinstance(expected_prefix, str):
        raise ValueError("upstream native recovery prefix missing")
    prefix = root / expected_prefix
    if not prefix.resolve().is_relative_to(run.resolve()):
        raise ValueError("upstream checkpoint outside restored run directory")
    if not expected_prefix.endswith(f"/{actual_step:04d}"):
        raise ValueError("upstream checkpoint prefix does not match native step")
    latest_exodus = manifest.get("latest_exodus_file", (run / "plasma.e").relative_to(root).as_posix())
    for p in (Path(str(prefix) + "-restart-0.rd/data"),
              Path(str(prefix) + "-restart-0.rd/header"),
              Path(str(prefix) + "-mesh.cpa.gz/1/header.gz"),
              root / latest_exodus):
        if not p.is_file() or not p.stat().st_size:
            raise ValueError(f"genuine upstream checkpoint/Exodus missing: {p}")
    (root / result / "recovery_prefix.txt").write_text(expected_prefix + "\n")
    inp = root / CHEM / f"rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"
    inp.write_text(advanced_restart_input(extend_input(inp.read_text(), start, end), expected_prefix))
    parent_overlay = root / CHEM / f"rf_elastic_multiapp_parent_{power}w_100us_dt1000ns_overlay.i"
    parent_overlay.write_text(stage_parent_multiapp_restart_overlay(parent_overlay.read_text()))
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
    # Restart is NOT --recover: MOOSE 9f388366 preserves the old sequence on
    # recover, causing an out-of-bounds next time at a completed checkpoint.
    # Advanced restart updates the future sequence while restoring saved state.
    input_path = root / CHEM / f"rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"
    inp = input_path.read_text()
    old_prefix = upstream["recovery_requirements"]["native_recover_prefix"]
    if f"restart_file_base = '/workspace/{old_prefix}'" not in inp:
        raise ValueError("advanced restart source is not the verified checkpoint")
    stage = stage_base(start, end)
    stage_csv = run / (stage + ".csv")
    stage_exodus = run / (stage + ".e")
    if not stage_exodus.is_file() or not stage_exodus.stat().st_size:
        raise ValueError("new-stage native Exodus missing")
    after = verify_csv(stage_csv, end, exact_rows=False)
    times = [float(r["time"]) for r in after]
    if not math.isclose(times[0], start * 1e-9, rel_tol=1e-12, abs_tol=1e-16):
        raise ValueError("advanced restart did not output initial checkpoint boundary")
    if any(b <= a for a, b in zip(times, times[1:])) or times[-1] <= times[0]:
        raise ValueError("advanced restart time not strictly increasing")
    if list(after[0]) != list(before[-1]):
        raise ValueError("upstream/restarted CSV monitor schema changed")
    for key in before[-1]:
        a, b = float(before[-1][key]), float(after[0][key])
        if not (math.isfinite(a) and math.isfinite(b) and
                math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-12)):
            raise ValueError(f"restart boundary state discontinuity: {key} {a} -> {b}")
    # Canonical CSV history is stitched only after validating the actual new
    # native stage. The stage-specific native CSV and Exodus remain untouched.
    original_csv = run / "plasma.csv"
    if read_csv(original_csv) != before:
        raise ValueError("upstream original CSV modified before validation")
    with original_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(before[0]))
        writer.writeheader()
        writer.writerows(before + after[1:])
    verify_csv(original_csv, end, exact_rows=False)
    log = (root / result / "recovery_runtime.log").read_text(errors="replace")
    if not re.search(r"(?i)\brestart(?:ing|ed)?\b", log):
        raise ValueError("no native advanced restart log evidence")
    last_step = native_final_step(log, end, upstream["actual_moose_step"])
    cp = run / (stage + "_cp")
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
        "schema": 3, "power_w": power, "source_sha": source_sha,
        "final_time_s": end * 1e-9, "time_sequence_s": [i*1e-9 for i in range(end+1)],
        "actual_moose_step": last_step,
        "checkpoint_prefix": checkpoint_prefix.relative_to(root).as_posix(),
        "latest_exodus_file": stage_exodus.relative_to(root).as_posix(),
        "stage_csv_file": stage_csv.relative_to(root).as_posix(),
        "restart_mode": "advanced_restart_not_recover",
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
    print("OXYGEN25_GENUINE_CROSS_RUN_ADVANCED_RESTART_PASS", power, start, end, len(after))


def self_test() -> None:
    sample = ("[Executioner]\n  type = Transient\n  end_time = 1e-9\n"
              "  [TimeStepper]\n    type = TimeSequenceStepper\n"
              "    time_sequence = '0 1e-9'\n  []\n[]\n"
              "[Outputs]\n  checkpoint = true\n[]\n")
    assert time_grid(extend_input(sample, 1, 2)) == (2, [0, 1, 2])
    assert time_grid(extend_input(sample, 1, 100)) == (100, list(range(101)))
    prefix = ("experiments/Issue395_powered_chemistry_ladder/"
              "results_rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_100us_dt1000ns/"
              "run/plasma_cp/0004")
    seeded = ("[Variables]\n" +
              "".join("  [" + name + "]\n    initial_condition = 0.0\n  []\n"
                      for name in sorted(EXPECTED_IC_VARIABLES)) +
              "[]\n" + sample)
    advanced = advanced_restart_input(extend_input(seeded, 1, 100), prefix)
    assert "initial_condition =" not in advanced
    assert "[Variables]" in advanced and "end_time = " in advanced
    # Mutation controls: an unreviewed/new seed must fail closed, not silently
    # overwrite a restored charged/heavy field.
    try:
        suppress_parent_restart_ics(seeded.replace("    initial_condition = 0.0\n", "", 1))
    except ValueError:
        pass
    else:
        raise AssertionError("missing required parent seed was accepted")
    try:
        suppress_parent_restart_ics(seeded + "\n[ICs]\n  [bad]\n    type = ConstantIC\n  []\n[]\n")
    except ValueError:
        pass
    else:
        raise AssertionError("unexpected explicit ICs block was accepted")
    assert "restart_file_base = '/workspace/" + prefix + "'" in advanced
    overlay = ("[MultiApps]\n  [maxwell_t6]\n"
               "    type = FullSolveMultiApp\n    no_restore = true\n"
               "  []\n[]\n")
    staged = stage_parent_multiapp_restart_overlay(overlay)
    assert "no_restore = false" in staged
    assert "no_restore = true" not in staged
    for bad in (overlay.replace("no_restore = true", "no_restore = false"),
                overlay.replace("no_restore = true", "no_restore = true\n    no_restore = true"),
                overlay.replace("FullSolveMultiApp", "TransientMultiApp")):
        try:
            stage_parent_multiapp_restart_overlay(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid parent MultiApp restoration configuration accepted")
    assert "[Problem]" in advanced
    try:
        advanced_restart_input(advanced, prefix)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate advanced restart block accepted")
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
