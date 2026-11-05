#!/usr/bin/env python3
"""Issue #395: one native 14-channel BASE restart from actual 100us -> 300us.

Source: exact CI run 42049066748 (400/1000 W, complete native archive).
No chemistry, RF, mesh, EEDF, inlet or upstream-checkpoint reconstruction.
Science acceptance remains HOLD. Never archive a private rate table.
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

ROOT = Path.cwd()
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
RECORD = Path("_base_record") / CHEM / "research_baselines/current_reaction_base.json"
LIBRARY = Path("_restart_library/.github/scripts/oxygen25_restart_chain.py")
SOURCE_SHA = "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
HARNESS_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
RECORD_SHA = "bc1193d3d86ceed929031e28ee832bef8ae2a43a"
UPSTREAM_RUN = 42049066748
START_NS = 100000
END_NS = 300000
CAP_NS = 1000
RUN_STEM = "plasma_restart_100000to300000"
REQUIRED_CHANNELS = (
    "EI-401", "EI-02", "EI-412", "EI-415", "EI-17", "EI-941",
    "EI-2738", "EI-407", "EI-417", "EI-935", "H24", "H25",
    "H23", "EI-2069",
)
PRIVATE_RATES = {
    "EI-401": "EI-401_O2_X.txt",
    "EI-412": "EI-412_O2_X.txt",
    "EI-415": "EI-415_O2_X.txt",
    "EI-941": "EI-941_O_3P.txt",
    "EI-2069": "EI-2069_O2_a1Delta.txt",
    "EI-407": "EI-407_O2_X.txt",
    "EI-417": "EI-417_O2_X.txt",
    "EI-935": "EI-935_O_3P.txt",
}

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load_json(path: Path) -> dict:
    require(path.is_file(), "missing JSON: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"))

def library():
    spec = importlib.util.spec_from_file_location("pinned_native_restart_library", LIBRARY)
    require(spec is not None and spec.loader is not None, "missing pinned native restart adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def paths(power: int):
    require(power in (400, 1000), "unsupported power")
    tag = f"{power}w_100us_dt1000ns"
    result = CHEM / f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"
    root = CHEM / f"rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"
    parent = CHEM / f"rf_elastic_multiapp_parent_{tag}_overlay.i"
    child = CHEM / f"rf_elastic_multiapp_maxwell_{tag}_overlay.i"
    arg_files = [
        root, parent, CHEM / f"o2_elastic_{tag}_overlay.i",
        CHEM / f"o2_dissociation_ei412_{tag}_overlay.i",
        CHEM / f"o2_ionization_ei415_{tag}_overlay.i",
        CHEM / f"o_ionization_ei941_{tag}_overlay.i",
        CHEM / f"o2_attachment_ei401_{tag}_overlay.i",
        CHEM / f"o_elastic_ei17_{tag}_overlay.i",
        CHEM / f"ei2738_detachment_formula_{tag}_overlay.i",
        CHEM / f"ei407_only_{tag}_overlay.i",
        CHEM / f"ei417_without_h05_{tag}_overlay.i",
        CHEM / f"ei935_atomic_excitation_{tag}_overlay.i",
        CHEM / f"h24_om_o2p_mutual_neutralization_{tag}_overlay.i",
        CHEM / f"h25_op_o2_charge_transfer_{tag}_overlay.i",
        CHEM / f"h23_op_om_mutual_neutralization_{tag}_overlay.i",
        CHEM / f"ei2069_o2a_dissociation_{tag}_overlay.i",
    ]
    return result, root, parent, child, arg_files

def load_record(power: int) -> dict:
    b = load_json(RECORD)
    require(b["base_id"] == "oxygen-icp-h23-ei941-ei412-ei401-ei415-14ch-20261105", "wrong BASE")
    require(b["acceptance"] == "SCIENCE_HOLD", "BASE scientific status drift")
    require(b["source"]["immutable_verified_harness_sha"] == HARNESS_SHA, "BASE harness SHA drift")
    require(b["source"]["physics_app_pinned_sha"] == SOURCE_SHA, "production physics SHA drift")
    require(b["authority_boundary"]["chosen_run_id"] == UPSTREAM_RUN, "wrong upstream run")
    require(tuple(b["chemistry"]["active_channels"]) == REQUIRED_CHANNELS, "reaction set drift")
    require(b["operating_conditions"]["power_W"] == [400, 1000], "power matrix drift")
    require(b["verified_runs"][f"{power}W"]["run_id"] == UPSTREAM_RUN, "run ID drift")
    require(b["verified_runs"][f"{power}W"]["native_P0_P4_pass"] is True, "upstream not native verified")
    require(b["verified_runs"][f"{power}W"]["verified_endpoint_s"] == 1e-4, "upstream endpoint")
    return b

def upstream_files(power: int):
    folder = Path("_upstream_artifact") / f"{power}W"
    names = list(folder.rglob("legacy6_restart_100000ns_manifest.json"))
    require(len(names) == 1, "missing/ambiguous original 100us manifest")
    return folder, names[0]

def stage(power: int) -> None:
    b = load_record(power)
    upstream_dir, manifest_path = upstream_files(power)
    m = load_json(manifest_path)
    proof = b["verified_runs"][f"{power}W"]
    require(m["power_W"] == power, "wrong power in checkpoint manifest")
    require(m["native_endpoint_s"] == 1e-4, "upstream native endpoint not 100us")
    require(m["actual_moose_step"] == proof["native_steps"], "upstream actual native step drift")
    require(m["verified_full_native_100us_checkpoint"] is True, "unverified native source checkpoint")
    require(m["scientific_acceptance"] == "HOLD", "upstream science state invalid")
    require(m["variant"] == "H23_NO943_MCS2738_EI2069_EI941_EI412_EI401_EI415_REPLACES_EI16_14CH_HOLD", "wrong upstream 14ch variant")
    require(tuple(m["chemistry_channels"]) == REQUIRED_CHANNELS, "upstream chemistry changed")
    require(m["transport_table_sha256"] == b["source"]["fixed_initial_eedf_sha256"], "upstream EEDF changed")
    for key in ("ei16_replaced_not_parallel", "ei01_replaced_not_parallel",
                "dissg_replaced_not_parallel", "ei20_replaced_not_parallel"):
        require(m.get(key) is True, "exclusive replacement lost: " + key)
    for kind in ("run", "inputs"):
        member = m["archives"][kind]
        artifact = list(upstream_dir.rglob(member["name"]))
        require(len(artifact) == 1, "missing/ambiguous original tarball " + kind)
        require(member["sha256"] == proof[f"native_{'run' if kind == 'run' else 'inputs'}_archive_sha256"],
                "original BASE tarball SHA does not match pinned research record")
        require(artifact[0].stat().st_size == member["bytes"], "archive byte size drift")
        lib = library()
        lib.extract_checked(artifact[0], member["sha256"], m["inventory"][kind], ROOT)
    result, inp, parent, child, args = paths(power)
    prefix = m["native_checkpoint_prefix"]
    require(prefix == (result / "run/plasma_cp" / f"{m['actual_moose_step']:04d}").as_posix(),
            "upstream checkpoint prefix does not match exact native step")
    require((ROOT / prefix).resolve().is_relative_to((ROOT / result / "run").resolve()),
            "unsafe native checkpoint prefix")
    for suffix in ("-restart-0.rd/data", "-restart-0.rd/header", "-mesh.cpa.gz/1/header.gz"):
        p = ROOT / (prefix + suffix)
        require(p.is_file() and p.stat().st_size > 0, "incomplete native plasma/Maxwell checkpoint: " + suffix)
    old_csv = ROOT / result / "run/plasma.csv"
    with old_csv.open(newline="") as f:
        times = [float(row["time"]) for row in csv.DictReader(f)]
    require(len(times) >= 461 and math.isclose(times[-1], 1e-4, abs_tol=1e-12),
            "upstream CSV endpoint/rows invalid")
    require(all(y > x for x, y in zip(times, times[1:])), "upstream native time sequence nonmonotonic")
    for p in args:
        require(p.is_file() and p.stat().st_size > 0, "missing exact active overlay: " + str(p))
    lib = library()
    prior = inp.read_text()
    end_ns, prior_grid = lib.time_grid(prior)
    require(end_ns == START_NS and len(prior_grid) == 461, "legacy BASE timegrid mismatch")
    extended = lib.extend_input(prior, START_NS, END_NS, str(CAP_NS))
    adaptive = lib.stage_adaptive_stepper(extended, str(CAP_NS))
    inp.write_text(lib.advanced_restart_input(adaptive, prefix))
    parent.write_text(lib.stage_parent_multiapp_restart_overlay(parent.read_text()))
    child.write_text(lib.stage_child_maxwell_restart_overlay(child.read_text()))
    require("type = IterationAdaptiveDT" in inp.read_text(), "adaptive stepper not installed")
    require("no_restore = false" in parent.read_text(), "Maxwell restore disabled")
    require("type = TimeSequenceStepper" not in inp.read_text(), "old stepper retained")
    require("initial_condition =" not in inp.read_text(), "parent IC re-seeding")
    require("initial_condition =" not in child.read_text(), "Maxwell IC re-seeding")
    require("EI-943" not in "\n".join(x.read_text() for x in args[2:]), "excluded EI943 material present")
    (result / "upstream_manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    (result / "recovery_prefix.txt").write_text(prefix + "\n")
    audit = {
        "source_run_id": UPSTREAM_RUN,
        "source_git_sha": SOURCE_SHA,
        "upstream_harness_sha": HARNESS_SHA,
        "base_authority_commit": RECORD_SHA,
        "upstream_artifact_id": proof["artifact_id"],
        "power_W": power, "start_ns": START_NS, "end_ns": END_NS,
        "interval_cap_ns": CAP_NS, "initial_dt_s": 1e-12,
        "restart_mode": "genuine_native_advanced_checkpoint",
        "exact_checkpoint_prefix": prefix,
        "actual_upstream_moose_step": m["actual_moose_step"],
        "chemistry_channels": list(REQUIRED_CHANNELS),
        "physics_semantics": "same_original_14ch_base",
        "acceptance": "SCIENCE_HOLD",
    }
    (result / "restart_100to300_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print("BASE14_100TO300_NATIVE_CHECKPOINT_STAGED_PASS", power, prefix, flush=True)

def restore_rates(power: int) -> None:
    b = load_record(power)
    _, manifest_path = upstream_files(power)
    m = load_json(manifest_path)
    result, _, _, _, args = paths(power)
    require((result / "restart_100to300_audit.json").is_file(), "restart not staged")
    rate_dir = Path("/tmp/oxygen25/private_rates")
    dest = CHEM / "private_rates"
    require(rate_dir.is_dir(), "missing original private rate package")
    dest.mkdir(parents=True, exist_ok=True)
    for reaction, filename in PRIVATE_RATES.items():
        p = rate_dir / filename
        expected = (b["rate_provenance"][reaction]["sha256"] if reaction in b["rate_provenance"]
                    else m[f"{reaction.lower().replace('-', '')}_lookup_sha256"])
        # EI-407/EI-417/EI-935 use original native manifest spelling.
        if reaction in ("EI-407", "EI-417", "EI-935"):
            expected = m[f"ei{reaction[3:]}_lookup_sha256"]
        require(p.is_file() and sha(p) == expected, "private rate SHA mismatch: " + reaction)
        target = dest / filename
        require(not target.exists(), "private rate target unexpectedly present")
        shutil.copyfile(p, target)
        require(sha(target) == expected, "rate copy hash mismatch")
    derived = list((Path("_upstream_artifact") / f"{power}W").rglob(
        "ei2738_mcs_derived_lookup_100pt.txt"))
    require(len(derived) == 1, "missing/ambiguous original derived EI2738 rate")
    require(sha(derived[0]) == m["ei2738_mcs_derived_rate_sha256"], "derived EI2738 SHA mismatch")
    require(sha(derived[0]) == b["rate_provenance"]["EI-2738"]["sha256"], "BASE EI2738 SHA mismatch")
    shutil.copyfile(derived[0], dest / "EI-2738_Om_MCS.txt")
    require(not (dest / "EI-943_O_1D.txt").exists(), "excluded EI943 rate unexpectedly present")
    for f in args:
        txt = f.read_text()
        for filename in PRIVATE_RATES.values():
            if f"private_rates/{filename}" in txt:
                require((dest / filename).is_file(), "unrehydrated active rate")
    print("BASE14_100TO300_PRIVATE_RATE_PROVENANCE_PASS", power, flush=True)

def native_csv(path: Path):
    require(path.is_file() and path.stat().st_size > 0, "missing native CSV")
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    require(len(rows) > 1 and "time" in rows[0], "missing native time series")
    times = [float(r["time"]) for r in rows]
    require(all(math.isfinite(x) for x in times), "nonfinite recorded time")
    require(all(b > a for a, b in zip(times, times[1:])), "nonmonotonic native time series")
    return rows, times

def archive_files(destination: Path, selected: list[Path]):
    records = []
    with tarfile.open(destination, "w:gz") as stream:
        for p in selected:
            require(p.is_file() and not p.is_symlink(), "unsafe/non-file archive member")
            require(p.resolve().is_relative_to(ROOT.resolve()), "archive member outside checkout")
            rel = p.relative_to(ROOT).as_posix() if p.is_absolute() else p.as_posix()
            require(rel.startswith("experiments/") and "private_rates" not in rel,
                    "private or unsafe archive path")
            stream.add(p, arcname=rel, recursive=False)
            records.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha(p)})
    return {"name": destination.name, "bytes": destination.stat().st_size,
            "sha256": sha(destination), "inventory": records}

def verify(power: int) -> None:
    b = load_record(power)
    result, inp, parent, child, args = paths(power)
    provenance = load_json(result / "restart_100to300_audit.json")
    require(provenance["power_W"] == power and provenance["start_ns"] == START_NS,
            "staged restart provenance changed")
    require(provenance["end_ns"] == END_NS, "end time changed")
    native_log = result / "recovery_runtime.log"
    require(native_log.is_file(), "native runtime log missing")
    matches = re.findall(r"(?m)^Time Step\s+(\d+),\s*time\s*=\s*([0-9.eE+-]+)", native_log.read_text(errors="replace"))
    require(bool(matches), "no genuine native step evidence")
    final_step, final_time_s = int(matches[-1][0]), float(matches[-1][1])
    require(final_step > provenance["actual_upstream_moose_step"], "native MOOSE step did not advance")
    require(math.isclose(final_time_s, 0.0003, rel_tol=0, abs_tol=1e-12), "native solver did not reach 300us")
    run = result / "run"
    csv_path = run / f"{RUN_STEM}.csv"
    exodus = run / f"{RUN_STEM}.e"
    rows, times = native_csv(csv_path)
    require(math.isclose(times[0], 0.0001, abs_tol=1e-12, rel_tol=0), "restart did not begin at 100us")
    require(math.isclose(times[-1], 0.0003, abs_tol=1e-12, rel_tol=0), "native CSV did not reach 300us")
    require(exodus.is_file() and exodus.stat().st_size > 0, "native Exodus output missing")
    require("P_rf_raw_W_t6" in rows[-1], "missing RF monitor")
    rf = float(rows[-1]["P_rf_raw_W_t6"])
    require(math.isfinite(rf), "RF monitor nonfinite")
    for key, val in rows[-1].items():
        if val not in ("", None):
            try:
                num = float(val)
            except ValueError:
                continue
            require(math.isfinite(num), "nonfinite terminal native monitor: " + key)
    cp = run / f"{RUN_STEM}_cp" / f"{final_step:04d}"
    for suffix in ("-restart-0.rd/data", "-restart-0.rd/header", "-mesh.cpa.gz/1/header.gz"):
        p = Path(str(cp) + suffix)
        require(p.is_file() and p.stat().st_size > 0, "missing final genuine checkpoint: " + str(p))
    checkpoint_dir = cp.parent
    selected_run = sorted(p for p in checkpoint_dir.rglob("*") if p.is_file()) + [csv_path, exodus]
    selected_inputs = sorted(set(args + [child, CHEM /
        f"rf_elastic_multiapp_maxwell_{power}w_100us_dt1000ns_child.i"]))
    prior_manifest = load_json(result / "upstream_manifest.json")
    for record in prior_manifest["inventory"]["inputs"]:
        f = Path(record["path"])
        require(f.is_file(), "missing archived original input: " + str(f))
        selected_inputs.append(f)
    selected_inputs = sorted(set(selected_inputs))
    run_meta = archive_files(result / "restart_run_300000ns.tar.gz", selected_run)
    inputs_meta = archive_files(result / "restart_inputs_300000ns.tar.gz", selected_inputs)
    manifest = {
        "schema": "base14_one_shot_restart_v1",
        "owner_issue": 395,
        "upstream_run_id": UPSTREAM_RUN,
        "upstream_source_SHA": HARNESS_SHA,
        "physics_app_source_SHA": SOURCE_SHA,
        "base_record_SHA": RECORD_SHA,
        "upstream_artifact_id": b["verified_runs"][f"{power}W"]["artifact_id"],
        "upstream_checkpoint_prefix": provenance["exact_checkpoint_prefix"],
        "native_restart_checkpoint_prefix": cp.as_posix(),
        "native_final_time_s": final_time_s,
        "native_step": final_step,
        "power_W": power,
        "native_RF_power_W_at_end": rf,
        "native_csv_initial_s": times[0],
        "native_csv_terminal_s": times[-1],
        "native_csv_rows": len(rows),
        "time_interval_ns": [START_NS, END_NS],
        "dt_cap_ns": CAP_NS,
        "chemistry_channels": list(REQUIRED_CHANNELS),
        "science_acceptance": "HOLD",
        "native_P3_P4_status": "PASS",
        "archives": {"run": run_meta, "inputs": inputs_meta},
        "private_rates_in_archive": False,
        "no_scientific_promotion": True,
    }
    (result / "restart_300000ns_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("BASE14_100TO300_NATIVE_P3_P4_PASS", power, "native_step", final_step,
          "last_rf_W", rf, flush=True)

def self_test():
    require(len(REQUIRED_CHANNELS) == len(set(REQUIRED_CHANNELS)) == 14, "invalid 14ch census")
    require(START_NS == 100000 and END_NS == 300000 and CAP_NS == 1000, "time contract drift")
    lib = library()
    for bad in ("../secret", "/tmp/secrets"):
        try:
            lib.safe_path(ROOT, bad)
        except ValueError:
            pass
        else:
            raise ValueError("unsafe tar path accepted in negative control")
    try:
        lib.stage_adaptive_stepper("not an Executioner", str(CAP_NS))
    except ValueError:
        pass
    else:
        raise ValueError("missing Executioner negative control accepted")
    print("BASE14_100TO300_RESTART_P0_SELF_TEST_PASS", flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("self-test", "stage", "rates", "verify"))
    p.add_argument("--power-w", type=int, choices=(400, 1000))
    args = p.parse_args()
    if args.action == "self-test":
        self_test()
        return
    require(args.power_w in (400, 1000), "power missing")
    {"stage": stage, "rates": restore_rates, "verify": verify}[args.action](args.power_w)

if __name__ == "__main__":
    main()
