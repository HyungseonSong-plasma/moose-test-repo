"""Prepare an explicitly reviewed, user-LOCAL BOLSIG process-matched source.

This never fetches or commits LXCat data. It requires the original source
and native output plus the operator's explicit omission decision. Output
is a derived third-party data file: keep it local, subject to source rights.
Process count agreement alone is NOT scientific EEPF parity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .bolsig_native_full_process_audit import (
        NativeProcessAuditHold, audit_case, parse_native, parse_source,
    )
except ImportError:
    from bolsig_native_full_process_audit import (
        NativeProcessAuditHold, audit_case, parse_native, parse_source,
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _delimiter(line: str) -> bool:
    value = line.strip()
    return len(value) >= 5 and set(value) == {"-"}


def prepare_matched_source(
    source: Path,
    native: Path,
    output: Path,
    *,
    source_sha256: str,
    native_sha256: str,
    excluded_source_line: int,
    three_body_convention: str,
) -> dict:
    """Require exact original hashes, native process identity and explicit omission."""
    if three_body_convention != "as-tabulated-unscaled":
        raise NativeProcessAuditHold(
            "three-body attachment convention must be explicitly as-tabulated-unscaled "
            "for this native output; this is not a physically approved normalization"
        )
    originals = (source.read_bytes(), native.read_bytes())
    if _sha(originals[0]) != source_sha256 or _sha(originals[1]) != native_sha256:
        raise NativeProcessAuditHold("raw source/native SHA256 mismatch")
    if output.resolve() in {source.resolve(), native.resolve()} or output.is_symlink():
        raise NativeProcessAuditHold("refusing to overwrite original source/native or a symlink")

    audit = audit_case(source, native)
    omitted = audit.get("inferred_omitted_source_process")
    if (audit["status"] != "HOLD_NATIVE_OMITTED_PROCESS" or
            not audit.get("omission_unique_by_rate_evidence") or
            not omitted or omitted["line"] != excluded_source_line):
        raise NativeProcessAuditHold(
            "caller-specified excluded source line does not match the independent native rate audit"
        )
    process = parse_source(source)
    native_rates, _, _ = parse_native(native)
    matches = [p for p in process if p.line != excluded_source_line]
    if len(matches) != len(native_rates) or any(
        (p.gas, p.kind) != (r.gas, r.kind)
        for p, r in zip(matches, native_rates)
    ):
        raise NativeProcessAuditHold("incomplete source/native process sequence match")

    lines = originals[0].decode("utf-8").splitlines(keepends=True)
    blocks = []
    for rec in matches:
        index = rec.line - 1
        if not (0 <= index < len(lines) and lines[index].strip() == rec.kind):
            raise NativeProcessAuditHold("source line identity changed")
        j = index + 1
        n_delimiters = 0
        while j < len(lines):
            if _delimiter(lines[j]):
                n_delimiters += 1
                if n_delimiters == 2:
                    break
            j += 1
        if j == len(lines):
            raise NativeProcessAuditHold("collision block missing closing delimiter")
        blocks.append("".join(lines[index:j + 1]).rstrip("\r\n") + "\n")
    # No reordering, numerical extrapolation, threshold repair or unit scaling.
    # The native ledger order is enforced above, and every other native
    # process stays present as a byte-preserving collision block.
    output_bytes = ("\n".join(blocks) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(output_bytes)
    return {
        "status": "LOCAL_MATCHED_INPUT_PREPARED_SCIENCE_HOLD",
        "scientific_acceptance": "HOLD_THREE_BODY_CONVENTION_AND_FULL_KINETIC_OPERATOR",
        "original_source_sha256": source_sha256,
        "original_native_sha256": native_sha256,
        "selected_process_count": len(matches),
        "excluded_source_line": excluded_source_line,
        "excluded_process": omitted,
        "three_body_attachment_convention": three_body_convention,
        "local_output_sha256": _sha(output_bytes),
        "local_output_bytes": len(output_bytes),
        "model_caveats": [
            "Derived data inherit third-party source rights: do not commit",
            "As-tabulated three-body value reproduces printed rate, not physical density convention",
            "No automatic cross-section extrapolation or C++ solver parity claim",
            "An excluded process is explicitly identified and traceable",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cross-sections", type=Path, required=True)
    p.add_argument("--native-output", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source-sha256", required=True)
    p.add_argument("--native-sha256", required=True)
    p.add_argument("--exclude-source-line", type=int, required=True)
    p.add_argument("--three-body-convention", required=True)
    a = p.parse_args()
    try:
        result = prepare_matched_source(
            a.cross_sections, a.native_output, a.output,
            source_sha256=a.source_sha256, native_sha256=a.native_sha256,
            excluded_source_line=a.exclude_source_line,
            three_body_convention=a.three_body_convention,
        )
    except (OSError, UnicodeError, NativeProcessAuditHold) as exc:
        print("BOLSIG_LOCAL_SOURCE_PREFLIGHT_HOLD:", exc)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    # This prepares a local data artifact; its numerical physics remains HOLD.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
