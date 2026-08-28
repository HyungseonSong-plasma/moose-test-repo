"""Managed PF-3 targeted probe for QPXThermalDiffusionMaterial.

The probe temporarily adds MOOSE TIME_SECTION instrumentation to the accepted
heavy-transport source, rebuilds QPX, runs one PROFILE measurement, analyzes the
raw PerfGraph hierarchy, and restores/rebuilds the production source in a
finally block.  Physics, mesh, timestep, solver type, and tolerances are not
changed by this diagnostic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ACCEPTED_SOURCE_SHA256 = "4533a3a2fe0d77f3d85ca171f9093907a76514dd024c5392c08dd8d17a2f4b7e"
ACCEPTED_HEADER_SHA256 = "8f97db663781c5788e18bb98cca284a9173597a2b7bfe44f148ca2beef9391c5"
SOURCE_RELATIVE = Path("src/materials/QPXThermalDiffusionMaterial.C")
HEADER_RELATIVE = Path("include/materials/QPXThermalDiffusionMaterial.h")
MARKER_PREFIX = "qpx_transport_"
TIMER_NAMES = {
    "evaluate": "qpx_transport_evaluate",
    "collision_pairs": "qpx_transport_collision_pairs",
    "dmix": "qpx_transport_dmix",
    "functor_DT": "qpx_transport_functor_DT",
    "functor_kT": "qpx_transport_functor_kT",
    "functor_Dmix": "qpx_transport_functor_Dmix",
}


class ProbeError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _mask_cpp(text: str) -> str:
    """Mask comments and quoted strings while preserving character offsets."""

    out = list(text)
    i = 0
    state = "code"
    quote = ""
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if state == "code":
            if c == "/" and n == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "line_comment"
                continue
            if c == "/" and n == "*":
                out[i] = out[i + 1] = " "
                i += 2
                state = "block_comment"
                continue
            if c in {'"', "'"}:
                quote = c
                out[i] = " "
                i += 1
                state = "string"
                continue
            i += 1
            continue
        if state == "line_comment":
            if c == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
            continue
        if state == "block_comment":
            if c == "*" and n == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "code"
            else:
                if c != "\n":
                    out[i] = " "
                i += 1
            continue
        if state == "string":
            if c == "\\":
                out[i] = " "
                if i + 1 < len(text):
                    if text[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                else:
                    i += 1
                continue
            out[i] = " " if c != "\n" else "\n"
            i += 1
            if c == quote:
                state = "code"
    return "".join(out)


def _match_forward(masked: str, open_idx: int, left: str, right: str) -> int:
    if masked[open_idx] != left:
        raise ProbeError(f"expected {left!r} at index {open_idx}")
    depth = 0
    for i in range(open_idx, len(masked)):
        c = masked[i]
        if c == left:
            depth += 1
        elif c == right:
            depth -= 1
            if depth == 0:
                return i
    raise ProbeError(f"unmatched {left!r} at index {open_idx}")


def _match_backward(masked: str, close_idx: int, left: str, right: str) -> int:
    if masked[close_idx] != right:
        raise ProbeError(f"expected {right!r} at index {close_idx}")
    depth = 0
    for i in range(close_idx, -1, -1):
        c = masked[i]
        if c == right:
            depth += 1
        elif c == left:
            depth -= 1
            if depth == 0:
                return i
    raise ProbeError(f"unmatched {right!r} at index {close_idx}")


def _find_function_body(text: str, signature: str) -> tuple[int, int]:
    masked = _mask_cpp(text)
    idx = masked.find(signature)
    if idx < 0:
        raise ProbeError(f"missing function signature anchor: {signature}")
    brace = masked.find("{", idx)
    semi = masked.find(";", idx)
    if brace < 0 or (semi >= 0 and semi < brace):
        raise ProbeError(f"could not find function body for {signature}")
    return brace, _match_forward(masked, brace, "{", "}")


def _block_spans(masked: str) -> list[tuple[int, int]]:
    stack: list[int] = []
    spans: list[tuple[int, int]] = []
    for i, c in enumerate(masked):
        if c == "{":
            stack.append(i)
        elif c == "}":
            if not stack:
                raise ProbeError("unbalanced C++ braces")
            spans.append((stack.pop(), i))
    if stack:
        raise ProbeError("unbalanced C++ braces")
    return spans


def _header_keyword(masked: str, brace_idx: int) -> str | None:
    i = brace_idx - 1
    while i >= 0 and masked[i].isspace():
        i -= 1
    if i < 0 or masked[i] != ")":
        return None
    open_paren = _match_backward(masked, i, "(", ")")
    j = open_paren - 1
    while j >= 0 and masked[j].isspace():
        j -= 1
    end = j + 1
    while j >= 0 and (masked[j].isalnum() or masked[j] == "_"):
        j -= 1
    return masked[j + 1 : end] or None


def _enclosing_for_blocks(text: str, anchor_pattern: str) -> list[tuple[int, int]]:
    masked = _mask_cpp(text)
    match = re.search(anchor_pattern, masked, re.MULTILINE)
    if not match:
        raise ProbeError(f"missing instrumentation anchor: {anchor_pattern}")
    pos = match.start()
    spans = [span for span in _block_spans(masked) if span[0] < pos < span[1]]
    spans = [span for span in spans if _header_keyword(masked, span[0]) == "for"]
    spans.sort(key=lambda span: span[1] - span[0])
    return spans


def _find_add_functor_lambda_body(text: str, token: str) -> tuple[int, int]:
    masked = _mask_cpp(text)
    starts = [
        match.start()
        for match in re.finditer(r"addFunctorProperty\s*<\s*ADReal\s*>\s*\(", masked)
    ]
    matches: list[tuple[int, int]] = []
    for start in starts:
        paren = masked.find("(", start)
        end = _match_forward(masked, paren, "(", ")")
        if token not in masked[start : end + 1]:
            continue
        lambda_idx = masked.find("[", paren, end)
        if lambda_idx < 0:
            continue
        brace = masked.find("{", lambda_idx, end)
        if brace < 0:
            continue
        close = _match_forward(masked, brace, "{", "}")
        if close <= end:
            matches.append((brace, close))
    if len(matches) != 1:
        raise ProbeError(
            f"expected one addFunctorProperty lambda for {token}, found {len(matches)}"
        )
    return matches[0]


def _timer_after_brace(text: str, brace_idx: int, name: str, level: int) -> tuple[int, str]:
    line_start = text.rfind("\n", 0, brace_idx) + 1
    match = re.match(r"[ \t]*", text[line_start:brace_idx])
    indent = (match.group(0) if match else "") + "  "
    if brace_idx + 1 < len(text) and text[brace_idx + 1] == "\n":
        payload = f'\n{indent}TIME_SECTION("{name}", {level});'
    else:
        payload = f'\n{indent}TIME_SECTION("{name}", {level});\n{indent}'
    return brace_idx + 1, payload


def _wrap_for_timer(
    text: str, span: tuple[int, int], name: str, level: int
) -> list[tuple[int, str]]:
    open_idx, close_idx = span
    masked = _mask_cpp(text)
    i = open_idx - 1
    while i >= 0 and masked[i].isspace():
        i -= 1
    if i < 0 or masked[i] != ")":
        raise ProbeError("for-loop instrumentation expected ')' before body")
    open_paren = _match_backward(masked, i, "(", ")")
    j = open_paren - 1
    while j >= 0 and masked[j].isspace():
        j -= 1
    end = j + 1
    while j >= 0 and (masked[j].isalnum() or masked[j] == "_"):
        j -= 1
    if masked[j + 1 : end] != "for":
        raise ProbeError("instrumentation span is not a for-loop body")
    for_start = j + 1
    line_start = text.rfind("\n", 0, for_start) + 1
    match = re.match(r"[ \t]*", text[line_start:for_start])
    indent = match.group(0) if match else ""
    return [
        (line_start, f'{indent}{{\n{indent}  TIME_SECTION("{name}", {level});\n'),
        (close_idx + 1, f"\n{indent}}}"),
    ]


def instrument_source(text: str) -> tuple[str, dict[str, Any]]:
    """Return an instrumented copy; fail rather than guess when anchors drift."""

    if MARKER_PREFIX in text:
        raise ProbeError("source already contains qpx transport instrumentation markers")
    required = [
        "QPXThermalDiffusionMaterial::evaluate",
        "_D_T_names",
        "_kT_names",
        "_D_mix_names",
        "nDij",
        "one_minus_Y",
    ]
    missing = [token for token in required if token not in text]
    if missing:
        raise ProbeError("source contract missing required anchors: " + ", ".join(missing))

    insertions: list[tuple[int, str]] = []
    body_open, _ = _find_function_body(text, "QPXThermalDiffusionMaterial::evaluate")
    insertions.append(_timer_after_brace(text, body_open, TIMER_NAMES["evaluate"], 1))

    for key, token in {
        "functor_DT": "_D_T_names",
        "functor_kT": "_kT_names",
        "functor_Dmix": "_D_mix_names",
    }.items():
        brace, _ = _find_add_functor_lambda_body(text, token)
        insertions.append(_timer_after_brace(text, brace, TIMER_NAMES[key], 2))

    dmix_for = _enclosing_for_blocks(
        text, r"one_minus_Y\s*=\s*1\.0\s*-\s*Y\s*\[\s*i\s*\]"
    )
    if not dmix_for:
        raise ProbeError("could not identify D_mix outer loop")
    dmix_span = dmix_for[0]
    insertions.extend(_wrap_for_timer(text, dmix_span, TIMER_NAMES["dmix"], 2))

    pair_for = _enclosing_for_blocks(
        text, r"nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*="
    )
    if len(pair_for) < 2:
        raise ProbeError("could not identify nested pair-collision loops")
    pair_span = pair_for[1]
    insertions.extend(
        _wrap_for_timer(text, pair_span, TIMER_NAMES["collision_pairs"], 2)
    )

    if "PerfGraphInterface.h" not in text:
        include = '#include "PerfGraphInterface.h"\n'
        matches = list(re.finditer(r"^#include[^\n]*\n", text, re.MULTILINE))
        insertions.append((matches[-1].end() if matches else 0, include))

    instrumented = text
    for idx, payload in sorted(insertions, key=lambda item: item[0], reverse=True):
        instrumented = instrumented[:idx] + payload + instrumented[idx:]

    if instrumented == text:
        raise ProbeError("instrumentation produced no source change")
    for name in TIMER_NAMES.values():
        if instrumented.count(name) != 1:
            raise ProbeError(f"timer marker {name} count is not exactly one")
    return instrumented, {
        "timers": dict(TIMER_NAMES),
        "dmix_span": list(dmix_span),
        "collision_pair_span": list(pair_span),
    }


def _walk_perfgraph(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    reporters = payload.get("reporters", {})
    names = [
        name
        for name, meta in reporters.items()
        if isinstance(meta, dict) and meta.get("type") == "PerfGraphReporter"
    ]
    if len(names) != 1:
        raise ProbeError(f"expected one PerfGraphReporter, found {len(names)}")
    steps = payload.get("time_steps")
    if not isinstance(steps, list) or not steps:
        raise ProbeError("PerfGraph JSON has no time_steps")
    reporter = steps[-1].get(names[0], {})
    graph = reporter.get("graph")
    if not isinstance(graph, dict) or len(graph) != 1:
        raise ProbeError("PerfGraph graph must have one root")
    version = reporter.get("version", 0)
    rows: list[dict[str, Any]] = []

    def walk(name: str, node: dict[str, Any], ancestors: tuple[str, ...]) -> float:
        self_seconds = float(node.get("time", 0.0))
        if version == 0:
            reserved = {"level", "time", "num_calls", "memory"}
            children = {
                key: value
                for key, value in node.items()
                if key not in reserved and isinstance(value, dict)
            }
        else:
            children = node.get("children", {})
            if not isinstance(children, dict):
                children = {}
        child_total = 0.0
        for child_name, child in children.items():
            if isinstance(child, dict):
                child_total += walk(child_name, child, ancestors + (name,))
        inclusive = self_seconds + child_total
        rows.append(
            {
                "name": name,
                "path": list(ancestors + (name,)),
                "self_seconds": self_seconds,
                "inclusive_seconds": inclusive,
                "num_calls": int(node.get("num_calls", 0)),
            }
        )
        return inclusive

    root_name, root = next(iter(graph.items()))
    walk(root_name, root, tuple())
    return rows


def _sum_timer(
    rows: list[dict[str, Any]], timer: str, *, jacobian_only: bool = False
) -> dict[str, float | int]:
    selected = []
    for row in rows:
        if timer not in row["name"]:
            continue
        if jacobian_only and not any(
            "jacobian" in part.lower() for part in row["path"][:-1]
        ):
            continue
        selected.append(row)
    return {
        "self_seconds": sum(float(row["self_seconds"]) for row in selected),
        "inclusive_seconds": sum(float(row["inclusive_seconds"]) for row in selected),
        "num_calls": sum(int(row["num_calls"]) for row in selected),
        "node_count": len(selected),
    }


def analyze_probe(profile_result: dict[str, Any], perfgraph_path: Path) -> dict[str, Any]:
    rows = _walk_perfgraph(perfgraph_path)
    wall = float(profile_result.get("performance", {}).get("wall_seconds") or 0.0)
    if wall <= 0:
        raise ProbeError("profile wall time missing")

    timers = {key: _sum_timer(rows, name) for key, name in TIMER_NAMES.items()}
    jac_timers = {
        key: _sum_timer(rows, name, jacobian_only=True)
        for key, name in TIMER_NAMES.items()
    }
    if timers["evaluate"]["node_count"] == 0:
        raise ProbeError("instrumented evaluate timer was not captured")

    jacobian_seconds = 0.0
    petsc = profile_result.get("performance", {}).get("petsc")
    if isinstance(petsc, dict):
        for row in petsc.get("rows", []):
            if (
                isinstance(row, dict)
                and row.get("Event Name") == "SNESJacobianEval"
                and row.get("Rank") in (None, "", 0, "0", 0.0)
            ):
                try:
                    jacobian_seconds += float(row.get("Time", 0.0))
                except (TypeError, ValueError):
                    pass
    if jacobian_seconds <= 0:
        jacobian_seconds = sum(
            float(row["self_seconds"])
            for row in rows
            if "jacobian" in row["name"].lower()
        )

    evaluate_all = float(timers["evaluate"]["inclusive_seconds"])
    evaluate_jac = float(jac_timers["evaluate"]["inclusive_seconds"])
    fraction_wall = evaluate_all / wall
    fraction_jac = evaluate_jac / jacobian_seconds if jacobian_seconds > 0 else None

    if fraction_jac is not None and fraction_jac >= 0.50:
        outcome = "APPLICATION_EVALUATION_INSIDE_JACOBIAN"
        confidence = "high" if fraction_jac >= 0.70 else "medium"
        reason = (
            f"instrumented heavy-transport evaluate accounts for {fraction_jac:.1%} "
            "of Jacobian time"
        )
    elif fraction_jac is not None and fraction_jac <= 0.20:
        outcome = "JACOBIAN_AD_RETAINED"
        confidence = "high" if fraction_jac <= 0.10 else "medium"
        reason = (
            f"instrumented heavy-transport evaluate accounts for only {fraction_jac:.1%} "
            "of Jacobian time"
        )
    elif fraction_wall >= 0.25:
        outcome = "APPLICATION_EVALUATION_MATERIAL"
        confidence = "medium"
        reason = (
            f"instrumented heavy-transport evaluate accounts for {fraction_wall:.1%} "
            "of wall time"
        )
    else:
        outcome = "MIXED_OR_FURTHER_LOCALIZATION"
        confidence = "low"
        reason = (
            "heavy-transport evaluate is material but not sufficiently separated "
            "from remaining Jacobian cost"
        )

    return {
        "analysis_status": "PASS",
        "outcome": outcome,
        "confidence": confidence,
        "reason": reason,
        "wall_seconds": wall,
        "jacobian_seconds": jacobian_seconds,
        "evaluate_fraction_of_wall": fraction_wall,
        "evaluate_fraction_of_jacobian": fraction_jac,
        "evaluate_self_seconds": float(timers["evaluate"]["self_seconds"]),
        "evaluate_inclusive_seconds": evaluate_all,
        "evaluate_jacobian_context_seconds": evaluate_jac,
        "collision_pair_seconds": float(
            timers["collision_pairs"]["inclusive_seconds"]
        ),
        "dmix_seconds": float(timers["dmix"]["inclusive_seconds"]),
        "timers": timers,
        "jacobian_context_timers": jac_timers,
        "functor_call_counts": {
            key: int(timers[key]["num_calls"])
            for key in ("functor_DT", "functor_kT", "functor_Dmix", "evaluate")
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ProbeError(f"missing {label}: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ProbeError(f"{label} must be a JSON object: {path}")
    return payload


def _stream_command(command: list[str], *, cwd: Path, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print("PF3_TRANSPORT_COMMAND:", shlex.join(command))
    with log_path.open("w") as log:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log.write(line)
            log.flush()
        return process.wait()


def _create_probe_root(results_root: Path, case_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", case_id).strip("_") or "case"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = results_root / f"pf3_transport_probe_{safe}_{stamp}"
    index = 1
    while root.exists():
        root = results_root / f"pf3_transport_probe_{safe}_{stamp}_{index:02d}"
        index += 1
    root.mkdir(parents=True)
    return root


def _resolve_case_manifest(smoke_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_manifest = _load_json(
        smoke_root / "profile_manifest.json", "PF-1 profile manifest"
    )
    baseline_profile = _load_json(
        smoke_root / "profile" / "result.json", "PF-1 profile result"
    )
    case = profile_manifest.get("case")
    if not isinstance(case, dict):
        raise ProbeError("PF-1 profile manifest has no case object")
    case_dir = Path(str(case.get("directory", ""))).expanduser()
    input_name = str(case.get("input", "input.i"))
    if case_dir.is_dir() and (case_dir / input_name).is_file():
        return profile_manifest, baseline_profile

    repo_root = Path(__file__).resolve().parents[1]
    case_id = str(profile_manifest.get("case_id", ""))
    candidate = repo_root / "tests" / case_id
    if candidate.is_dir() and (candidate / input_name).is_file():
        profile_manifest = json.loads(json.dumps(profile_manifest))
        profile_manifest["case"]["directory"] = str(candidate.resolve())
        return profile_manifest, baseline_profile
    raise ProbeError(
        "PF-1 case directory is unavailable and no matching current tests/<case_id> exists"
    )


def _parity_checks(baseline: dict[str, Any], probe: dict[str, Any]) -> dict[str, bool]:
    return {
        "same_input_sha": baseline.get("identity", {}).get("input_sha256")
        == probe.get("identity", {}).get("input_sha256"),
        "same_dofs": baseline.get("problem", {}).get("dofs")
        == probe.get("problem", {}).get("dofs"),
        "same_nonlinear_iterations": baseline.get("work", {}).get(
            "nonlinear_iterations"
        )
        == probe.get("work", {}).get("nonlinear_iterations"),
        "same_linear_iterations": baseline.get("work", {}).get("linear_iterations")
        == probe.get("work", {}).get("linear_iterations"),
        "same_residual_evaluations": baseline.get("work", {}).get(
            "residual_evaluations"
        )
        == probe.get("work", {}).get("residual_evaluations"),
    }


def restore_probe(run_root: Path, executable: Path | None = None) -> int:
    """Emergency recovery for a probe interrupted before its finally block."""

    run_root = Path(run_root).expanduser().resolve()
    state = _load_json(run_root / "probe_state.json", "probe state")
    source_path = Path(state["source_path"])
    backup_source = run_root / "source_original.C"
    if not backup_source.is_file():
        raise ProbeError(f"missing source backup: {backup_source}")
    source_path.write_bytes(backup_source.read_bytes())
    os.utime(source_path, None)
    source_ok = sha256_file(source_path) == state.get("source_sha_before")

    exe_path = (
        Path(executable).resolve()
        if executable is not None
        else Path(state["executable_path"])
    )
    backup_exe = run_root / "qpx-opt.original"
    binary_ok = True
    if backup_exe.is_file():
        shutil.copy2(backup_exe, exe_path)
        binary_ok = sha256_file(exe_path) == state.get("executable_sha_before")

    state["emergency_restore"] = {
        "source_restored": source_ok,
        "binary_restored": binary_ok,
        "restored_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(run_root / "probe_state.json", state)
    print("PF3_TRANSPORT_RESTORE:", "PASS" if source_ok and binary_ok else "FAIL")
    return 0 if source_ok and binary_ok else 2


def run_managed_probe(
    *,
    executable_arg: str | Path | None,
    smoke_root_arg: Path | None = None,
    source_arg: Path | None = None,
    build_command_arg: str | None = None,
    jobs: int | None = None,
    allow_source_sha_mismatch: bool = False,
) -> int:
    from .performance_core import run_measurement
    from .performance_investigation import discover_latest_smoke
    from .performance_smoke import default_results_root
    from .runtime import resolve_executable, validate_executable

    exe = resolve_executable(executable_arg)
    validate_executable(exe)
    qpx_root = exe.parent.resolve()
    results_root = default_results_root(exe)
    results_root.mkdir(parents=True, exist_ok=True)
    smoke_root = (
        Path(smoke_root_arg).expanduser().resolve()
        if smoke_root_arg is not None
        else discover_latest_smoke(results_root)
    )
    profile_manifest, baseline_profile = _resolve_case_manifest(smoke_root)
    case_id = str(profile_manifest.get("case_id") or smoke_root.name)
    run_root = _create_probe_root(results_root, case_id)
    print(f"PF3_TRANSPORT_PROBE_ROOT: {run_root}")
    print(f"PF3_TRANSPORT_BASELINE_ROOT: {smoke_root}")

    source_path = (
        Path(source_arg).expanduser().resolve()
        if source_arg is not None
        else qpx_root / SOURCE_RELATIVE
    )
    header_path = qpx_root / HEADER_RELATIVE
    if not source_path.is_file():
        raise ProbeError(f"transport source does not exist: {source_path}")
    if not header_path.is_file():
        raise ProbeError(f"transport header does not exist: {header_path}")

    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    source_sha = sha256_bytes(source_bytes)
    header_sha = sha256_file(header_path)
    if not allow_source_sha_mismatch and source_sha != ACCEPTED_SOURCE_SHA256:
        raise ProbeError(
            "QPXThermalDiffusionMaterial.C SHA does not match the accepted frozen source; "
            f"expected={ACCEPTED_SOURCE_SHA256} actual={source_sha}"
        )
    if not allow_source_sha_mismatch and header_sha != ACCEPTED_HEADER_SHA256:
        raise ProbeError(
            "QPXThermalDiffusionMaterial.h SHA does not match the accepted frozen source; "
            f"expected={ACCEPTED_HEADER_SHA256} actual={header_sha}"
        )

    instrumented_text, instrumentation = instrument_source(source_text)
    instrumented_bytes = instrumented_text.encode("utf-8")
    instrumented_sha = sha256_bytes(instrumented_bytes)
    shutil.copy2(source_path, run_root / "source_original.C")
    (run_root / "source_instrumented.C").write_bytes(instrumented_bytes)
    shutil.copy2(exe, run_root / "qpx-opt.original")

    before_exe_sha = sha256_file(exe)
    state: dict[str, Any] = {
        "schema_version": 1,
        "status": "PREPARED",
        "source_path": str(source_path),
        "source_sha_before": source_sha,
        "source_sha_instrumented": instrumented_sha,
        "header_path": str(header_path),
        "header_sha": header_sha,
        "accepted_source_sha": ACCEPTED_SOURCE_SHA256,
        "accepted_header_sha": ACCEPTED_HEADER_SHA256,
        "executable_path": str(exe),
        "executable_sha_before": before_exe_sha,
        "smoke_root": str(smoke_root),
        "instrumentation": instrumentation,
    }
    _write_json(run_root / "probe_state.json", state)

    jobs_value = jobs if jobs is not None else max(1, min(8, os.cpu_count() or 1))
    build_command = (
        shlex.split(build_command_arg)
        if build_command_arg
        else ["make", f"-j{jobs_value}"]
    )
    if not build_command:
        raise ProbeError("build command is empty")

    instrument_build_rc: int | None = None
    profile_rc: int | None = None
    restore_build_rc: int | None = None
    restored_source_ok = False
    restored_binary_ok = False
    summary: dict[str, Any] = {
        "schema_version": 1,
        "case_id": case_id,
        "probe_root": str(run_root),
        "baseline_smoke_root": str(smoke_root),
    }

    try:
        source_path.write_bytes(instrumented_bytes)
        state["status"] = "SOURCE_INSTRUMENTED"
        _write_json(run_root / "probe_state.json", state)
        print(f"PF3_TRANSPORT_SOURCE_SHA: {source_sha}")
        print(f"PF3_TRANSPORT_INSTRUMENTED_SHA: {instrumented_sha}")

        instrument_build_rc = _stream_command(
            build_command,
            cwd=qpx_root,
            log_path=run_root / "build_instrumented.log",
        )
        if instrument_build_rc != 0:
            raise ProbeError(
                f"instrumented QPX build failed with return code {instrument_build_rc}"
            )
        state["status"] = "INSTRUMENTED_BUILD_PASS"
        state["executable_sha_instrumented"] = sha256_file(exe)
        _write_json(run_root / "probe_state.json", state)
        print("PF3_TRANSPORT_BUILD: PASS")

        probe_manifest = json.loads(json.dumps(profile_manifest))
        probe_manifest["experiment_id"] = "pf3-transport-targeted-probe"
        probe_manifest["mode"] = "PROFILE"
        probe_manifest.setdefault("collectors", {})["perfgraph"] = True
        probe_manifest["collectors"]["petsc_log"] = True
        probe_manifest["stream_output"] = True
        manifest_path = run_root / "profile_manifest.json"
        _write_json(manifest_path, probe_manifest)
        profile_rc = run_measurement(
            manifest_path, executable=exe, out_dir=run_root / "profile"
        )
        if profile_rc != 0:
            raise ProbeError(
                f"instrumented PROFILE run failed with return code {profile_rc}"
            )
        probe_result = _load_json(
            run_root / "profile" / "result.json", "probe profile result"
        )
        if probe_result.get("validation", {}).get("status") != "P2_PASS_P3_PASS":
            raise ProbeError("instrumented PROFILE result is not P2_PASS_P3_PASS")
        perfgraph_value = probe_result.get("evidence", {}).get("perfgraph_json")
        if not isinstance(perfgraph_value, str) or not perfgraph_value:
            raise ProbeError("instrumented PROFILE result has no PerfGraph JSON evidence")

        analysis = analyze_probe(probe_result, Path(perfgraph_value))
        parity = _parity_checks(baseline_profile, probe_result)
        baseline_wall = float(
            baseline_profile.get("performance", {}).get("wall_seconds") or 0.0
        )
        probe_wall = float(probe_result.get("performance", {}).get("wall_seconds") or 0.0)
        profile_ratio = probe_wall / baseline_wall if baseline_wall > 0 else None
        analysis["parity_checks"] = parity
        analysis["instrumented_to_baseline_profile_ratio"] = profile_ratio
        analysis["instrumentation_overhead_warning"] = (
            profile_ratio is not None and profile_ratio > 1.25
        )
        if not all(parity.values()):
            analysis["analysis_status"] = "EVIDENCE_PARITY_FAIL"
        summary.update(
            {
                "analysis": analysis,
                "profile_returncode": profile_rc,
                "profile_result": str(run_root / "profile" / "result.json"),
                "source_sha_before": source_sha,
                "source_sha_instrumented": instrumented_sha,
                "executable_sha_before": before_exe_sha,
                "executable_sha_instrumented": state.get(
                    "executable_sha_instrumented"
                ),
            }
        )
        state["status"] = "PROFILE_ANALYZED"
        _write_json(run_root / "probe_state.json", state)
    except Exception as exc:
        summary["error"] = str(exc)
        print(f"PF3_TRANSPORT_PROBE_ERROR: {exc}", file=sys.stderr)
    finally:
        source_path.write_bytes(source_bytes)
        os.utime(source_path, None)
        restored_source_ok = sha256_file(source_path) == source_sha
        print(
            "PF3_TRANSPORT_SOURCE_RESTORE:",
            "PASS" if restored_source_ok else "FAIL",
        )
        if restored_source_ok:
            restore_build_rc = _stream_command(
                build_command,
                cwd=qpx_root,
                log_path=run_root / "build_restored.log",
            )
        if restore_build_rc == 0:
            restored_binary_ok = True
        else:
            try:
                shutil.copy2(run_root / "qpx-opt.original", exe)
                restored_binary_ok = sha256_file(exe) == before_exe_sha
            except OSError:
                restored_binary_ok = False
        state["status"] = (
            "RESTORED"
            if restored_source_ok and restored_binary_ok
            else "RESTORE_FAIL"
        )
        state["restore_build_returncode"] = restore_build_rc
        state["source_restored"] = restored_source_ok
        state["binary_restored_or_rebuilt"] = restored_binary_ok
        state["executable_sha_after_restore"] = (
            sha256_file(exe) if exe.is_file() else None
        )
        _write_json(run_root / "probe_state.json", state)
        summary["instrumented_build_returncode"] = instrument_build_rc
        summary["restore_build_returncode"] = restore_build_rc
        summary["source_restored"] = restored_source_ok
        summary["binary_restored_or_rebuilt"] = restored_binary_ok
        _write_json(run_root / "probe_summary.json", summary)
        print(
            "PF3_TRANSPORT_RESTORE:",
            "PASS" if restored_source_ok and restored_binary_ok else "FAIL",
        )

    analysis = summary.get("analysis")
    if not isinstance(analysis, dict):
        print(f"PF3_TRANSPORT_SUMMARY: {run_root / 'probe_summary.json'}")
        return 2
    print("PF3_TRANSPORT_ANALYSIS_STATUS:", analysis.get("analysis_status"))
    print("PF3_TRANSPORT_OUTCOME:", analysis.get("outcome"))
    print("PF3_TRANSPORT_CONFIDENCE:", analysis.get("confidence"))
    print("PF3_TRANSPORT_REASON:", analysis.get("reason"))
    fraction_jac = analysis.get("evaluate_fraction_of_jacobian")
    fraction_wall = analysis.get("evaluate_fraction_of_wall")
    print(
        "PF3_TRANSPORT_EVALUATE_JACOBIAN_FRACTION:",
        f"{fraction_jac:.4f}" if isinstance(fraction_jac, float) else fraction_jac,
    )
    print(
        "PF3_TRANSPORT_EVALUATE_WALL_FRACTION:",
        f"{fraction_wall:.4f}" if isinstance(fraction_wall, float) else fraction_wall,
    )
    print(
        "PF3_TRANSPORT_COLLISION_SECONDS:", analysis.get("collision_pair_seconds")
    )
    print("PF3_TRANSPORT_DMIX_SECONDS:", analysis.get("dmix_seconds"))
    print(
        "PF3_TRANSPORT_EVALUATE_SELF_SECONDS:",
        analysis.get("evaluate_self_seconds"),
    )
    print(
        "PF3_TRANSPORT_FUNCTOR_CALLS:",
        json.dumps(analysis.get("functor_call_counts", {}), sort_keys=True),
    )
    print(
        "PF3_TRANSPORT_PROFILE_RATIO:",
        analysis.get("instrumented_to_baseline_profile_ratio"),
    )
    print(f"PF3_TRANSPORT_SUMMARY: {run_root / 'probe_summary.json'}")
    ok = (
        analysis.get("analysis_status") == "PASS"
        and restored_source_ok
        and restored_binary_ok
    )
    return 0 if ok else 2


def _synthetic_source() -> str:
    return '''#include "SomeHeader.h"
QPXThermalDiffusionMaterial::QPXThermalDiffusionMaterial()
{
  addFunctorProperty<ADReal>(_D_T_names[i], [this, i](const auto & r, const auto & state) {
    return evaluate(r, state).D_T[i];
  });
  addFunctorProperty<ADReal>(_kT_names[i], [this, i](const auto & r, const auto & state) {
    return evaluate(r, state).kT[i];
  });
  addFunctorProperty<ADReal>(_D_mix_names[i], [this, i](const auto & r, const auto & state) {
    return evaluate(r, state).D_mix[i];
  });
}
Result
QPXThermalDiffusionMaterial::evaluate(const int r, const int state) const
{
  auto nDij = foo();
  for (int i = 0; i < 7; ++i)
  {
    for (int j = 0; j < 7; ++j)
    {
      nDij[i][j] = i + j;
    }
  }
  for (int i = 0; i < 7; ++i)
  {
    const ADReal one_minus_Y = 1.0 - Y[i];
    for (int j = 0; j < 7; ++j)
      denominator += X[j] / (nDij[i][j] / number_density);
    D_mix[i] = one_minus_Y / denominator;
  }
  return out;
}
'''


def self_test() -> int:
    try:
        source = _synthetic_source()
        instrumented, metadata = instrument_source(source)
        for name in TIMER_NAMES.values():
            if instrumented.count(name) != 1:
                raise AssertionError(f"timer {name} missing or duplicated")
        if "PerfGraphInterface.h" not in instrumented:
            raise AssertionError("PerfGraph include insertion failed")
        if not metadata["dmix_span"] or not metadata["collision_pair_span"]:
            raise AssertionError("loop instrumentation metadata missing")
        try:
            instrument_source(instrumented)
        except ProbeError:
            pass
        else:
            raise AssertionError("reinstrumentation mutation was not rejected")
        try:
            instrument_source(source.replace("one_minus_Y", "broken"))
        except ProbeError:
            pass
        else:
            raise AssertionError("missing D_mix anchor mutation was not rejected")

        perfgraph = {
            "reporters": {"pg": {"type": "PerfGraphReporter"}},
            "time_steps": [
                {
                    "pg": {
                        "version": 1,
                        "graph": {
                            "app": {
                                "level": 0,
                                "time": 1.0,
                                "num_calls": 1,
                                "children": {
                                    "NonlinearSystemBase::computeJacobianInternal": {
                                        "level": 1,
                                        "time": 4.0,
                                        "num_calls": 1,
                                        "children": {
                                            "QPXThermalDiffusionMaterial::qpx_transport_evaluate": {
                                                "level": 2,
                                                "time": 3.0,
                                                "num_calls": 10,
                                                "children": {
                                                    "QPXThermalDiffusionMaterial::qpx_transport_collision_pairs": {
                                                        "level": 3,
                                                        "time": 2.0,
                                                        "num_calls": 10,
                                                        "children": {},
                                                    },
                                                    "QPXThermalDiffusionMaterial::qpx_transport_dmix": {
                                                        "level": 3,
                                                        "time": 1.0,
                                                        "num_calls": 10,
                                                        "children": {},
                                                    },
                                                },
                                            }
                                        },
                                    }
                                },
                            }
                        },
                    }
                }
            ],
        }
        profile = {
            "performance": {
                "wall_seconds": 20.0,
                "petsc": {
                    "rows": [
                        {
                            "Event Name": "SNESJacobianEval",
                            "Rank": 0,
                            "Time": 10.0,
                            "Count": 1,
                        }
                    ]
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            perf_path = Path(tmp) / "perf.json"
            perf_path.write_text(json.dumps(perfgraph))
            result = analyze_probe(profile, perf_path)
            if result["outcome"] != "APPLICATION_EVALUATION_INSIDE_JACOBIAN":
                raise AssertionError(result)
            if not math.isclose(
                float(result["evaluate_fraction_of_jacobian"]), 0.6, rel_tol=1e-12
            ):
                raise AssertionError("Jacobian-context fraction mutation")
        print("QPX_TRANSPORT_PROBE_SELFTEST: PASS")
        return 0
    except Exception as exc:
        print(f"QPX_TRANSPORT_PROBE_SELFTEST: FAIL: {exc}")
        return 1


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx transport-probe")
    parser.add_argument("--qpx")
    parser.add_argument("--smoke-root")
    parser.add_argument("--source")
    parser.add_argument("--build-command")
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--allow-source-sha-mismatch", action="store_true")
    parser.add_argument("--restore-run")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return self_test()
    try:
        if args.restore_run:
            executable = Path(args.qpx).expanduser().resolve() if args.qpx else None
            return restore_probe(Path(args.restore_run), executable)
        return run_managed_probe(
            executable_arg=args.qpx,
            smoke_root_arg=Path(args.smoke_root) if args.smoke_root else None,
            source_arg=Path(args.source) if args.source else None,
            build_command_arg=args.build_command,
            jobs=args.jobs,
            allow_source_sha_mismatch=args.allow_source_sha_mismatch,
        )
    except (ProbeError, OSError, json.JSONDecodeError) as exc:
        print(f"PF3_TRANSPORT_PROBE_FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
