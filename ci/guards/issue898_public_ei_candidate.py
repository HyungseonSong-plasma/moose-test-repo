"""#898: public EI rate cutover in disposable New-only Public D cases.

No protected data or secret is read. Do not replace the original baseline or
claim physical equivalence. Verify source-layer receipts, exact public data
pins, case-specific bindings, and actual Native check-input separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

from issue671_secure_ei_rate_scratch import validate_rows

ROOT = Path(__file__).resolve().parents[2]
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
DB = Path("physics_app/database")
CASES = ("417", "941")
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
PUBLIC_BLOBS = {
    "EI-415_O2_X.txt": "4ece8676cd98d14bab534edbdf1a6fd9c8be7cf6",
    "EI-401_O2_X.txt": "24df46abe6bf001be650785415446e5be245622a",
    "EI-407_O2_X.txt": "0069d5a506ae85ff5d994049a7de34d25d439918",
    "EI-2069_O2_a1Delta.txt": "f23a9efc1ee35882734768a1db93057bbf901c63",
    "EI-417_O2_X.txt": "f005d856b75209fc4e3df0c1904f526907d40fc2",
    "EI-941_O_3P.txt": "1c85c36afbc9249f79aaff09cdcb564700649b9b",
}
REQUIRED = {
    "417": frozenset(PUBLIC_BLOBS) - {"EI-941_O_3P.txt"},
    "941": frozenset(PUBLIC_BLOBS) - {"EI-417_O2_X.txt"},
}
RATE = re.compile(
    rb"(?m)^([ \t]*rate_table_file[ \t]*=[ \t]*)(['\"]?)"
    rb"private_rates/([\w.+-]+\.txt)\2([ \t]*(?:#[^\r\n]*)?)(\r?)$"
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_rates(root):
    result = {}
    for name, expected in PUBLIC_BLOBS.items():
        file = root / DB / name
        if file.is_symlink() or not file.is_file():
            raise ValueError("PUBLIC_EI_SOURCE_NOT_REGULAR")
        raw = file.read_bytes()
        if blob_sha(raw) != expected or validate_rows(raw) != 100:
            raise ValueError("PUBLIC_EI_SOURCE_PIN_OR_SHAPE")
        result[name] = raw
    return result


def rebind(case, layers):
    """Change only the five exact protected lookup path tokens."""
    if case not in REQUIRED:
        raise ValueError("PUBLIC_EI_CASE_INVALID")
    observed = []
    changed = {}
    for name, raw in layers.items():
        def replace(match):
            observed.append(match.group(3).decode("ascii"))
            return (match.group(1) + match.group(2) +
                    b"../../physics_app/database/" + match.group(3) +
                    match.group(2) + match.group(4) + match.group(5))
        new = RATE.sub(replace, raw)
        if b"private_rates/" in new:
            raise ValueError("PUBLIC_EI_UNRECOGNIZED_PRIVATE_REFERENCE")
        changed[name] = new
    if len(observed) != 5 or set(observed) != REQUIRED[case]:
        raise ValueError("PUBLIC_EI_EXACT_CASE_BINDING_MISMATCH")
    return changed


def stage_case(source, target, case, receipt, rates):
    if target.exists() or target.is_symlink() or source.is_symlink():
        raise ValueError("PUBLIC_EI_SCRATCH_DESTINATION_CONFLICT")
    if any(p.is_symlink() or p.name == "private_rates" for p in source.rglob("*")):
        raise ValueError("PUBLIC_EI_PRIVATE_OR_SYMLINK_INPUT")
    ordered = receipt["ordered_inputs"]
    names = [Path(n).name for n in ordered]
    if (len(names) != 11 or len(set(names)) != 11
            or any(Path(n) != CHEM / name for n, name in zip(ordered, names))):
        raise ValueError("PUBLIC_EI_ORDER_INVALID")
    chem = source / CHEM
    layers = {n: (chem / n).read_bytes() for n in names}
    if {n: sha(v) for n, v in layers.items()} != receipt["11_layer_sha256"]:
        raise ValueError("PUBLIC_EI_SOURCE_LAYER_DRIFT")
    mechanism = Path("chemistry") / f"public_d_s6_{case}_physics.json"
    mechanism_bytes = (chem / mechanism).read_bytes()
    if (sha(mechanism_bytes) != receipt["JSON_sha256"]
            or receipt.get("original_table_rows") != 100):
        raise ValueError("PUBLIC_EI_MECHANISM_OR_LOOKUP_DRIFT")
    rewritten = rebind(case, layers)
    for name in REQUIRED[case]:
        if blob_sha(rates[name]) != PUBLIC_BLOBS[name]:
            raise ValueError("PUBLIC_EI_RATE_DRIFT")
    shutil.copytree(source, target, symlinks=False)
    database = target / DB
    database.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED[case]:
        file = database / name
        with file.open("xb") as stream:
            stream.write(rates[name])
        if sha(file.read_bytes()) != sha(rates[name]):
            raise ValueError("PUBLIC_EI_RATE_READBACK")
    for n, raw in rewritten.items():
        if raw != layers[n]:
            (target / CHEM / n).write_bytes(raw)
        if (target / CHEM / n).read_bytes() != raw:
            raise ValueError("PUBLIC_EI_LAYER_READBACK")
    if (target / CHEM / mechanism).read_bytes() != mechanism_bytes:
        raise ValueError("PUBLIC_EI_JSON_CHANGED")
    return {
        "case": case, "ordered": ordered,
        "source_layer_sha256": receipt["11_layer_sha256"],
        "candidate_layer_sha256": {n: sha(v) for n, v in rewritten.items()},
        "changed_layers": sorted(n for n in names if layers[n] != rewritten[n]),
        "json_sha256": sha(mechanism_bytes),
        "rates_sha256": {n: sha(rates[n]) for n in sorted(REQUIRED[case])},
        "rate_source": "PUBLIC_INDEPENDENT_100ROW",
        "native_p2": "NOT_RUN", "science": "SCIENCE_HOLD",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    if "PROTECTED_ARCHIVE_B64" in os.environ:
        raise ValueError("PUBLIC_EI_SECRET_ENV_DENIED")
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                   text=True).strip()
    if head != args.head or args.output.exists():
        raise ValueError("PUBLIC_EI_SOURCE_OR_OUTPUT_IDENTITY")
    binary = ROOT / "physics_app/physics-opt"
    binary_sha = sha(binary.read_bytes())
    rates = load_rates(ROOT)
    source_receipt = json.loads(args.receipt.read_text())
    if set(source_receipt) != set(CASES):
        raise ValueError("PUBLIC_EI_SOURCE_CASE_SET")
    result = {"schema": "issue898.public_ei_newonly_candidate.v1",
              "source_head": head, "binary_sha256": binary_sha,
              "science": "SCIENCE_HOLD", "cases": {}, "native_p2": "HOLD"}
    try:
        with tempfile.TemporaryDirectory(prefix="issue898-public-ei-") as tmp:
            for case in CASES:
                target = Path(tmp) / case
                rec = stage_case(args.staged / "scratch" / case, target,
                                 case, source_receipt[case], rates)
                result["cases"][case] = rec
                command = ("set -euo pipefail; source /environment; exec "
                           "/workspace/physics_app/physics-opt --check-input -i " +
                           " ".join(shlex.quote(n) for n in rec["ordered"]))
                proc = subprocess.run([
                    "docker", "run", "--rm", "--network", "none",
                    "--entrypoint", "/bin/bash", "--user",
                    f"{os.getuid()}:{os.getgid()}", "--workdir", "/case",
                    "--env", "OXYGEN_RESEARCH_400=1",
                    "--env", "OXYGEN_RESEARCH_FULL24=0",
                    "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
                    "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
                    "--mount", f"type=bind,src={ROOT},dst=/workspace,readonly",
                    "--mount", f"type=bind,src={target},dst=/case",
                    OCI, "-lc", command], capture_output=True, text=True,
                    timeout=480, check=False)
                combined = proc.stdout + "\n" + proc.stderr
                rec["exit_code"] = proc.returncode
                rec["log_sha256"] = sha(combined.encode())
                rec["syntax_ok"] = "Syntax OK" in combined
                rec["native_p2"] = ("PASS_SYNTAX_ONLY" if proc.returncode == 0
                                    and rec["syntax_ok"] else "HOLD")
                if rec["native_p2"] != "PASS_SYNTAX_ONLY":
                    # This run contains only public inputs; bounded diagnostic.
                    print(combined[-4000:])
                    raise ValueError("PUBLIC_EI_NATIVE_P2_FAILED:" + case)
            if sha(binary.read_bytes()) != binary_sha:
                raise ValueError("PUBLIC_EI_BINARY_CHANGED")
            result["native_p2"] = "PASS_SYNTAX_ONLY"
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print("ISSUE898_PUBLIC_EI_NEWONLY_NATIVE_P2", result["native_p2"],
          "417/941 SCIENCE_HOLD")


if __name__ == "__main__":
    main()
