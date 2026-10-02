"""Reusable simple-case inventory and selector.

This module is a selection/catalog layer, not a second experiment control
plane. Runnable entries delegate to the existing physics test surface through
their repository-owned test.json manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "experiments" / "simple_case_inventory.json"
STABLE_STATUS = "STABLE_REUSABLE_BASELINE"


class SimpleCaseCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class SimpleCase:
    order: int
    simple_case_id: str
    experiment_id: str | None
    status: str
    path: str | None
    test_manifest: str | None
    provenance: str | None
    description: str
    physics_layers: tuple[str, ...]
    deliberately_absent: tuple[str, ...]
    aliases: tuple[str, ...]

    @property
    def reproducible(self) -> bool:
        return self.status == STABLE_STATUS and self.path is not None


def _load_payload(path: Path = DEFAULT_CATALOG) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SimpleCaseCatalogError(f"cannot load simple-case catalog {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SimpleCaseCatalogError("simple-case catalog must be a schema_version=1 object")
    return payload


def load_simple_case_catalog(path: Path = DEFAULT_CATALOG) -> tuple[SimpleCase, ...]:
    payload = _load_payload(path)
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SimpleCaseCatalogError("simple-case catalog requires a non-empty cases array")

    cases: list[SimpleCase] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise SimpleCaseCatalogError("each simple-case entry must be an object")
        cases.append(SimpleCase(
            order=int(raw["order"]),
            simple_case_id=str(raw["simple_case_id"]),
            experiment_id=raw.get("experiment_id"),
            status=str(raw["status"]),
            path=raw.get("path"),
            test_manifest=raw.get("test_manifest"),
            provenance=raw.get("provenance"),
            description=str(raw["description"]),
            physics_layers=tuple(str(item) for item in raw.get("physics_layers", [])),
            deliberately_absent=tuple(str(item) for item in raw.get("deliberately_absent", [])),
            aliases=tuple(str(item) for item in raw.get("aliases", [])),
        ))

    cases.sort(key=lambda case: case.order)
    orders = [case.order for case in cases]
    ids = [case.simple_case_id for case in cases]
    if orders != list(range(1, len(cases) + 1)):
        raise SimpleCaseCatalogError(f"simple-case order must be contiguous from 1: {orders}")
    if len(ids) != len(set(ids)):
        raise SimpleCaseCatalogError("simple-case ids must be unique")
    return tuple(cases)


def simple_case_choices(*, include_planned: bool = True) -> tuple[SimpleCase, ...]:
    cases = load_simple_case_catalog()
    return cases if include_planned else tuple(case for case in cases if case.reproducible)


def _normalized(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def resolve_simple_case(selector: str | int) -> SimpleCase:
    key = _normalized(str(selector))
    for case in load_simple_case_catalog():
        candidates = {_normalized(case.simple_case_id), _normalized(str(case.order))}
        candidates.update(_normalized(alias) for alias in case.aliases)
        if key in candidates:
            return case
    raise SimpleCaseCatalogError(f"unknown simple-case selector: {selector!r}")


def reproduction_command(case: SimpleCase, *, executable: str = "$PHYSICS_OPT") -> str:
    if not case.reproducible:
        raise SimpleCaseCatalogError(
            f"{case.simple_case_id} is {case.status}; only {STABLE_STATUS} entries are runnable"
        )
    return f"python3 bin/physics.py test {case.path} --qpx {executable}"


def is_simple_case_request(text: str) -> bool:
    payload = _load_payload()
    normalized = _normalized(text)
    triggers = tuple(_normalized(item) for item in payload.get("conversation_triggers", []))
    return any(trigger in normalized for trigger in triggers)


def format_simple_case_choices(
    cases: Iterable[SimpleCase] | None = None,
    *,
    include_reproduction_command: bool = False,
) -> str:
    selected = tuple(cases) if cases is not None else simple_case_choices()
    lines: list[str] = []
    for case in selected:
        state = "ready" if case.reproducible else "planned"
        line = f"{case.order}. {case.simple_case_id} [{state}] — {case.description}"
        if include_reproduction_command and case.reproducible:
            line += f"\n   run: {reproduction_command(case)}"
        lines.append(line)
    return "\n".join(lines)


def simple_case_menu_for_request(text: str) -> str | None:
    if not is_simple_case_request(text):
        return None
    return format_simple_case_choices(include_reproduction_command=False)


def validate_simple_case_catalog(root: Path = ROOT) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        cases = load_simple_case_catalog(root / "experiments" / "simple_case_inventory.json")
    except SimpleCaseCatalogError as exc:
        return (str(exc),)

    for case in cases:
        if case.reproducible:
            case_dir = root / str(case.path)
            if not case_dir.is_dir():
                errors.append(f"{case.simple_case_id}: missing case directory {case.path}")
                continue
            if not case.test_manifest:
                errors.append(f"{case.simple_case_id}: stable case missing test_manifest")
                continue
            manifest_path = case_dir / case.test_manifest
            if not manifest_path.is_file():
                errors.append(f"{case.simple_case_id}: missing {case.test_manifest}")
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{case.simple_case_id}: invalid test manifest: {exc}")
                continue
            if manifest.get("name") != case.experiment_id:
                errors.append(
                    f"{case.simple_case_id}: test manifest name {manifest.get('name')!r} "
                    f"!= experiment_id {case.experiment_id!r}"
                )
            input_name = manifest.get("input")
            if not isinstance(input_name, str) or not (case_dir / input_name).is_file():
                errors.append(f"{case.simple_case_id}: runnable input missing")
            checker = manifest.get("checker")
            if checker and not (case_dir / str(checker)).is_file():
                errors.append(f"{case.simple_case_id}: checker missing: {checker}")
            if not case.provenance or not (case_dir / case.provenance).is_file():
                errors.append(f"{case.simple_case_id}: provenance missing")
            else:
                provenance = json.loads((case_dir / case.provenance).read_text(encoding="utf-8"))
                if provenance.get("status") != STABLE_STATUS:
                    errors.append(
                        f"{case.simple_case_id}: provenance status {provenance.get('status')!r} "
                        f"!= {STABLE_STATUS!r}"
                    )
        elif case.path is not None:
            errors.append(f"{case.simple_case_id}: non-stable entry must not claim runnable path")

    return tuple(errors)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simple-cases")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--ready-only", action="store_true")
    parser.add_argument("--with-command", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        errors = validate_simple_case_catalog()
        if errors:
            print("SIMPLE_CASE_CATALOG: FAIL")
            for error in errors:
                print("  -", error)
            return 1
        print("SIMPLE_CASE_CATALOG: PASS")

    cases = simple_case_choices(include_planned=not args.ready_only)
    print(format_simple_case_choices(cases, include_reproduction_command=args.with_command))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
