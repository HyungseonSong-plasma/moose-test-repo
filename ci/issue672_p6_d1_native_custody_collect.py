#!/usr/bin/env python3
"""Collect independent P6-D1 PR684 Public/FLOW real --check-input P2/P05 evidence.

No scientific timesteps; fail closed on source/binary identity and log mismatch.
Never label a staging or parser failure a P05 Warehouse result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

SOURCE = "3e48a0651ac53ec32e34b4b31e44098ffad80e1c"
HIST = "29d1acc6ef7969908b86719e4b95c73a1565136d"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for c in iter(lambda: f.read(1024*1024), b""):
            h.update(c)
    return h.hexdigest()


def optional(path):
    p = Path(path)
    return p if p.is_file() else None


def first_error(log):
    if not log:
        return "NATIVE_NOT_RUN_NO_LOG"
    text = Path(log).read_text(errors="replace")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "*** ERROR ***" in line:
            return " ".join(lines[index + 1:index + 4]).strip()[:450]
    for line in lines:
        if any(word in line for word in ("P05 ", "ERROR:", "Error: ", "Errorcode:")):
            return line.strip()[:450]
    return "NO_EXPLICIT_ERROR_IN_NATIVE_LOG"


def describe(logpath, metadata=None):
    info = dict(metadata or {})
    p = optional(logpath)
    info["real_native_log_present"] = p is not None
    info["real_native_log_sha256"] = digest(p) if p else None
    info["first_error_or_marker"] = first_error(p)
    text = p.read_text(errors="replace") if p else ""
    info["P05_reached_with_guard_message"] = bool(re.search(
        r"P05 FV Native/Physics duplicate or unexpected owner|P05 expected|P05 FV",
        text))
    info["P05_rejected_duplicate"] = "P05 FV Native/Physics duplicate or unexpected owner" in text
    info["Syntax_OK_in_native_log"] = "Syntax OK" in text
    if "log_sha256" in info and p is not None and info["log_sha256"] != info["real_native_log_sha256"]:
        raise AssertionError("NATIVE_LOG_SHA_CUSTODY_MISMATCH:" + str(logpath))
    info["actual_P2"] = ("PASS" if info.get("exit_code") == 0 and "Syntax OK" in text
                         else "HOLD")
    return info


def capture(root, outputs):
    src = root / "control"
    history = root / "historical"
    source = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    historical = subprocess.check_output(["git", "-C", str(history), "rev-parse", "HEAD"], text=True).strip()
    if (source, historical) != (SOURCE, HIST):
        raise AssertionError(f"EXACT_SOURCE_IDENTITY_MISMATCH:{source}:{historical}")
    provenance_file = src / "experiments/Issue402_plasma_dsl_g1/evidence/native_p1_identity.json"
    binary = src / "physics_app/physics-opt"
    if not provenance_file.is_file() or not binary.is_file():
        raise AssertionError("NO_ACTUAL_BINARY_OR_NATIVE_P1_PROVENANCE")
    provenance = json.loads(provenance_file.read_text())
    if provenance.get("source_sha") != SOURCE or provenance.get("oci_image") != OCI:
        raise AssertionError("WRONG_NATIVE_SOURCE_OR_TOOLCHAIN")
    real_elf_sha = digest(binary)
    if provenance["binary_sha256"] != real_elf_sha:
        raise AssertionError("ACTUAL_BINARY_SHA_CHANGED")
    report = {
        "schema": "issue672.p6_d1_integration_review.actual_cpp_native.v1",
        "PR684_exact_source_sha": SOURCE, "historical_exact_sha": HIST,
        "native_binary_sha256_independently_rehashed": real_elf_sha,
        "binary_provenance": provenance,
        "no_physical_science_timestep": True, "science": "SCIENCE_HOLD",
        "cases": {}, "P05_positive_control": {}, "P05_negative_control": {},
    }
    evidence = src / "experiments/Issue402_plasma_dsl_g1/evidence"
    public_file = evidence / "issue402_option_s6_p2_status.json"
    report["public_driver_exit_code"] = int((outputs/"public_driver.exit").read_text()) if (outputs/"public_driver.exit").exists() else None
    if public_file.is_file():
        public = json.loads(public_file.read_text())
        report["public_p2_report_sha256"] = digest(public_file)
        for case in ("417", "941"):
            for variant in ("B", "D"):
                meta = public.get("checks", {}).get(case, {}).get(variant, {})
                log = evidence / f"S6_{case}_{variant}_P2.log"
                report["cases"][f"PUBLIC_{case}_{variant}"] = describe(log, meta)
    else:
        report["public_p2_report_sha256"] = None
        for case in ("417", "941"):
            for variant in ("B", "D"):
                report["cases"][f"PUBLIC_{case}_{variant}"] = describe(evidence/f"S6_{case}_{variant}_P2.log")
    for case in ("417", "941"):
        folder = outputs/f"flow-{case}"
        rfile = folder/"readiness.json"
        driver_exit = outputs/f"flow-{case}.exit"
        log = folder/f"S6-{case}"/"native_P2.log"
        metadata = {}
        if rfile.is_file():
            readiness = json.loads(rfile.read_text())
            if readiness.get("source_sha") != SOURCE or readiness.get("binary_sha256") != real_elf_sha:
                raise AssertionError("FLOW_BINARY_OR_SOURCE_DIFFERENT")
            report[f"flow_{case}_readiness_sha256"] = digest(rfile)
            metadata = readiness.get("cases", {}).get(case, {}).get("check_input", {})
        info = describe(log, metadata)
        info["driver_exit_code"] = int(driver_exit.read_text()) if driver_exit.exists() else None
        report["cases"][f"FLOW_{case}"] = info
    for label, filename in (("P05_positive_control","p05-positive"),
                            ("P05_negative_control","p05-negative")):
        file=outputs/(filename+".log")
        exitfile=outputs/(filename+".exit")
        data=describe(file)
        data["exit_code"] = int(exitfile.read_text()) if exitfile.is_file() else None
        report[label]=data
    report["all_requested_actual_native_logs_present"] = all(
        report["cases"][k]["real_native_log_present"]
        for k in ("PUBLIC_417_D", "PUBLIC_941_D", "FLOW_417", "FLOW_941"))
    report["all_requested_s6_P2_PASS"] = all(
        report["cases"][k]["actual_P2"] == "PASS"
        for k in ("PUBLIC_417_D", "PUBLIC_941_D", "FLOW_417", "FLOW_941"))
    report["all_requested_S6_P05_confirmed"] = all(
        report["cases"][k]["P05_reached_with_guard_message"]
        for k in ("PUBLIC_417_D", "PUBLIC_941_D", "FLOW_417", "FLOW_941"))
    report["integration_recommendation"] = (
        "P6_D1_CAN_REVIEW_MERGE_ONLY_AFTER_APPROVAL_GATES"
        if report["all_requested_s6_P2_PASS"] else
        "P6_D1_MERGE_HOLD_NATIVE_P2_NOT_ALL_PASS")
    report["source_only_P05_guard_not_waived"] = True
    (outputs/"p6_d1_native_custody.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    return report


if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--workspace",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    print(json.dumps(capture(args.workspace,args.out),sort_keys=True))
