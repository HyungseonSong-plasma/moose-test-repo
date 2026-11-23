#!/usr/bin/env python3
"""In-memory, hash-only verification of historical protected EI rates.

Never persist or print original rate table bytes, decoded archive bytes, or
unmatched digest values. This tool must run only in an authorized Actions
secret-bearing job. It does not perform Native P2/P3/P4.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import math
import os
from pathlib import PurePosixPath, Path
import sys
import tarfile
import tempfile
import re
import stat
import zipfile

EXPECTED = {
    "EI-415_O2_X.txt": "9108838e43298185e71679d2fff09c74c5c601ed3ebbaa3ba02548a374db8c64",
    "EI-401_O2_X.txt": "185a102beb38d5a7a91846c69933b3f4b43e9c31dc0d57d1c5fae496206782ff",
    "EI-417_O2_X.txt": "4e87121cad771a4ebbe272efa0b9349e527b0de782afc97b3f14556c57fc550d",
    "EI-941_O_3P.txt": "ca10a223d631e04a84464649bac96ba3c7ee4ca157a1127376e04b66781e2adc",
    "EI-407_O2_X.txt": "2565be45b9a13204583b6714a7d1b581cf29c157c78ac502d665649e4065b359",
    "EI-2069_O2_a1Delta.txt": "5eba74c1870e0635a3e316e143961e9f04e259675ddad00fd8653de28980644a",
}
REQUIRED_B6 = ("EI-415_O2_X.txt", "EI-401_O2_X.txt", "EI-417_O2_X.txt")
SOURCE_HEAD = "9c15a4f0e2cf8042cb0d4b2f18af31511021d168"
HISTORICAL_HEAD = "29d1acc6ef7969908b86719e4b95c73a1565136d"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_rows(data: bytes) -> int:
    # Historical original preparer (prepare_first_batch.py) skips empty/comment
    # lines before checking EXACTLY 100 finite, nonnegative two-column rows.
    text = data.decode("utf-8")
    rows = []
    for raw in text.splitlines():
        stripped = raw.partition("#")[0].strip()
        if not stripped:
            continue
        fields = stripped.split()
        if len(fields) != 2:
            raise ValueError("NON_TWO_COLUMN_NUMERIC_DATA")
        energy, rate = map(float, fields)
        if not math.isfinite(energy) or not math.isfinite(rate) or rate < 0:
            raise ValueError("NONFINITE_OR_NEGATIVE_NUMERIC_DATA")
        if rows and energy <= rows[-1][0]:
            raise ValueError("NON_MONOTONIC_GRID")
        rows.append((energy, rate))
        if len(rows) > 100:
            raise ValueError("NUMERIC_DATA_TOO_MANY_ROWS")
    if len(rows) != 100:
        raise ValueError("NUMERIC_DATA_NOT_100_ROWS")
    return len(rows)


def read_hashed_rows():
    secret = os.environ.get("PROTECTED_ARCHIVE_B64", "")
    if not secret:
        raise ValueError("PROTECTED_RATE_SECRET_NOT_AVAILABLE")
    if len(secret) > 40_000_000:
        raise ValueError("PROTECTED_RATE_SECRET_SIZE_BOUND")
    compressed = base64.b64decode(secret, validate=True)
    if len(compressed) > 30_000_000:
        raise ValueError("PROTECTED_ARCHIVE_COMPRESSED_SIZE_BOUND")
    result = {}
    raw_table_bytes = {}
    with tarfile.open(fileobj=io.BytesIO(compressed), mode="r:xz") as bundle:
        members = bundle.getmembers()
        if len(members) > 256:
            raise ValueError("PROTECTED_ARCHIVE_MEMBER_BOUND")
        for member in members:
            name = member.name
            parts = PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts or member.issym() or member.islnk():
                raise ValueError("PROTECTED_ARCHIVE_UNSAFE_PATH_OR_LINK")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("PROTECTED_ARCHIVE_UNSUPPORTED_TYPE")
            # Only exact root-level original table names can satisfy an input.
            if len(parts) != 1 or parts[0] not in EXPECTED:
                continue
            if parts[0] in result:
                raise ValueError("PROTECTED_ARCHIVE_DUPLICATE_TARGET")
            if member.size <= 0 or member.size > 1024 * 1024:
                raise ValueError("PROTECTED_TABLE_SIZE_BOUND")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ValueError("PROTECTED_TABLE_READ_FAILURE")
            blob = stream.read(1024 * 1024 + 1)
            if len(blob) != member.size:
                raise ValueError("PROTECTED_TABLE_TRUNCATED")
            # The observed digest is retained ONLY if it equals an existing
            # reviewed public provenance digest. Never publish mismatch hashes.
            actual = digest(blob)
            match = actual == EXPECTED[parts[0]]
            try:
                numeric_rows = validate_rows(blob)
                shape_ok = True
            except Exception:
                numeric_rows = None
                shape_ok = False
            if match and shape_ok:
                raw_table_bytes[parts[0]] = blob
            result[parts[0]] = {
                "file": parts[0],
                "sha256_expected": EXPECTED[parts[0]],
                "sha256_observed_if_equal": actual if match else None,
                "sha256_match": match,
                "numeric_data_rows": numeric_rows,
                "numeric_shape_pass": shape_ok,
            }
    return result, raw_table_bytes


def negative_selftests():
    good = "# provenance\n# units\n" + "\n".join(f"{n} {n / 100:.8f}" for n in range(1, 101)) + "\n"
    good = good.encode()
    if validate_rows(good) != 100:
        raise AssertionError("VALID_100_DATA_ROWS_WITH_2_HEADERS_REJECTED")
    tests = [
        good.replace(b"1 0.01000000", b"1 NaN"),
        good.replace(b"2 0.02000000", b"1 0.02000000"),
        good + b"\n101 1.0\n",
        good.replace(b"3 0.03000000", b"3 -1.0"),
        good.replace(b"4 0.04000000", b"4 0.04 0.06"),
    ]
    for i, content in enumerate(tests):
        try:
            validate_rows(content)
        except ValueError:
            continue
        raise AssertionError("NEGATIVE_CONTROL_NOT_REJECTED_" + str(i))
    return len(tests)



# #671 secure handoff: the six original protected rate hashes are already
# independently established by CI #44190774410 (P1-B6/C6). Never substitute
# synthetic, public Boltzmann, or newly fitted rates for the original source.
SOURCE_HEAD_INTEGRATION = "395eeac274125ffa632b4d75a4531996dee24fe0"
P3X_ARTIFACT_SHA = "592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111"
CHEM = "experiments/Issue395_powered_chemistry_ladder"
REQUIRED = {
    "417": frozenset(EXPECTED) - {"EI-941_O_3P.txt"},
    "941": frozenset(EXPECTED) - {"EI-417_O2_X.txt"},
}
RATE_RE = re.compile(
    r"(?m)^\s*rate_table_file\s*=\s*['\"]?private_rates/([\w.+-]+\.txt)['\"]?\s*(?:#.*)?$"
)


class SecureHandoffError(Exception):
    """Safe, fixed error identifier only, never protected data."""


def check(ok: bool, code: str):
    if not ok:
        raise SecureHandoffError(code)


def safe_relative(path: str) -> Path:
    p = PurePosixPath(path)
    check(bool(path) and not path.startswith("/")
          and ".." not in p.parts and "\\" not in path
          and p.parts[0] == "experiments",
          "INVALID_PUBLIC_STAGE_PATH")
    return Path(*p.parts)


def preflight_cases(path: Path) -> dict:
    check(path.is_file() and digest(path.read_bytes()) == P3X_ARTIFACT_SHA,
          "IMMUTABLE_P3X_ARTIFACT_SHA_MISMATCH")
    cases = {}
    with zipfile.ZipFile(path) as z:
        check(z.testzip() is None, "PUBLIC_ZIP_CRC_MISMATCH")
        for case in ("417", "941"):
            root = "cases/" + case + "/"
            manifest = json.loads(z.read(root + "case_manifest.json"))
            stage = json.loads(z.read(root + "newonly_stage_receipt.json"))
            ordered = manifest["ordered_input_paths"]
            check(manifest.get("source_head") == SOURCE_HEAD
                  and stage.get("source_head") == SOURCE_HEAD
                  and str(manifest.get("case")) == case
                  and stage.get("variant") == case
                  and stage.get("retired_native_ion_owners") == 26
                  and stage.get("p3_x_electron", {}).get("removed_native_electron_owners") == 10
                  and len(ordered) == 11
                  and len({Path(p).name for p in ordered}) == 11,
                  "SOURCE_CASE_OR_OWNER_PIN_MISMATCH")
            layers = {}
            for name in ordered:
                rel = safe_relative(name)
                data = z.read(root + rel.as_posix())
                check(digest(data) == stage["layers_after_sha256"][rel.name],
                      "SOURCE_LAYER_SHA_MISMATCH")
                layers[rel.as_posix()] = data
            actual_names = []
            for blob in layers.values():
                actual_names.extend(RATE_RE.findall(blob.decode("utf-8")))
            check(len(actual_names) == 5 and len(set(actual_names)) == 5
                  and set(actual_names) == REQUIRED[case],
                  "PRIVATE_RATE_PRODUCER_PATHS_NOT_EXACT")
            json_path = f"{CHEM}/chemistry/unified_s6_{case}_newonly.json"
            case_json = z.read(root + json_path)
            check(digest(case_json) == stage["json_sha256"],
                  "CASE_JSON_SHA_MISMATCH")
            public_files = {}
            for member in z.infolist():
                if not member.filename.startswith(root + "experiments/") or member.is_dir():
                    continue
                rel = member.filename[len(root):]
                safe_relative(rel)
                mode = (member.external_attr >> 16) & 0o170000
                check(mode != stat.S_IFLNK and member.file_size <= 20_000_000
                      and "/private_rates/" not in rel and rel not in public_files,
                      "UNSAFE_PUBLIC_ARCHIVE_FILE")
                public_files[rel] = z.read(member)
            check(all(public_files.get(k) == v for k, v in layers.items())
                  and public_files.get(json_path) == case_json,
                  "STAGED_SOURCE_LAYER_OR_JSON_CONTENT_MISMATCH")
            cases[case] = {
                "files": public_files,
                "rate_names": sorted(actual_names),
                "source_layers_verified": len(layers),
                "json_sha256": stage["json_sha256"],
            }
    return cases


def stage_case(root: Path, case: str, data: dict, original: dict[str, bytes]) -> dict:
    case_root = root / case
    case_root.mkdir(mode=0o700)
    for name, blob in data["files"].items():
        target = case_root / safe_relative(name)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(blob)
    # This is the *actual* resolved PhysicsLookupTable1D location from the
    # previous S6-417/941 Native --check-input diagnostic error.
    destination = case_root / CHEM / "private_rates"
    check(not destination.exists() and not destination.is_symlink(),
          "PROTECTED_RATE_STAGE_DESTINATION_NOT_NEW")
    destination.mkdir(mode=0o700)
    check(set(data["rate_names"]) == REQUIRED[case],
          "PROTECTED_RATE_CASE_SET_MISMATCH")
    for name in data["rate_names"]:
        check(name in original, "PROTECTED_RATE_NOT_AUTHENTICATED")
        target = destination / name
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(original[name])
        check((target.stat().st_mode & 0o777) == 0o600
              and digest(target.read_bytes()) == EXPECTED[name]
              and validate_rows(target.read_bytes()) == 100,
              "PROTECTED_RATE_SCRATCH_SHA_OR_SHAPE_READBACK_FAILED")
    check({p.name for p in destination.iterdir()} == REQUIRED[case],
          "UNEXPECTED_PROTECTED_RATE_OUTPUT")
    for name, blob in data["files"].items():
        check((case_root / name).read_bytes() == blob,
              "PUBLIC_STAGE_BYTES_CHANGED_WHEN_STAGING_PRIVATE")
    return {
        "case": case, "staged_original_rate_count": 5,
        "staged_rate_sha256_equal_pinned": {n: EXPECTED[n] for n in data["rate_names"]},
        "numeric_data_rows_each": 100,
        "rate_resolved_relative_directory": "private_rates/",
        "rate_file_mode": "0600", "source_layers_sha_verified": 11,
        "json_sha256": data["json_sha256"],
        "untargeted_public_source_bytes_unchanged": True,
        "Native_P2": "NOT_RUN", "D8_NewOnly_dynamic": "HOLD",
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-zip", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--source-head")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if args.self_test:
        checked = negative_selftests()
        print("ISSUE671_PRIVATE_EI_NEGATIVE_ROWS", checked, "OF_5_PASS")
        return 0
    check(args.source_zip is not None and args.receipt is not None
          and args.source_head == SOURCE_HEAD_INTEGRATION,
          "CURRENT_SHARED_SOURCE_HEAD_PIN_MISMATCH")
    receipt = {
        "schema": "issue671.p5_a3.private_original_ei_rate_scratch_handoff.v1",
        "status": "HOLD",
        "historical_source": SOURCE_HEAD,
        "shared_source_head": SOURCE_HEAD_INTEGRATION,
        "input_zip_sha256": P3X_ARTIFACT_SHA,
        "secret_reference_name": "OXYGEN24_RATES_TAR_XZ_B64",
        "historical_rate_SHA_verified": 0,
        "scratch_tmpfs": True, "scratch_removed_after_execution": False,
        "private_bytes_in_logs_artifacts_or_git": False,
        "cases": {},
        "Native_P2": "NOT_RUN", "D8_NewOnly_dynamic": "HOLD",
        "P4_X": "NOT_INTEGRATED", "science": "SCIENCE_HOLD",
    }
    result_code = 1
    try:
        cases = preflight_cases(args.source_zip)  # no protected data consumed yet
        # The approved secret is never passed as an argv value or written as a tar.
        old_rates, original = read_hashed_rows()
        # Require EVERY original SHA and full numeric shape, not only 5 in a case.
        check(set(old_rates) == set(EXPECTED)
              and set(original) == set(EXPECTED)
              and all(old_rates[n]["sha256_match"] and
                      old_rates[n]["numeric_shape_pass"] and
                      old_rates[n]["numeric_data_rows"] == 100 for n in EXPECTED),
              "PROTECTED_ORIGINAL_SIX_SHA_MISMATCH")
        os.environ.pop("PROTECTED_ARCHIVE_B64", None)
        receipt["historical_rate_SHA_verified"] = 6
        check(Path("/dev/shm").is_dir(), "EPHEMERAL_TMPFS_NOT_AVAILABLE")
        with tempfile.TemporaryDirectory(prefix="issue671-private-ei-", dir="/dev/shm") as dirname:
            scratch = Path(dirname)
            check((scratch.stat().st_mode & 0o777) == 0o700,
                  "PROTECTED_SCRATCH_NOT_PRIVATE")
            for case in ("417", "941"):
                receipt["cases"][case] = stage_case(scratch, case, cases[case], original)
        receipt["scratch_removed_after_execution"] = not scratch.exists()
        check(receipt["scratch_removed_after_execution"],
              "PROTECTED_SCRATCH_REMOVAL_FAILURE")
        receipt["status"] = "PASS_SIX_HISTORICAL_SHA_AND_417_941_FIVE_RATE_STAGE"
        result_code = 0
    except SecureHandoffError as e:
        receipt["reason_code"] = str(e)
        receipt["status"] = "HOLD_PRIVATE_EI_STAGE"
    except Exception:
        # NEVER print parser exceptions or secret-bearing paths/bytes.
        receipt["reason_code"] = "PROTECTED_SOURCE_STAGE_OR_READBACK_FAILURE"
        receipt["status"] = "HOLD_PRIVATE_EI_STAGE"
    finally:
        os.environ.pop("PROTECTED_ARCHIVE_B64", None)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print("ISSUE671_PRIVATE_EI_HANDOFF", receipt["status"],
          "source_shas", receipt["historical_rate_SHA_verified"],
          "cases", len(receipt["cases"]))
    return result_code


if __name__ == "__main__":
    sys.exit(main())
