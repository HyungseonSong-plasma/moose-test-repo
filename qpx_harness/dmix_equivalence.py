"""Managed direct equivalence test for optimized vs legacy D_mix evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cpp.calls import CppCallError, self_test as cpp_calls_self_test, split_call_arguments
from .cpp.source import CppSource, CppSourceError, self_test as cpp_source_self_test
from .runtime import resolve_executable, validate_executable

SOURCE_RELATIVE = Path("src/materials/QPXThermalDiffusionMaterial.C")
BASE_CASE_RELATIVE = Path(
    "tests/Issue20_full_oxygen_canonical_promotion/dmix_oracle_ne_sensitivity"
)
SPECIES = ("O2", "O2s", "O2p", "O", "Om", "Op", "Os")
TAGS = ("A", "B")
REL_TOL = 2.0e-5
TRACE = {
    "w_O2": 0.99994,
    "w_O2s": 1e-5,
    "w_O2p": 1e-5,
    "w_O": 1e-5,
    "w_Om": 1e-5,
    "w_Op": 1e-5,
    "w_Os": 1e-5,
}


class EquivalenceError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def legacy_source_transform(source: str) -> tuple[str, dict[str, Any]]:
    """Reconstruct the legacy full evaluate(...) call from evaluateDmix(...).

    Production optimized contract:

        return evaluateDmix(species_i, T, p, Te, ne, Y);

    Legacy contract:

        return evaluate(T, p, Te, ne, Y).D_mix[species_i];

    The six argument expressions are parsed structurally and preserved rather
    than hardcoded so nested functor/state expressions remain valid.
    """
    try:
        cpp = CppSource(source)
        cpp.require_tokens(
            (
                "QPXThermalDiffusionMaterial::evaluate",
                "QPXThermalDiffusionMaterial::evaluateDmix",
                "_D_mix_names",
            )
        )
        functor_call = cpp.unique_call("addFunctorProperty", containing="_D_mix_names")
        lambda_body = cpp.lambda_body(functor_call)
        dmix_call = cpp.unique_call("evaluateDmix", within=lambda_body)
        parsed = split_call_arguments(cpp, dmix_call)
        return_stmt = cpp.unique_return_call("evaluateDmix", within=lambda_body)
    except (CppSourceError, CppCallError) as exc:
        raise EquivalenceError(f"structural C++ source inspection failed: {exc}") from exc

    args = parsed.arguments
    if len(args) != 6:
        raise EquivalenceError(
            "evaluateDmix production contract expected 6 arguments "
            f"(species_i,T,p,Te,ne,Y), found {len(args)}: {args}"
        )

    species_index = args[0].strip()
    evaluate_args = ", ".join(arg.strip() for arg in args[1:])
    replacement = f"return evaluate({evaluate_args}).D_mix[{species_index}];"
    patched = cpp.replace(return_stmt, replacement)
    if patched == source:
        raise EquivalenceError("legacy source transform produced no change")

    metadata = {
        "parser": "CppSource+CppCallArguments",
        "functor_call_span": [functor_call.start, functor_call.end],
        "lambda_body_span": [lambda_body.start, lambda_body.end],
        "dmix_call_span": [dmix_call.start, dmix_call.end],
        "return_statement_span": [return_stmt.start, return_stmt.end],
        "dmix_arguments": list(args),
        "original_return": return_stmt.slice(source).strip(),
        "replacement_return": replacement,
    }
    return patched, metadata


def legacy_source(source: str) -> str:
    return legacy_source_transform(source)[0]


def quoted_values(text: str, key: str) -> tuple[re.Match[str], list[str]]:
    m = re.search(
        rf"(^\s*{re.escape(key)}\s*=\s*')([^']*)('.*$)",
        text,
        re.MULTILINE,
    )
    if not m:
        raise EquivalenceError(f"missing {key} in base input")
    return m, m.group(2).split()


def trace_input(text: str) -> str:
    _, names = quoted_values(text, "prop_names")
    values_match, values = quoted_values(text, "prop_values")
    if len(names) != len(values):
        raise EquivalenceError("prop_names/prop_values size mismatch")
    index = {name: i for i, name in enumerate(names)}
    missing = [name for name in TRACE if name not in index]
    if missing:
        raise EquivalenceError("missing trace fraction names: " + ", ".join(missing))
    for name, value in TRACE.items():
        values[index[name]] = f"{value:.12g}"
    total = sum(float(values[index[name]]) for name in TRACE)
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-14):
        raise EquivalenceError(f"trace mass fractions sum to {total}")
    replacement = values_match.group(1) + " ".join(values) + values_match.group(3)
    return text[: values_match.start()] + replacement + text[values_match.end() :]


def read_dmix(csv_path: Path) -> dict[str, float]:
    if not csv_path.is_file():
        raise EquivalenceError(f"missing output {csv_path}")
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise EquivalenceError(f"no rows in {csv_path}")
    row = rows[-1]
    out: dict[str, float] = {}
    for tag in TAGS:
        for species in SPECIES:
            key = f"Dmix_{tag}_{species}"
            try:
                value = float(row[key])
            except (KeyError, ValueError) as exc:
                raise EquivalenceError(f"bad {key}: {exc}") from exc
            if not math.isfinite(value) or value <= 0:
                raise EquivalenceError(f"non-positive/non-finite {key}={value}")
            out[key] = value
    return out


def compare(
    candidate: dict[str, float], legacy: dict[str, float], tol: float
) -> dict[str, Any]:
    failures: list[str] = []
    maximum = 0.0
    details = []
    for tag in TAGS:
        for species in SPECIES:
            key = f"Dmix_{tag}_{species}"
            if key not in candidate or key not in legacy:
                failures.append(f"missing {key}")
                continue
            old = legacy[key]
            new = candidate[key]
            rel = abs(new - old) / max(abs(old), 1e-300)
            maximum = max(maximum, rel)
            details.append(
                {
                    "key": key,
                    "candidate": new,
                    "legacy": old,
                    "relative_error": rel,
                }
            )
            if rel > tol:
                failures.append(f"{key}: {rel:.6e} > {tol:.6e}")
    return {
        "status": "PASS" if not failures else "FAIL",
        "max_relative_error": maximum,
        "relative_tolerance": tol,
        "failures": failures,
        "details": details,
    }


def stream(command: list[str], cwd: Path, log: Path) -> int:
    print("DMIX_EQ_COMMAND:", shlex.join(command))
    with log.open("w", buffering=1) as f:
        p = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert p.stdout is not None
        for line in p.stdout:
            print(line, end="")
            f.write(line)
            f.flush()
        return p.wait()


def prepare_case(base: Path, target: Path, trace: bool) -> None:
    shutil.copytree(base, target)
    for stale in target.glob("input_out*"):
        if stale.is_file():
            stale.unlink()
    if trace:
        inp = target / "input.i"
        inp.write_text(trace_input(inp.read_text()))


def run_case(exe: Path, case: Path, label: str, root: Path) -> dict[str, Any]:
    for stale in case.glob("input_out*"):
        if stale.is_file():
            stale.unlink()
    if stream(
        [str(exe), "-i", "input.i", "--check-input"],
        case,
        root / f"{label}_p2.log",
    ):
        raise EquivalenceError(f"{label} P2 failed")
    if stream(
        [str(exe), "-i", "input.i"],
        case,
        root / f"{label}_p3.log",
    ):
        raise EquivalenceError(f"{label} P3 failed")
    return {
        "input_sha256": sha256(case / "input.i"),
        "csv_sha256": sha256(case / "input_out.csv"),
        "values": read_dmix(case / "input_out.csv"),
    }


def self_test() -> int:
    try:
        if cpp_source_self_test():
            raise AssertionError("CppSource self-test failed")
        if cpp_calls_self_test():
            raise AssertionError("CppCallArguments self-test failed")

        source = r'''
void f()
{
  addFunctorProperty<ADReal>(
      _D_mix_names[i],
      [this, i](const auto & r, const auto & state)
      {
        return evaluateDmix(
            i,
            temperature(r, state),
            pressure(foo(1, 2), state),
            Te(r, state),
            ne(r, state),
            composition(bar(3, 4), state));
      });
}
Result QPXThermalDiffusionMaterial::evaluate(int, int, int, int, int) const { return {}; }
ADReal QPXThermalDiffusionMaterial::evaluateDmix(int, int, int, int, int, int) const { return {}; }
'''
        patched, meta = legacy_source_transform(source)
        expected = (
            "return evaluate(temperature(r, state), pressure(foo(1, 2), state), "
            "Te(r, state), ne(r, state), composition(bar(3, 4), state)).D_mix[i];"
        )
        if expected not in patched:
            raise AssertionError(meta)
        if meta["parser"] != "CppSource+CppCallArguments":
            raise AssertionError("structured call parser was not used")
        if meta["dmix_arguments"][0] != "i":
            raise AssertionError("species index was not preserved")

        wrong_arity = source.replace(
            "composition(bar(3, 4), state)",
            "extra(r, state), composition(bar(3, 4), state)",
        )
        try:
            legacy_source_transform(wrong_arity)
        except EquivalenceError:
            pass
        else:
            raise AssertionError("evaluateDmix arity mutation was not rejected")

        ambiguous = source.replace(
            "void f()",
            "void g(){ addFunctorProperty<ADReal>(_D_mix_names[i], []{ return evaluateDmix(i,1,2,3,4,5); }); }\nvoid f()",
        )
        try:
            legacy_source(ambiguous)
        except EquivalenceError:
            pass
        else:
            raise AssertionError("ambiguous D_mix producer mutation was not rejected")

        text = (
            "prop_names = 'T p Te neA neB w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'\n"
            "prop_values = '1 2 3 4 5 0.70 0.05 0.01 0.10 0.01 0.01 0.12'\n"
        )
        _, vals = quoted_values(trace_input(text), "prop_values")
        if not any(math.isclose(float(v), 0.99994, abs_tol=1e-14) for v in vals):
            raise AssertionError("trace transform positive control failed")

        baseline = {
            f"Dmix_{tag}_{species}": float(i + 1)
            for i, (tag, species) in enumerate(
                (tag, species) for tag in TAGS for species in SPECIES
            )
        }
        if compare(baseline, dict(baseline), REL_TOL)["status"] != "PASS":
            raise AssertionError("checker positive control failed")
        mutated = dict(baseline)
        mutated["Dmix_B_Op"] *= 1.1
        if compare(baseline, mutated, REL_TOL)["status"] != "FAIL":
            raise AssertionError("checker mutation was not rejected")
    except Exception as exc:
        print(f"DMIX_EQ_SELFTEST: FAIL ({exc})")
        return 1
    print("DMIX_EQ_SELFTEST: PASS")
    return 0


def _create_result_root(results: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = results / f"dmix_equivalence_Issue32_{stamp}"
    index = 1
    while root.exists():
        root = results / f"dmix_equivalence_Issue32_{stamp}_{index:02d}"
        index += 1
    root.mkdir()
    return root


def validate(args: argparse.Namespace) -> int:
    if self_test():
        return 2
    if not math.isfinite(args.rel_tol) or args.rel_tol <= 0:
        raise EquivalenceError("--rel-tol must be finite and positive")

    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    qpx_root = exe.parent.resolve()
    repo_root = Path(__file__).resolve().parents[1]
    source = args.source.resolve() if args.source else qpx_root / SOURCE_RELATIVE
    base = args.base_case.resolve() if args.base_case else repo_root / BASE_CASE_RELATIVE
    if not source.is_file() or not base.is_dir():
        raise EquivalenceError(f"missing source/base case: source={source} base={base}")

    source_original = source.read_bytes()
    source_sha = hashlib.sha256(source_original).hexdigest()
    source_legacy_text, source_parse = legacy_source_transform(source_original.decode())
    source_legacy = source_legacy_text.encode()

    jobs = args.jobs or max(1, min(8, os.cpu_count() or 1))
    build = shlex.split(args.build_command) if args.build_command else ["make", f"-j{jobs}"]

    results = qpx_root / "temp" / "results"
    results.mkdir(parents=True, exist_ok=True)
    root = _create_result_root(results)
    print("DMIX_EQ_ROOT:", root)

    shutil.copy2(exe, root / "qpx-opt.production")
    shutil.copy2(source, root / "QPXThermalDiffusionMaterial.production.C")
    exe_sha = sha256(exe)

    cases: dict[str, Path] = {}
    for branch in ("candidate", "legacy"):
        for name, is_trace in (("ordinary", False), ("trace", True)):
            case = root / "cases" / f"{branch}_{name}"
            prepare_case(base, case, is_trace)
            cases[f"{branch}_{name}"] = case

    for name in ("ordinary", "trace"):
        if sha256(cases[f"candidate_{name}"] / "input.i") != sha256(
            cases[f"legacy_{name}"] / "input.i"
        ):
            raise EquivalenceError(f"candidate/legacy {name} input mismatch")

    summary: dict[str, Any] = {
        "relative_tolerance": args.rel_tol,
        "production_source_sha256": source_sha,
        "production_executable_sha256": exe_sha,
        "source_parse": source_parse,
    }
    source_ok = binary_ok = False
    try:
        candidate = {
            name: run_case(exe, cases[f"candidate_{name}"], f"candidate_{name}", root)
            for name in ("ordinary", "trace")
        }
        summary["candidate"] = candidate

        source.write_bytes(source_legacy)
        os.utime(source, None)
        if stream(build, qpx_root, root / "build_legacy.log"):
            raise EquivalenceError("legacy build failed")
        summary["legacy_executable_sha256"] = sha256(exe)

        legacy = {
            name: run_case(exe, cases[f"legacy_{name}"], f"legacy_{name}", root)
            for name in ("ordinary", "trace")
        }
        summary["legacy"] = legacy
        summary["comparisons"] = {
            name: compare(candidate[name]["values"], legacy[name]["values"], args.rel_tol)
            for name in ("ordinary", "trace")
        }
        summary["validation_status"] = (
            "PASS"
            if all(value["status"] == "PASS" for value in summary["comparisons"].values())
            else "FAIL"
        )
    except Exception as exc:
        summary["validation_status"] = "FAIL"
        summary["error"] = str(exc)
        print("DMIX_EQ_ERROR:", exc, file=sys.stderr)
    finally:
        source.write_bytes(source_original)
        os.utime(source, None)
        source_ok = sha256(source) == source_sha
        restore_rc = stream(build, qpx_root, root / "build_restored.log") if source_ok else 1
        try:
            shutil.copy2(root / "qpx-opt.production", exe)
            binary_ok = sha256(exe) == exe_sha
        except OSError:
            binary_ok = False
        summary["restore_build_returncode"] = restore_rc
        summary["source_restored"] = source_ok
        summary["binary_restored"] = binary_ok
        write_json(root / "summary.json", summary)
        print("DMIX_EQ_RESTORE:", "PASS" if source_ok and binary_ok else "FAIL")

    for name in ("ordinary", "trace"):
        result = summary.get("comparisons", {}).get(name, {})
        print(f"DMIX_EQ_{name.upper()}:", result.get("status", "NOT_RUN"))
        if "max_relative_error" in result:
            print(f"DMIX_EQ_{name.upper()}_MAX_REL: {result['max_relative_error']:.6e}")
    print("DMIX_EQ_VALIDATION:", summary.get("validation_status", "FAIL"))
    print("DMIX_EQ_SUMMARY:", root / "summary.json")
    return (
        0
        if summary.get("validation_status") == "PASS" and source_ok and binary_ok
        else 2
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="qpx dmix-equivalence")
    p.add_argument("--qpx")
    p.add_argument("--source", type=Path)
    p.add_argument("--base-case", type=Path)
    p.add_argument("--build-command")
    p.add_argument("--jobs", type=int)
    p.add_argument("--rel-tol", type=float, default=REL_TOL)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        return validate(args)
    except (EquivalenceError, SystemExit) as exc:
        print("DMIX_EQ_FATAL:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())