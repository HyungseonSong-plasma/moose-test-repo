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
            result[parts[0]] = {
                "file": parts[0],
                "sha256_expected": EXPECTED[parts[0]],
                "sha256_observed_if_equal": actual if match else None,
                "sha256_match": match,
                "numeric_data_rows": numeric_rows,
                "numeric_shape_pass": shape_ok,
            }
    return result


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


def main() -> int:
    output = Path(os.environ["RUNNER_TEMP"]) / "issue667_private_ei_rate_sha_receipt.json"
    result = {
        "schema": "issue667.private_ei_rate_secure_hash_only.v1",
        "task": "P1-B6_AND_P1-C6_EI_ORIGINAL_RATE_SHA",
        "source_pr": 665,
        "source_head": SOURCE_HEAD,
        "historical_source_head": HISTORICAL_HEAD,
        "source_secret_reference": "OXYGEN24_RATES_TAR_XZ_B64",
        "provenance": "repo-secured original Oxygen24 kinetic rates archive used by historical Issue477 workflow",
        "mode": "IN_MEMORY_SECRET_BORNE_REHASH",
        "status": "HOLD",
        "files": [],
        "required_B6": list(REQUIRED_B6),
        "private_bytes_in_artifact": False,
        "private_bytes_in_logs": False,
        "mismatch_digest_in_artifact": False,
        "Native_P2": "NOT_RUN",
        "Native_P3": "NOT_RUN",
        "Native_P4": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }
    try:
        result["negative_shape_tests_rejected"] = negative_selftests()
        observed = read_hashed_rows()
        for name in EXPECTED:
            result["files"].append(
                observed.get(name, {
                    "file": name, "sha256_expected": EXPECTED[name],
                    "sha256_observed_if_equal": None, "sha256_match": False,
                    "numeric_shape_pass": False, "reason": "NOT_IN_PROTECTED_ARCHIVE",
                })
            )
        b6 = all(
            observed.get(name, {}).get("sha256_match") is True and
            observed[name].get("numeric_shape_pass") is True
            for name in REQUIRED_B6
        )
        all_six = all(row["sha256_match"] and row["numeric_shape_pass"]
                      for row in result["files"])
        result["required_B6_status"] = "PASS" if b6 else "HOLD"
        result["optional_extra_status"] = "PASS" if all_six else "HOLD"
        result["status"] = ("PASS_ALL_6_ORIGINAL_PRIVATE_EI_SHA" if all_six
                            else "PASS_B6_3_ONLY_EXTRAS_HOLD" if b6
                            else "HOLD_B6_PRIVATE_SHA")
    except Exception as exc:
        # Never print actual exception messages from parsers of protected data.
        result["reason_code"] = type(exc).__name__
        result["status"] = "HOLD_SECURE_PRIVATE_SOURCE_OR_SHAPE"
    output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("ISSUE667_PRIVATE_EI_SECURE_SHA", result["status"],
          "matched", sum(row.get("sha256_match",False) for row in result["files"]),
          "of", len(EXPECTED))
    return 0 if result.get("required_B6_status") == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
