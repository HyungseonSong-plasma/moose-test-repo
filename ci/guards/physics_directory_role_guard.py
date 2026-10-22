"""Semantic directory responsibility guard for Physics.

Checks only syntax-backed evidence: declared roles, explicit import directions
and listed forbidden process call shapes. Role names and prose cannot prove
actual semantic ownership or runtime execution. Transitional exceptions are
REVIEW, not an unqualified architectural PASS.
"""
from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "docs/architecture/physics_directory_roles_v1.json"


def _valid_path(value: object) -> bool:
    return (
        isinstance(value, str) and bool(value)
        and not value.startswith("/") and "\\" not in value and "\x00" not in value
        and all(x not in ("", ".", "..") for x in value.split("/"))
    )


def _imports(tree: ast.AST, path: str) -> tuple[str, ...]:
    module = path.removesuffix(".py").split("/")
    scope = module[:-1] if module[-1] != "__init__" else module[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                if node.module:
                    found.add(node.module)
            elif node.level <= len(scope):
                prefix = scope[:len(scope) - (node.level - 1)]
                # Relative imports into a package resolve to the package
                # without guessing whether an imported symbol is a module.
                found.add(".".join(prefix + ([node.module] if node.module else [])))
    return tuple(sorted(found))


def _call_spelling(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        return node.func.value.id + "." + node.func.attr
    return None


def _prefix(target: str, pattern: str) -> bool:
    return target == pattern or target.startswith(pattern + ".")


def evaluate(
    files: Mapping[str, str], policy: Mapping,
) -> list[dict[str, str]]:
    root = policy.get("scope")
    roles = policy.get("roles")
    if not _valid_path(root) or not isinstance(roles, dict) or not roles:
        raise ValueError("invalid directory role policy")
    for role, info in roles.items():
        if not isinstance(info, dict) or not isinstance(info.get("responsibility"), str) or not info["responsibility"]:
            raise ValueError(f"role {role}: missing responsibility")
        forbidden = info.get("forbidden_imports")
        if not isinstance(forbidden, list) or len(forbidden) != len(set(forbidden)):
            raise ValueError(f"role {role}: invalid forbidden imports")
        if any(not _valid_path(x.replace(".", "/")) for x in forbidden):
            raise ValueError(f"role {role}: invalid import prefix")
    approved = {}
    for exc in policy.get("import_exceptions", []):
        key = (exc["source"], exc["target"])
        if (key in approved or not _valid_path(key[0])
            or exc.get("status") not in {"TRANSITIONAL_REVIEW", "APPROVED_OPERATIONAL_BOUNDARY"}
            or not exc.get("rationale")):
            raise ValueError("invalid import exception")
        role = key[0].removeprefix(root + "/").split("/")[0]
        if role not in roles or key[1] not in roles[role]["forbidden_imports"]:
            raise ValueError("exception does not match a forbidden role dependency")
        approved[key] = exc
    process_approved = {}
    for exc in policy.get("process_exceptions", []):
        key = (exc["source"], exc["callee"])
        if key in process_approved or not _valid_path(key[0]) or not exc.get("rationale") or exc.get("status") != "TRANSITIONAL_REVIEW":
            raise ValueError("invalid process exception")
        process_approved[key] = exc

    found: list[dict[str, str]] = []
    active_import_exceptions: set[tuple[str, str]] = set()
    active_process_exceptions: set[tuple[str, str]] = set()
    present = set()
    for path, content in sorted(files.items()):
        if not _valid_path(path) or not isinstance(content, str):
            raise ValueError("invalid source file input")
        if not path.startswith(root + "/") or not path.endswith(".py"):
            continue
        relative = path[len(root) + 1:]
        # Package root's __init__.py belongs to the namespace itself and is
        # not a subdirectory role.
        if "/" not in relative:
            continue
        role = relative.split("/")[0]
        present.add(role)
        if role not in roles:
            found.append({"status":"NOT_EVALUATED","code":"UNCLASSIFIED_ROLE",
                          "source":path,"target":"","reason":"no policy role"})
            continue
        tree = ast.parse(content, filename=path)
        for module in _imports(tree, path):
            for prefix in roles[role]["forbidden_imports"]:
                if not _prefix(module, prefix):
                    continue
                key = (path, prefix)
                exc = approved.get(key)
                if exc:
                    active_import_exceptions.add(key)
                found.append({
                    "status": ("REVIEW_REQUIRED" if exc and exc["status"] == "TRANSITIONAL_REVIEW" else
                               "APPROVED_OPERATIONAL_BOUNDARY" if exc else "VIOLATION"),
                    "code": "APPROVED_ROLE_EDGE" if exc and exc["status"] == "APPROVED_OPERATIONAL_BOUNDARY" else
                            "TRANSITIONAL_ROLE_EDGE" if exc else "FORBIDDEN_ROLE_EDGE",
                    "source": path, "target": module,
                    "reason": exc["rationale"] if exc else f"{role} must not import {prefix}",
                })
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            spelling = _call_spelling(node)
            if not any(rule["role"] == role and rule["callee"] == spelling
                       for rule in policy.get("forbidden_process_calls", [])):
                continue
            key = (path, spelling)
            exc = process_approved.get(key)
            if exc:
                active_process_exceptions.add(key)
            found.append({
                "status": "REVIEW_REQUIRED" if exc else "VIOLATION",
                "code": "TRANSITIONAL_PROCESS_CALL" if exc else "FORBIDDEN_PROCESS_CALL",
                "source": path, "target": spelling,
                "reason": exc["rationale"] if exc else f"{role} must not implement {spelling}",
            })
    for role in sorted(set(roles) - present):
        found.append({"status":"VIOLATION","code":"MISSING_ROLE",
                      "source":root+"/"+role,"target":"","reason":"declared role absent"})
    for key in sorted(set(approved) - active_import_exceptions):
        found.append({"status":"REVIEW_REQUIRED","code":"OBSOLETE_IMPORT_EXCEPTION",
                      "source":key[0],"target":key[1],"reason":"reassess stale exception"})
    for key in sorted(set(process_approved) - active_process_exceptions):
        found.append({"status":"REVIEW_REQUIRED","code":"OBSOLETE_PROCESS_EXCEPTION",
                      "source":key[0],"target":key[1],"reason":"reassess stale exception"})
    return sorted(found, key=lambda x: (x["status"], x["code"], x["source"], x["target"]))


def _self_test() -> None:
    fixture = {
        "scope":"physics_harness",
        "roles":{
            "ontology":{"responsibility":"semantics","forbidden_imports":["physics_harness.adapters.moose"]},
            "adapters":{"responsibility":"solver backends","forbidden_imports":[]},
        },
        "import_exceptions":[], "process_exceptions":[],
        "forbidden_process_calls":[{"role":"ontology","callee":"subprocess.run"}],
    }
    files = {
        "physics_harness/ontology/a.py": "from physics_harness.adapters.moose import target\n",
        "physics_harness/adapters/b.py": "pass\n",
    }
    cases = evaluate(files, fixture)
    assert [(r["code"], r["status"]) for r in cases] == [
        ("FORBIDDEN_ROLE_EDGE", "VIOLATION")
    ], cases
    files["physics_harness/ontology/a.py"] = "import subprocess\nsubprocess.run(['echo'])\n"
    cases = evaluate(files, fixture)
    assert cases[0]["code"] == "FORBIDDEN_PROCESS_CALL", cases
    files["physics_harness/ontology/a.py"] = "from ..adapters.moose import target\n"
    cases = evaluate(files, fixture)
    assert cases[0]["code"] == "FORBIDDEN_ROLE_EDGE", cases
    print("PHYSICS_DIRECTORY_ROLE_GUARD_SELF_TEST: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.self_test:
        _self_test()
    if not args.check:
        return 0
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    files = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
             for p in sorted((ROOT / policy["scope"]).rglob("*.py"))}
    findings = evaluate(files, policy)
    blocking = [x for x in findings if x["status"] == "VIOLATION"]
    reviews = [x for x in findings if x["status"] == "REVIEW_REQUIRED"]
    accepted = [x for x in findings if x["status"] == "APPROVED_OPERATIONAL_BOUNDARY"]
    unknown = [x for x in findings if x["status"] == "NOT_EVALUATED"]
    if args.json_out:
        args.json_out.write_text(
            json.dumps({"policy_id":policy["policy_id"], "analyzed_paths":len(files),
                        "violations":len(blocking),"reviews":len(reviews),
                        "accepted_operational":len(accepted),
                        "unclassified":len(unknown),"findings":findings},
                       indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for f in findings:
        print(f"{f['status']} {f['code']}: {f['source']} -> {f['target']}; {f['reason']}")
    print(
        f"PHYSICS_DIRECTORY_ROLE_GUARD: {'FAIL' if blocking or unknown else 'PASS_WITH_REVIEW' if reviews else 'PASS'} "
        f"violations={len(blocking)} reviews={len(reviews)} accepted={len(accepted)} "
        f"unclassified={len(unknown)}",
    )
    return 1 if blocking or unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
