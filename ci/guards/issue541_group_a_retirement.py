#!/usr/bin/env python3
"""Fail-closed, read-only Group A retirement inventory.

This is an evidence gate, NOT a workflow retirement or global guard waiver.
No dynamic/external caller absence is inferred from a code-search miss.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = Path("ci/baselines/issue541_group_a_retirement.json")
CASES = {
    "A1": ("CORE", "issue402-dd-json-boundary-p0-p2-once.yml",
           "bbebff910db3e5659014368043a50b99273d2cdc",
           "issue-402-dd-plasma-boundary-action", "PRESENT", 43533803916),
    "A2": ("FLOW", "issue402-legacy-symbol-audit-once.yml",
           "1931f0b9909507979826812f346d3353f12e333b",
           "issue-402-dd-plasma-boundary-action", "PRESENT", 43522731185),
    "A3": ("FLOW", "issue402-rate-coef-ideal-gas-native-once.yml",
           "64164c097ec8f7831e67b80b317144cd97ba9ee8",
           "issue-402-rate-coef-ideal-gas", "NOT_FOUND", 43464123958),
    "A4": ("FLOW", "issue402-reaction-material-reduction-p0-once.yml",
           "5e433b5c56f335808e6a5cbaa771b808eef1ad45",
           "issue-402-species-functor-naming", "NOT_FOUND", 43428302896),
}
KNOWN_ARTIFACTS = {"A1": 14088768015, "A2": None,
                   "A3": 14058320821, "A4": None}


# Immutable 2026-11-16 readback receipts. These are historical observations,
# not live branch lookups and not permission to retire either workflow.
A1_A2_LIVE_HEAD = "af4a9e896328386723e8bbb957f334e1d83fe75e"
A1_A2_SAME_HEAD_PROOFS = {
  "A1": {
    "candidate_pr": 553,
    "head": "34a3539477071d56027c60b1f19d0b502b2e9733",
    "run_id": 43839529668,
    "run_conclusion": "failure",
    "job_id": 133204451509,
    "job_name": "Issue541 CORE four native source-bound P1 P2 (no P3)",
    "job_conclusion": "success",
    "scope": "P0/P1/P2",
    "p3": "NOT_RUN"
  },
  "A2": {
    "candidate_pr": 553,
    "head": "34a3539477071d56027c60b1f19d0b502b2e9733",
    "run_id": 43839529668,
    "run_conclusion": "failure",
    "job_id": 133204451103,
    "job_name": "issue402_legacy_p0_inventory",
    "job_conclusion": "success",
    "scope": "P0",
    "p3": "NOT_RUN"
  }
}

def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def check_trigger(source: str, path: str, branch: str) -> list[str]:
    errors = []
    prologue = source.split("permissions:", 1)[0]
    if not re.search(r"(?m)^on:\s*$", prologue):
        errors.append("missing on: trigger")
    if not re.search(r"(?m)^  push:\s*$", prologue):
        errors.append("missing push trigger")
    if "    branches: [" + branch + "]" not in prologue:
        errors.append("historical branch differs")
    if "    paths: [" + path + "]" not in prologue:
        errors.append("exact self-file trigger differs")
    if re.search(r"(?m)^  (workflow_dispatch|workflow_call|workflow_run|repository_dispatch|schedule|pull_request):", prologue):
        errors.append("unexpected additional trigger")
    return errors


def inspect(root: Path, doc: dict) -> list[str]:
    errors = []
    if doc.get("schema") != "issue541.workflow_surface.group_a_evidence.v1":
        errors.append("schema")
    if doc.get("repository") != "HyungseonSong-plasma/moose-test-repo":
        errors.append("repository")
    if doc.get("baseline_main_sha") != "71e112eb05d4645c82aab8861b99d6952ac4ac3e":
        errors.append("baseline source")
    if doc.get("science") != "SCIENCE_HOLD" or doc.get("p3") != "NOT_RUN":
        errors.append("science/P3 promotion")
    records = doc.get("workflows")
    if not isinstance(records, list):
        return errors + ["missing workflow records"]
    ids = [x.get("id") for x in records if isinstance(x, dict)]
    if len(records) != 4 or set(ids) != set(CASES) or len(ids) != len(set(ids)):
        errors.append("must inventory exactly four unique Group A owners")
    for record in records:
        if not isinstance(record, dict) or record.get("id") not in CASES:
            errors.append("unknown or malformed Group A record")
            continue
        id_ = record["id"]
        package, name, sha, branch, observed, run = CASES[id_]
        path = ".github/workflows/" + name
        for key, value in (("package", package), ("path", path),
                           ("original_blob", sha), ("historical_branch", branch),
                           ("branch_observed", observed), ("original_run_id", run),
                           ("original_conclusion", "success")):
            if record.get(key) != value:
                errors.append(id_ + " mismatched " + key)
        if not re.fullmatch(r"[0-9a-f]{40}", str(record.get("original_source_sha", ""))):
            errors.append(id_ + " missing historical source identity")
        source_path = root / path
        if not source_path.is_file():
            # A future accepted retirement requires a *different* contract;
            # do not let dropping the old YAML silently turn CI green.
            errors.append(id_ + " historical workflow absent without accepted retirement")
        else:
            raw = source_path.read_bytes()
            if git_blob_sha(raw) != sha:
                errors.append(id_ + " original Git blob changed")
            errors += [id_ + " " + error for error in
                       check_trigger(raw.decode("utf-8"), path, branch)]
        artifact = record.get("artifact")
        expected_id = KNOWN_ARTIFACTS[id_]
        if expected_id is None:
            if artifact is not None:
                errors.append(id_ + " invented original artifact")
        elif not isinstance(artifact, dict) or artifact.get("id") != expected_id or (
            not isinstance(artifact.get("bytes"), int) or artifact["bytes"] <= 0
        ) or artifact.get("expired") is not False:
            errors.append(id_ + " missing original artifact receipt")
        replacement = record.get("replacement")
        if not isinstance(replacement, dict) or replacement.get("conclusion") != "success" or (
            not isinstance(replacement.get("run_id"), int) or replacement["run_id"] <= 0
        ) or not re.fullmatch(r"[0-9a-f]{40}", str(replacement.get("head", ""))):
            errors.append(id_ + " missing source-bound replacement receipt")
        if id_ in A1_A2_SAME_HEAD_PROOFS:
            # A historical success job does not override red global CI or
            # the verified still-present live legacy-branch entrypoint.
            observed = {
                "head": A1_A2_LIVE_HEAD,
                "workflow_blob": sha,
                "entrypoint": "PUSH_SELF_PATH_STILL_PRESENT",
                "observed_on": "2026-11-16",
            }
            if record.get("live_branch_readback") != observed:
                errors.append(id_ + " active legacy branch receipt missing or falsified")
            if record.get("same_head_revalidation") != A1_A2_SAME_HEAD_PROOFS[id_]:
                errors.append(id_ + " same-head CI/job provenance missing or falsified")
        if record.get("decision") != "KEEP_HOLD":
            errors.append(id_ + " retirement promoted without accepted caller-zero/integrated proof")
        if not isinstance(record.get("blockers"), list) or not record["blockers"]:
            errors.append(id_ + " missing explicit HOLD blockers")
        if "UNPROVEN" not in str(record.get("caller_state", "")):
            errors.append(id_ + " external/dynamic caller uncertainty omitted")
        if not isinstance(record.get("required"), list) or not record["required"]:
            errors.append(id_ + " missing P0/P1/P2 obligations")
    return errors


def self_test(root: Path, original: dict) -> None:
    assert not inspect(root, original), inspect(root, original)
    probes = []
    for id_ in CASES:
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["decision"] = "RETIRED_VERIFIED"
        probes.append(("false retirement " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["original_blob"] = "0" * 40
        probes.append(("forged source hash " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["blockers"] = []
        probes.append(("lost blockers " + id_, mutated))
    mutated = copy.deepcopy(original)
    mutated["workflows"].pop()
    probes.append(("omitted owner", mutated))
    mutated = copy.deepcopy(original)
    mutated["science"] = "SCIENCE_PASS"
    probes.append(("unapproved science", mutated))
    mutated = copy.deepcopy(original)
    mutated["workflows"][0]["caller_state"] = "ZERO_PROVEN"
    probes.append(("fabricated caller zero", mutated))
    for id_ in A1_A2_SAME_HEAD_PROOFS:
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["live_branch_readback"]["head"] = "0" * 40
        probes.append(("falsified active branch " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["same_head_revalidation"]["run_conclusion"] = "success"
        probes.append(("falsified global CI pass " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["same_head_revalidation"]["job_id"] = 0
        probes.append(("missing exact job provenance " + id_, mutated))
    for label, fake in probes:
        assert inspect(root, fake), "negative mutation not rejected: " + label
    first = original["workflows"][0]
    raw = (root / first["path"]).read_text(encoding="utf-8")
    assert check_trigger(raw.replace(first["historical_branch"], "main", 1),
                         first["path"], first["historical_branch"])
    assert check_trigger(raw.replace("    paths:", "    paths_disabled:", 1),
                         first["path"], first["historical_branch"])
    print("ISSUE541_GROUP_A_MUTATION_SELF_TEST=PASS count=" + str(len(probes) + 2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    doc = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    errors = inspect(root, doc)
    if errors:
        for item in errors:
            print("::error::GROUP_A_CONTRACT: " + item)
        return 1
    if args.self_test:
        self_test(root, doc)
    if args.check:
        for record in doc["workflows"]:
            print(record["id"] + " " + record["decision"] + " | " +
                  record["caller_state"] + " | original=" + record["original_blob"])
        print("ISSUE541_GROUP_A_LEDGER=PASS RETIREMENTS=0 GLOBAL_SURFACE_GUARD_NOT_WAIVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
