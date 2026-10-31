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
from decimal import Decimal, ROUND_CEILING

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

NS_S = Decimal("1e-9")
MAX_TIME_NS = 500000  # Five separately verified stages: 500 us terminal horizon
MAX_SEQUENCE_EVENTS = 20001

# The legacy 2 ns --recover native checkpoint retained a corrupted
# TimeSequenceStepper sequence (P3: 1.1907e-321 s), inconsistent with
# current_step=4. Preserve full native fields but replace only timestep
# policy for advanced restart. MOOSE IterationAdaptiveDT is restart safe.
RESTART_TIME_STEPPER_RE = re.compile(
    r"(?ms)^  \[TimeStepper\]\n(?P<body>.*?)^  \[\][ \t]*$"
)

def stage_adaptive_stepper(text: str, interval_ns: str,
                           already_staged: bool = False) -> str:
    requested = Decimal(str(interval_ns))
    if not requested.is_finite() or requested <= 0:
        raise ValueError("invalid timestep interval")
    # Five-stage mode uses the requested stage spacing as an adaptive upper
    # bound; MOOSE may take smaller steps or cut back. This is NOT a claim
    # that 10us is stable for the plasma/RF model; acceptance requires
    # per-stage P3 numerical and P4 continuity evidence.
    if requested > Decimal("10000"):
        raise ValueError("stage dt cap exceeds verified schedule upper bound")
    dt_cap = requested
    dt_initial = min(dt_cap, Decimal("0.001"))
    if dt_initial < Decimal("0.001"):
        raise ValueError("requested timestep below verified 1 ps floor")
    matches = list(EXEC_RE.finditer(text))
    if len(matches) != 1:
        raise ValueError("missing Executioner")
    exec_block = matches[0]
    body = exec_block.group("body")
    steps = list(RESTART_TIME_STEPPER_RE.finditer(body))
    if len(steps) != 1:
        raise ValueError("missing/nonunique TimeStepper")
    m = steps[0]
    old = m.group("body")
    expected_type = "IterationAdaptiveDT" if already_staged else "TimeSequenceStepper"
    if len(re.findall(r"(?m)^[ \t]*type[ \t]*=[ \t]*" + expected_type + r"[ \t]*$", old)) != 1:
        raise ValueError("unreviewed checkpoint TimeStepper type")
    if not already_staged and len(SEQ_RE.findall(old)) != 1:
        raise ValueError("missing legacy TimeSequenceStepper sequence")
    if already_staged and "reset_dt = true" not in old:
        raise ValueError("continued restart missing reset_dt")
    fmt = lambda n: format(n * NS_S, ".17g")
    step = ("  [TimeStepper]\n"
            "    type = IterationAdaptiveDT\n"
            "    dt = " + fmt(dt_initial) + "\n"
            "    growth_factor = 2\n"
            "    reset_dt = true\n  []")
    body = body[:m.start()] + step + body[m.end():]
    for name, num in (("dtmin", dt_initial), ("dtmax", dt_cap)):
        exp = re.compile(r"(?m)^  " + name + r"[ \t]*=[^\n]*$")
        if len(exp.findall(body)) > 1:
            raise ValueError("duplicate Executioner " + name)
        if exp.search(body):
            body = exp.sub("  " + name + " = " + fmt(num), body)
        else:
            body = body.rstrip() + "\n  " + name + " = " + fmt(num) + "\n"
    result = text[:exec_block.start("body")] + body + text[exec_block.end("body"):]
    if "type = TimeSequenceStepper" in result or "time_sequence =" in result:
        raise ValueError("legacy time stepper survived advanced restart")
    return result

def time_grid(text: str) -> tuple[int, list[Decimal]]:
    """Parse actual MOOSE time sequence without rounding sub-ns targets."""
    matches = list(EXEC_RE.finditer(text))
    if len(matches) != 1:
        raise ValueError("nonunique Executioner")
    body = matches[0].group("body")
    ends, grids = list(END_RE.finditer(body)), list(SEQ_RE.finditer(body))
    if len(ends) != 1 or len(grids) != 1:
        raise ValueError("nonunique time grid")
    try:
        # Prior 2ns files used float .17g (2.0000000000000001e-9).
        # Normalize only representation noise at 1e-17 s resolution.
        quant = Decimal("0.00000001")
        end_ns = (Decimal(ends[0].group().split("=", 1)[1].strip()) / NS_S).quantize(quant)
        seq_ns = [(Decimal(x) / NS_S).quantize(quant) for x in
                  grids[0].group().split("'", 2)[1].split()]
    except Exception as exc:
        raise ValueError("invalid time sequence decimals") from exc
    if (not end_ns.is_finite() or end_ns != end_ns.to_integral_value()
            or end_ns < 1 or end_ns > MAX_TIME_NS or len(seq_ns) < 2
            or seq_ns[0] != 0 or seq_ns[-1] != end_ns
            or any(not t.is_finite() for t in seq_ns)
            or any(b <= a for a, b in zip(seq_ns, seq_ns[1:]))):
        raise ValueError("invalid time grid, endpoint or time ordering")
    return int(end_ns), seq_ns


def extend_requested_event_targets(prior: list[Decimal],
                                    start: int, end: int,
                                    interval_ns: str) -> list[Decimal]:
    """Carry prior declared time targets unchanged and append future targets.

    The adaptive native solver may substep; these are audit/monitor targets,
    not a serialized TimeSequenceStepper state or a fabricated checkpoint.
    """
    if not prior or prior[0] != 0 or prior[-1] != start:
        raise ValueError("requested target prefix does not match checkpoint")
    try:
        step = Decimal(str(interval_ns))
    except Exception as exc:
        raise ValueError("unparseable requested time interval") from exc
    if not step.is_finite() or step < Decimal("0.001"):
        raise ValueError("requested interval below verified 1 ps floor")
    count = int((Decimal(end - start) / step).to_integral_value(
        rounding=ROUND_CEILING))
    if not 1 <= start < end <= MAX_TIME_NS or count < 1 or len(prior) + count > MAX_SEQUENCE_EVENTS:
        raise ValueError("requested time target bounds exceeded")
    result = list(prior)
    for i in range(1, count + 1):
        t = min(Decimal(start) + i * step, Decimal(end))
        if t > result[-1]:
            result.append(t)
    if result[-1] != end or any(b <= a for a, b in zip(result, result[1:])):
        raise ValueError("invalid chained requested time targets")
    return result


def extend_input(text: str, start: int, end: int,
                 interval_ns: str = "1") -> str:
    """Append configurable physical output/event times; NEVER change past grid."""
    outputs = list(OUTPUT_RE.finditer(text))
    if len(outputs) != 1 or len(re.findall(
            r"(?m)^[ \t]*checkpoint[ \t]*=[ \t]*true[ \t]*$",
            outputs[0].group("body"))) != 1:
        raise ValueError("missing, disabled or ambiguous native checkpoint output")
    # On successive native advanced stages the archived input has the
    # IterationAdaptiveDT policy, not a TimeSequenceStepper/time_sequence.
    if "type = IterationAdaptiveDT" in text:
        blocks = list(EXEC_RE.finditer(text))
        if len(blocks) != 1 or "type = TimeSequenceStepper" in text:
            raise ValueError("ambiguous chained advanced restart Executioner")
        block = blocks[0]
        body = block.group("body")
        ends = list(END_RE.finditer(body))
        if len(ends) != 1:
            raise ValueError("invalid chained advanced restart end_time")
        previous = (Decimal(ends[0].group().split("=", 1)[1].strip()) /
                    NS_S).quantize(Decimal("0.00000001"))
        if not 1 <= start < end <= MAX_TIME_NS or previous != start:
            raise ValueError("chained restart endpoint does not match accepted upstream")
        adaptive_timestep_interval = Decimal(str(interval_ns))
        if not adaptive_timestep_interval.is_finite() or adaptive_timestep_interval < Decimal("0.001"):
            raise ValueError("invalid chained adaptive restart time interval")
        new_body = END_RE.sub(lambda m: m.group(1) + format(
            Decimal(end) * NS_S, ".17g"), body, count=1)
        result = text[:block.start("body")] + new_body + text[block.end("body"):]
        return result
    original_end, prior = time_grid(text)
    if not 1 <= start < end <= MAX_TIME_NS or original_end != start:
        raise ValueError("wrong start checkpoint or end time")
    try:
        step = Decimal(str(interval_ns))
    except Exception as exc:
        raise ValueError("unparseable interval_ns") from exc
    if not step.is_finite() or step <= 0:
        raise ValueError("interval_ns must be finite and strictly positive")
    count = int((Decimal(end - start) / step).to_integral_value(
        rounding=ROUND_CEILING))
    if count < 1 or count + len(prior) > MAX_SEQUENCE_EVENTS:
        raise ValueError("time sequence exceeds bounded event budget")
    sequence = list(prior)
    for i in range(1, count + 1):
        current = min(Decimal(start) + i * step, Decimal(end))
        if current > sequence[-1]:
            sequence.append(current)
    if sequence[-1] != end:
        raise ValueError("time grid did not reach requested end")
    match = next(EXEC_RE.finditer(text))
    body = match.group("body")
    def seconds(t):
        return format(t * NS_S, ".17g")
    body = END_RE.sub(lambda m: m.group(1) + seconds(Decimal(end)), body, count=1)
    grid = " ".join(seconds(t) for t in sequence)
    body = SEQ_RE.sub(lambda m: m.group(1) + "'" + grid + "'", body, count=1)
    result = text[:match.start("body")] + body + text[match.end("body"):]
    if time_grid(result) != (end, sequence):
        raise ValueError("extended time grid did not round-trip")
    return result



# MOOSE 9f388366 TimeSequenceStepperBase::setupSequence validates input
# times[j] against serialized saved_time_sequence[j] through _current_step
# inclusive. The genuine 1ns recover to 2ns checkpoint at native step 4 has
# a repeated 1ns event in its serialized prefix, while native CSV only
# records accepted distinct times [0,1,1.001,1.002,2]ns. A microscopic
# strictly increasing proxy of the repeated 1ns event is allowed by MOOSE
# absoluteFuzzyEqual, without modifying the genuine checkpoint.
LEGACY_2NS_HISTORY_NS = tuple(map(Decimal, (
    "0", "1", "1.001", "1.002", "2"
)))
LEGACY_DUPLICATE_PROXY_NS = Decimal("1.00000001")
LEGACY_SAVED_PREFIX_NS = tuple(map(Decimal, (
    "0", "1", "1", "1.001", "1.002"
)))
CHECKPOINT_PREFIX_ABS_TOL_NS = Decimal("0.00000002")

def compatible_upstream_2ns_sequence(text: str, manifest: dict,
                                     csv_rows: list[dict[str, str]]) -> str:
    """Stage the exact known 2ns legacy checkpoint time-history overlay.

    Old source input [0,1,2]ns differs from stored TimeSequenceStepper
    current_step=4: [0,1,1,1.001,1.002]ns (native restart error + two
    independently verified cross-CI time traces). Never guess other histories.
    """
    if (manifest.get("schema") != 2 or
            manifest.get("actual_moose_step") != 4 or
            manifest.get("source_sha") !=
            "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab" or
            manifest.get("restart_mode") == "advanced_restart_not_recover" or
            time_grid(text) != (2, [Decimal(0), Decimal(1), Decimal(2)])):
        raise ValueError("unverified 2ns legacy checkpoint TimeStepper identity")
    history = [Decimal(r["time"]) / NS_S for r in csv_rows]
    if len(history) != 5 or any(abs(x - y) > CHECKPOINT_PREFIX_ABS_TOL_NS
                                for x, y in zip(history, LEGACY_2NS_HISTORY_NS)):
        raise ValueError("2ns native accepted time history differs from evidenced checkpoint")
    # Native new time targets must be strictly increasing, although the
    # serialized sequence has an exact duplicate at 1ns. The 1e-17s proxy
    # is far below MooseUtils::absoluteFuzzyEqual default 1e-12s tolerance.
    # Real MOOSE P3 remains authoritative for this compatibility claim.
    candidate = [Decimal(0), Decimal(1), LEGACY_DUPLICATE_PROXY_NS,
                 Decimal("1.001"), Decimal("1.002"), Decimal(2)]
    if not all(a < b for a, b in zip(candidate, candidate[1:])):
        raise ValueError("nonmonotonic checkpoint-compatible prefix")
    for offered, saved in zip(candidate, LEGACY_SAVED_PREFIX_NS):
        if abs(offered - saved) > CHECKPOINT_PREFIX_ABS_TOL_NS:
            raise ValueError("checkpoint stored prefix not fuzzy-compatible")
    match = next(EXEC_RE.finditer(text))
    body = match.group("body")
    raw = " ".join(format(x * NS_S, ".17g") for x in candidate)
    body = SEQ_RE.sub(lambda m: m.group(1) + "'" + raw + "'", body, count=1)
    staged = text[:match.start("body")] + body + text[match.end("body"):]
    if time_grid(staged) != (2, candidate):
        raise ValueError("checkpoint-compatible 2ns staged sequence did not round-trip")
    return staged

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

def suppress_parent_restart_ics(text: str, already_staged: bool = False) -> str:
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
    if (not already_staged and (set(configured) != EXPECTED_IC_VARIABLES or
            len(configured) != len(EXPECTED_IC_VARIABLES))):
        raise ValueError("unexpected parent IC inventory: " + repr(sorted(configured)))
    if already_staged:
        if configured or INLINE_IC_RE.search(text):
            raise ValueError("a continued restart input unexpectedly acquired initial conditions")
        return text
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
    r"(?ms)^  \[maxwell_t6\][ \t]*\n(?P<body>.*?)^  \[\][ \t]*$"
)
NO_RESTORE_TRUE_RE = re.compile(r"(?m)^(?P<indent>[ \t]+)no_restore[ \t]*=[ \t]*true[ \t]*$")
NO_RESTORE_ANY_RE = re.compile(r"(?m)^[ \t]+no_restore[ \t]*=[^\n]*$")

def stage_parent_multiapp_restart_overlay(text: str, already_staged: bool = False) -> str:
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
    if already_staged:
        if len(re.findall(r"(?m)^[ \t]+no_restore[ \t]*=[ \t]*false[ \t]*$", body)) != 1:
            raise ValueError("continued advanced restart has no_restore mismatch")
        return text
    changed, count = NO_RESTORE_TRUE_RE.subn(
        lambda m: m.group("indent") + "no_restore = false", body)
    if count != 1:
        raise ValueError("expected exactly one no_restore=true in Maxwell MultiApp")
    return text[:b.start("body")] + changed + text[b.end("body"):]



# Both archived 400W/1000W Maxwell child overlays contain exactly these
# three AuxVariables seed defaults, which advanced MultiApp restart must NOT run.
CHILD_RESTART_SEEDS = frozenset((
    "electron_density_state_t6", "mean_energy_state_t6", "pressure_state_t6"
))
CHILD_AUX_RE = re.compile(r"(?ms)^\[AuxVariables\][ \t]*\n(?P<body>.*?)^\[\][ \t]*$")
CHILD_AUX_VAR_RE = re.compile(
    r"(?ms)^  \[(?P<name>[A-Za-z_][A-Za-z_0-9]*)\][ \t]*\n(?P<body>.*?)^  \[\][ \t]*$"
)

def stage_child_maxwell_restart_overlay(text: str,
                                        already_staged: bool = False) -> str:
    """Restore native Maxwell AuxVariables state without re-applying 3 seeds."""
    if re.search(r"(?m)^\[ICs\][ \t]*$", text):
        raise ValueError("unreviewed explicit child ICs")
    blocks = list(CHILD_AUX_RE.finditer(text))
    if len(blocks) != 1:
        raise ValueError("missing/nonunique Maxwell child AuxVariables block")
    block = blocks[0]
    body = block.group("body")
    names = []
    for var in CHILD_AUX_VAR_RE.finditer(body):
        count = len(INLINE_IC_RE.findall(var.group("body")))
        if count > 1:
            raise ValueError("duplicate child seed")
        if count:
            names.append(var.group("name"))
    if already_staged:
        if names or INLINE_IC_RE.search(text):
            raise ValueError("continued Maxwell restart retained seed ICs")
        return text
    if set(names) != CHILD_RESTART_SEEDS or len(names) != 3:
        raise ValueError("unrecognized Maxwell child initial state inventory")
    cleaned, removed = INLINE_IC_RE.subn("", body)
    if removed != 3:
        raise ValueError("unmapped Maxwell child seed")
    result = text[:block.start("body")] + cleaned + text[block.end("body"):]
    if INLINE_IC_RE.search(result):
        raise ValueError("unreviewed extra Maxwell initial_condition")
    return result

def strip_previous_restart_problem(text: str, previous_prefix: str) -> str:
    """Validated removal of the previous stage's restart binding only."""
    marker = "\n[Problem]\n  restart_file_base = '/workspace/" + previous_prefix + "'\n[]"
    if text.rstrip().count(marker) != 1 or not text.rstrip().endswith(marker):
        raise ValueError("previous-stage restart base changed or ambiguous")
    return text.rstrip()[:-len(marker)].rstrip() + "\n"

def advanced_restart_input(text: str, prefix: str,
                           prior_restart_prefix: str | None = None) -> str:
    """MOOSE 9f388366: recover ignores an extended TimeSequenceStepper sequence.
    
    Problem/restart_file_base activates the genuine advanced *restart* path,
    which checks the saved sequence prefix and appends new future times.
    Keep the original deterministic mesh generator and all MultiApps.
    """
    if prior_restart_prefix is None and re.search(r"(?m)^\[Problem\]\s*$", text):
        raise ValueError("unexpected existing Problem block")
    if not re.fullmatch(
        r"experiments/Issue395_powered_chemistry_ladder/"
        r"results_rf_elastic_diss_ion_ei20_ei01_(400|1000)w_"
        r"adjacent_sheath_wall_closed_100us_dt1000ns/run/"
        r"plasma(?:_restart_\d+to\d+)?_cp/\d{4,}", prefix
    ):
        raise ValueError("invalid exact restart checkpoint prefix")
    if prior_restart_prefix is not None:
        text = strip_previous_restart_problem(text, prior_restart_prefix)
    cleaned = suppress_parent_restart_ics(text, already_staged=prior_restart_prefix is not None)
    # MOOSE resolves a relative restart base against the *input file folder*;
    # the manifest prefix is repository-root-relative. Use the fixed container
    # workspace root to avoid duplicating experiments/Issue395 in the path.
    return cleaned.rstrip() + "\n\n[Problem]\n  restart_file_base = '/workspace/" + prefix + "'\n[]\n"


def stage_base(start: int, end: int) -> str:
    if not 1 <= start < end <= MAX_TIME_NS:
        raise ValueError("invalid bounded stage")
    return f"plasma_restart_{start}to{end}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))

def verify_csv(path: Path, end: int, exact_rows: bool,
               expected_times: list[float] | None = None) -> list[dict[str, str]]:
    rows = read_csv(path)
    if not rows:
        raise ValueError("empty native CSV")
    times = [float(row["time"]) for row in rows]
    if any(not math.isfinite(t) for t in times):
        raise ValueError("nonfinite CSV time")
    if not math.isclose(times[-1], end * 1e-9, rel_tol=1e-12, abs_tol=1e-16):
        raise ValueError(f"wrong endpoint {times[-1]} vs {end} ns")
    if exact_rows:
        if not math.isclose(times[0], 0, rel_tol=0, abs_tol=1e-16) or any(
                b <= a for a, b in zip(times, times[1:])):
            raise ValueError("upstream native CSV history not time ordered")
        boundary = expected_times if expected_times is not None else [
            i * 1e-9 for i in range(end + 1)]
        k = 0
        for target in boundary:
            while k < len(times) and times[k] < target and not math.isclose(
                    times[k], target, rel_tol=1e-12, abs_tol=1e-16):
                k += 1
            if k == len(times) or not math.isclose(
                    times[k], target, rel_tol=1e-12, abs_tol=1e-16):
                raise ValueError(f"upstream CSV missing time-grid boundary {target}")
    for key in ("n_O_ex_avg", "n_O_3P_avg", "chem24_monitor_R_936",
                "P_rf_raw_W_t6", "chem24_monitor_S_charge_closure_chem24",
                "chem24_monitor_S_mass_closure_chem24"):
        if key not in rows[-1] or not math.isfinite(float(rows[-1][key])):
            raise ValueError(f"nonfinite/missing chemistry monitor {key}")
    return rows

def result_path(power: int) -> Path:
    return CHEM / f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"

def restore(root: Path, artifact: Path, power: int, start: int, end: int,
            source_sha: str, interval_ns: str = "1") -> None:
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
    # Legacy schema2 had native sequence targets; schema4 adaptive stages
    # record requested monitor targets, not guaranteed exact solver steps.
    required_native_times = (
        manifest["time_sequence_s"] if manifest.get("schema") in (2, 5)
        else [0.0, start * 1e-9])
    rows_before = verify_csv(run / "plasma.csv", start, exact_rows=True,
                             expected_times=required_native_times)
    # Checkpoint prefixes are native MOOSE step IDs, not physical nanoseconds.
    # A recovered 2 ns run may end at step 7 after 1 ps substeps.
    actual_step = manifest.get("actual_moose_step")
    # Actual MOOSE timestep numbers must never be equated with nanoseconds:
    # later stages request 10/100/1000/10000ns targets and may have far
    # fewer actual native steps than the numeric start_ns value.
    if type(actual_step) is not int or actual_step < 1:
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
    previous_mode = manifest.get("restart_mode") == "advanced_restart_not_recover"
    prior_source = manifest.get("restart_source_prefix") if previous_mode else None
    if previous_mode and not isinstance(prior_source, str):
        raise ValueError("missing prior-stage restart source prefix")
    prior_input = inp.read_text()
    if start == 2 and not previous_mode:
        prior_input = compatible_upstream_2ns_sequence(
            prior_input, manifest, rows_before)
    elif start == 100 and manifest.get("schema") == 5 and not previous_mode:
        # The proven initial-run schema5 checkpoint is native and fresh
        # (not recover); stage2 is the first advanced restart and will
        # replace TimeSequenceStepper only in the staged input.
        grid_end, grid = time_grid(prior_input)
        if grid_end != 100 or len(grid) != 101 or grid != list(map(Decimal, range(101))):
            raise ValueError("first-stage 100ns native grid is not the 100 exact 1ns targets")
        if manifest.get("five_stage_chain", {}).get("stage") != 1:
            raise ValueError("first-stage provenance not attested")
    elif not previous_mode:
        raise ValueError("unknown native checkpoint TimeStepper history")
    staged_time = extend_input(prior_input, start, end, interval_ns)
    if start == 100 and manifest.get("schema") == 5:
        requested_targets = extend_requested_event_targets(
            [((Decimal(str(v)) / NS_S).quantize(Decimal("0.00000001"))) for v in manifest["time_sequence_s"]],
            start, end, interval_ns)
    if previous_mode:
        previous_overlay_path = root / result / "restart_time_sequence_overlay.json"
        if not previous_overlay_path.is_file():
            raise ValueError("missing prior-stage native restart timing audit")
        previous_overlay = json.loads(previous_overlay_path.read_text())
        if (previous_overlay.get("native_timestepper") != "IterationAdaptiveDT" or
                previous_overlay.get("end_ns") != start or
                previous_overlay.get("upstream_source_sha") != source_sha or
                previous_overlay.get("from_checkpoint") != prior_source):
            raise ValueError("previous-stage adaptive time provenance mismatch")
        prior_requested = [Decimal(v) for v in
                           previous_overlay["staged_time_sequence_ns"]]
        requested_targets = extend_requested_event_targets(
            prior_requested, start, end, interval_ns)
    elif not (start == 100 and manifest.get("schema") == 5):
        requested_targets = time_grid(staged_time)[1]
    staged_native = stage_adaptive_stepper(
        staged_time, interval_ns, already_staged=previous_mode)
    inp.write_text(advanced_restart_input(
        staged_native, expected_prefix, prior_restart_prefix=prior_source))
    (root / result / "restart_time_sequence_overlay.json").write_text(
        json.dumps({
            "schema": 1, "from_checkpoint": expected_prefix,
            "upstream_actual_moose_step": actual_step,
            "upstream_source_sha": source_sha,
            "start_ns": start, "end_ns": end,
            "requested_interval_ns": interval_ns,
            "staged_time_sequence_ns": [str(t) for t in requested_targets],
            "native_timestepper": "IterationAdaptiveDT",
            "native_timestepper_reset_dt": True,
            "native_dt_initial_s": 1e-12,
            "native_dtmax_s": float(Decimal(str(interval_ns)) * NS_S),
            "legacy_duplicate_checkpoint_boundary_proxy": (
                "1.00000001 ns; represents native serialized 1ns duplicate; "
                "P3 native proof required" if
                start == 2 and not previous_mode else None),
            "state_source": "verified native checkpoint, never CSV reconstruction",
        }, indent=2, sort_keys=True) + "\n")
    parent_overlay = root / CHEM / f"rf_elastic_multiapp_parent_{power}w_100us_dt1000ns_overlay.i"
    parent_overlay.write_text(stage_parent_multiapp_restart_overlay(
        parent_overlay.read_text(), already_staged=previous_mode))
    child_overlay = root / CHEM / f"rf_elastic_multiapp_maxwell_{power}w_100us_dt1000ns_overlay.i"
    child_overlay.write_text(stage_child_maxwell_restart_overlay(
        child_overlay.read_text(), already_staged=previous_mode))
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

# Source-backed temporal semantics: build_t6_overlays.py freezes plasma
# RF auxiliary state on INITIAL/TIMESTEP_BEGIN, while these five RF
# postprocessors execute on INITIAL/TIMESTEP_END. The preceding END row
# reflects the preceding step's frozen state; advanced restart INITIAL
# re-freezes the restored parent at the checkpoint time. These are
# re-evaluated diagnostics, not serialized state continuity monitors.
RF_REINITIALIZED_MONITORS = frozenset((
    "P_rf_raw_W_t6", "P_rf_scaled_W_t6", "S_rf_eV_mol_s_t6",
    "mean_energy_rf_state_min_t6", "mean_energy_rf_state_max_t6",
))

def verify_boundary_monitors(old: dict, new: dict) -> dict:
    """Preserve every checkpointed monitor; audit reinitialized RF separately.

    Never skip a new/unknown monitor, a plasma/Maxwell continuity failure,
    a nonfinite diagnostic, or a changed RF source/scale identity.
    """
    if list(old) != list(new) or not RF_REINITIALIZED_MONITORS.issubset(old):
        raise ValueError("restart monitor schema or known RF diagnostic inventory changed")
    changed = {}
    for key in old:
        a, b = float(old[key]), float(new[key])
        if not (math.isfinite(a) and math.isfinite(b)):
            raise ValueError(f"nonfinite restart boundary monitor: {key}")
        if key in RF_REINITIALIZED_MONITORS:
            if not math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-12):
                changed[key] = {"upstream": a, "reinitialized": b}
        elif not math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError(f"restart boundary state discontinuity: {key} {a} -> {b}")
    for row in (old, new):
        raw = float(row["P_rf_raw_W_t6"])
        scaled = float(row["P_rf_scaled_W_t6"])
        source = float(row["S_rf_eV_mol_s_t6"])
        e_min = float(row["mean_energy_rf_state_min_t6"])
        e_max = float(row["mean_energy_rf_state_max_t6"])
        if not (raw > 0 and scaled > 0 and source > 0 and
                0 < e_min <= e_max):
            raise ValueError("nonphysical restart RF diagnostic sign or energy extrema")
    for num, den in (("P_rf_scaled_W_t6", "P_rf_raw_W_t6"),
                     ("S_rf_eV_mol_s_t6", "P_rf_scaled_W_t6")):
        old_ratio = float(old[num]) / float(old[den])
        new_ratio = float(new[num]) / float(new[den])
        if not math.isclose(old_ratio, new_ratio, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError(f"RF source/scale identity changed at restart: {num}/{den}")
    return changed

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
    boundary_rf_reinitialized = verify_boundary_monitors(before[-1], after[0])
    print("OXYGEN25_RESTART_BOUNDARY_STATE_MONITORS_PASS",
          len(before[-1]) - len(RF_REINITIALIZED_MONITORS),
          "RF_REINITIALIZED", sorted(boundary_rf_reinitialized))
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
    time_overlay_path = root / result / "restart_time_sequence_overlay.json"
    if not time_overlay_path.is_file() or not time_overlay_path.stat().st_size:
        raise ValueError("missing staged TimeStepper checkpoint compatibility evidence")
    time_overlay = json.loads(time_overlay_path.read_text())
    if (time_overlay["from_checkpoint"] != old_prefix or
            time_overlay["start_ns"] != start or
            time_overlay["end_ns"] != end or
            time_overlay["upstream_actual_moose_step"] != upstream["actual_moose_step"] or
            time_overlay["native_timestepper"] != "IterationAdaptiveDT" or
            "type = IterationAdaptiveDT" not in inp or
            "    reset_dt = true" not in inp or
            "type = TimeSequenceStepper" in inp):
        raise ValueError("staged TimeStepper compatibility evidence changed")
    input_files = [root / row["path"] for row in upstream["input_files"]]
    if time_overlay_path not in input_files:
        input_files.append(time_overlay_path)
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
        "schema": 4, "power_w": power, "source_sha": source_sha,
        "final_time_s": end * 1e-9,
        "time_sequence_s": [float(Decimal(t) * NS_S) for t in time_overlay["staged_time_sequence_ns"]],
        "restart_source_prefix": old_prefix,
        "staged_time_sequence_overlay_sha256": sha(time_overlay_path),
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
        "restart_boundary_preserved_monitor_count":
            len(before[-1]) - len(RF_REINITIALIZED_MONITORS),
        "restart_boundary_rf_diagnostics_reinitialized": boundary_rf_reinitialized,
        "scientific_acceptance": "HOLD",
    }
    (root / result / f"restart_{end}ns_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    print("OXYGEN25_GENUINE_CROSS_RUN_ADVANCED_RESTART_PASS", power, start, end, len(after))


def self_test() -> None:
    # Source-backed RF freeze/END epoch mismatch: exact 145-state-monitor
    # continuity is mandatory, but the five INITIAL-refreshed RF diagnostics
    # are compared by source/scale identity rather than stale END equality.
    old_boundary = {
        "time": "2e-9", "n_O_3P_avg": "3.22e15",
        "P_abs_maxwell_t6": "198.5",
        "P_rf_raw_W_t6": "201", "P_rf_scaled_W_t6": "201",
        "S_rf_eV_mol_s_t6": str(201 / 96485.33212),
        "mean_energy_rf_state_min_t6": "3.86",
        "mean_energy_rf_state_max_t6": "4.73",
    }
    new_boundary = dict(old_boundary,
        P_rf_raw_W_t6="203", P_rf_scaled_W_t6="203",
        S_rf_eV_mol_s_t6=str(203 / 96485.33212),
        mean_energy_rf_state_min_t6="3.82",
        mean_energy_rf_state_max_t6="4.96")
    assert set(verify_boundary_monitors(old_boundary, new_boundary)) == RF_REINITIALIZED_MONITORS
    for key, bad_value in (
            ("n_O_3P_avg", "4e15"),
            ("P_abs_maxwell_t6", "250"),
            ("P_rf_scaled_W_t6", "250"),
            ("mean_energy_rf_state_min_t6", "-1")):
        corrupted = dict(new_boundary, **{key: bad_value})
        try:
            verify_boundary_monitors(old_boundary, corrupted)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid restart boundary monitor accepted: {key}")
    sample = ("[Executioner]\n  type = Transient\n  end_time = 1e-9\n"
              "  [TimeStepper]\n    type = TimeSequenceStepper\n"
              "    time_sequence = '0 1e-9'\n  []\n[]\n"
              "[Outputs]\n  checkpoint = true\n[]\n")
    assert time_grid(extend_input(sample, 1, 2)) == (2, [0, 1, 2])
    assert time_grid(extend_input(sample, 1, 100)) == (100, list(range(101)))
    legacy_input = extend_input(sample, 1, 2)
    legacy_manifest = {
        "schema": 2, "actual_moose_step": 4,
        "source_sha": "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab",
    }
    accepted_rows = [
        {"time": format(t * NS_S, ".17g")}
        for t in LEGACY_2NS_HISTORY_NS
    ]
    aligned = compatible_upstream_2ns_sequence(
        legacy_input, legacy_manifest, accepted_rows)
    assert time_grid(aligned)[1][:6] == [
        Decimal(0), Decimal(1), LEGACY_DUPLICATE_PROXY_NS,
        Decimal("1.001"), Decimal("1.002"), Decimal(2)
    ]
    extended = extend_input(aligned, 2, 100, "1")
    assert time_grid(extended)[1][2:6] == [
        LEGACY_DUPLICATE_PROXY_NS, Decimal("1.001"), Decimal("1.002"), Decimal(2)
    ]
    assert time_grid(extended)[1][-1] == 100
    adaptive = stage_adaptive_stepper(extended, "1")
    assert "type = IterationAdaptiveDT" in adaptive
    assert "    reset_dt = true" in adaptive
    chain_stage = extend_input(adaptive, 100, 1000, "10")
    assert "end_time = 0.000001" in chain_stage
    chained = stage_adaptive_stepper(chain_stage, "10", already_staged=True)
    assert "    reset_dt = true" in chained
    assert "  dtmax = 1e-8" in chained
    proposed = extend_requested_event_targets(
        time_grid(extended)[1], 100, 1000, "10")
    assert proposed[-1] == 1000
    assert len(proposed) == len(time_grid(extended)[1]) + 90
    try:
        extend_requested_event_targets([Decimal(0), Decimal(99)], 100, 1000, "10")
    except ValueError:
        pass
    else:
        raise AssertionError("bad chained checkpoint event prefix accepted")
    assert "time_sequence =" not in adaptive
    assert "  dtmax = 1e-9" in adaptive
    assert "    dt = 1e-12" in adaptive
    assert stage_adaptive_stepper(adaptive, "1", already_staged=True) == adaptive
    for bad in ("0", "NaN", "-1", "0.0001"):
        try:
            stage_adaptive_stepper(extended, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe adaptive timestep accepted")
    try:
        stage_adaptive_stepper(extended.replace(
            "type = TimeSequenceStepper", "type = ConstantDT"), "1")
    except ValueError:
        pass
    else:
        raise AssertionError("unrecognized native timestepper accepted")
    for corrupt in (dict(legacy_manifest, actual_moose_step=3),
                    dict(legacy_manifest, source_sha="0"*40)):
        try:
            compatible_upstream_2ns_sequence(
                legacy_input, corrupt, accepted_rows)
        except ValueError:
            pass
        else:
            raise AssertionError("unknown checkpoint sequence accepted")
    mutated_rows = [dict(row) for row in accepted_rows]
    mutated_rows[3]["time"] = "1.5e-9"
    try:
        compatible_upstream_2ns_sequence(
            legacy_input, legacy_manifest, mutated_rows)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched native history accepted")
    variable = extend_input(sample, 1, 100, "2.5")
    assert time_grid(variable)[1][-3:] == [Decimal("96"), Decimal("98.5"), Decimal("100")]
    for invalid in ("0", "-1", "NaN", "1e-30"):
        try:
            extend_input(sample, 1, 100, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid time interval accepted")
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
    assert stage_parent_multiapp_restart_overlay(staged, already_staged=True) == staged
    child = ("[AuxVariables]\n" +
             "".join("  [" + name + "]\n    initial_condition = 1\n  []\n"
                     for name in sorted(CHILD_RESTART_SEEDS)) + "[]\n")
    clean_child = stage_child_maxwell_restart_overlay(child)
    assert "initial_condition" not in clean_child
    assert stage_child_maxwell_restart_overlay(clean_child, already_staged=True) == clean_child
    for bad in (child.replace("pressure_state_t6", "unreviewed_state", 1),
                child.replace("initial_condition = 1", "initial_condition = 1\n    initial_condition = 2", 1)):
        try:
            stage_child_maxwell_restart_overlay(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid Maxwell child IC inventory accepted")
    old_staged = advanced_restart_input(extend_input(seeded, 1, 2), prefix)
    again = advanced_restart_input(extend_input(old_staged, 2, 100), prefix,
                                   prior_restart_prefix=prefix)
    assert again.count("[Problem]") == 1
    assert time_grid(again) == (100, list(range(101)))
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
    parser.add_argument("--interval-ns", default="1", help="positive decimal ns spacing of requested time_sequence targets")
    parser.add_argument("--source-sha")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if None in (args.power_w, args.start_ns, args.end_ns, args.source_sha):
        parser.error("--power-w, --start-ns, --end-ns, --source-sha required")
    root = args.root.resolve()
    if args.restore:
        restore(root, args.restore, args.power_w, args.start_ns, args.end_ns, args.source_sha, args.interval_ns)
    elif args.verify_rates:
        verify_rates(root, args.power_w, args.verify_rates)
    else:
        verify_recovery(root, args.power_w, args.start_ns, args.end_ns, args.source_sha)

if __name__ == "__main__":
    main()
