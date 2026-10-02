"""Code-addressable simple-case templates for reusable Physics experiments.

This module owns template discovery and materialization only. Generated cases
are executed through the existing physics test command.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

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
    template_manifest: str | None = None

    @property
    def template_source(self) -> bool:
        return (
            self.status == STABLE_STATUS
            and self.path is not None
            and self.template_manifest is not None
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SimpleCaseCatalogError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SimpleCaseCatalogError(f"JSON object required: {path}")
    return value


def load_simple_case_catalog(path: Path = DEFAULT_CATALOG) -> tuple[SimpleCase, ...]:
    payload = _load_json(path)
    if payload.get("schema_version") != 1:
        raise SimpleCaseCatalogError("simple-case catalog requires schema_version=1")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SimpleCaseCatalogError("simple-case catalog requires a non-empty cases array")

    cases: list[SimpleCase] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise SimpleCaseCatalogError("each simple-case entry must be an object")
        template = raw.get("template")
        cases.append(
            SimpleCase(
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
                template_manifest=(
                    str(template["manifest"])
                    if isinstance(template, dict) and template.get("manifest")
                    else None
                ),
            )
        )

    cases.sort(key=lambda case: case.order)
    orders = [case.order for case in cases]
    ids = [case.simple_case_id for case in cases]
    if orders != list(range(1, len(cases) + 1)):
        raise SimpleCaseCatalogError(f"simple-case order must be contiguous from 1: {orders}")
    if len(ids) != len(set(ids)):
        raise SimpleCaseCatalogError("simple-case ids must be unique")
    return tuple(cases)


def resolve_simple_case(selector: str | int) -> SimpleCase:
    key = str(selector).strip().lower().replace("_", "-")
    for case in load_simple_case_catalog():
        candidates = {
            case.simple_case_id.lower(),
            str(case.order),
            *(alias.strip().lower().replace("_", "-") for alias in case.aliases),
        }
        if key in candidates:
            return case
    raise SimpleCaseCatalogError(f"unknown simple-case selector: {selector!r}")


def _template_payload(case: SimpleCase, root: Path = ROOT) -> tuple[Path, dict]:
    if not case.template_source:
        raise SimpleCaseCatalogError(
            f"{case.simple_case_id} is not an approved template source "
            f"(status={case.status})"
        )
    case_dir = root / str(case.path)
    manifest_path = case_dir / str(case.template_manifest)
    if not manifest_path.is_file():
        raise SimpleCaseCatalogError(
            f"{case.simple_case_id}: missing template manifest {manifest_path}"
        )
    payload = _load_json(manifest_path)
    if payload.get("schema_version") != 1:
        raise SimpleCaseCatalogError(
            f"{case.simple_case_id}: template manifest requires schema_version=1"
        )
    if payload.get("template_id") != case.simple_case_id:
        raise SimpleCaseCatalogError(
            f"{case.simple_case_id}: template_id mismatch in {manifest_path}"
        )
    return case_dir, payload


def materialize_input_template(
    selector: str | int,
    output: Path,
    *,
    root: Path = ROOT,
    overwrite: bool = False,
) -> Path:
    case = resolve_simple_case(selector)
    case_dir, payload = _template_payload(case, root)
    source = case_dir / str(payload["input_template"])
    if not source.is_file():
        raise SimpleCaseCatalogError(f"missing input template: {source}")
    output = Path(output).expanduser().resolve()
    if output.exists() and not overwrite:
        raise SimpleCaseCatalogError(f"refusing to overwrite existing file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    return output


def create_simple_case(
    selector: str | int,
    destination: Path,
    *,
    input_path: Path | None = None,
    root: Path = ROOT,
) -> Path:
    case = resolve_simple_case(selector)
    case_dir, payload = _template_payload(case, root)

    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise SimpleCaseCatalogError(
            f"destination already exists; case creation is non-destructive: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)

    input_template = case_dir / str(payload["input_template"])
    if not input_template.is_file():
        raise SimpleCaseCatalogError(f"missing input template: {input_template}")

    overlay = Path(input_path).expanduser().resolve() if input_path is not None else None
    if overlay is not None and not overlay.is_file():
        raise SimpleCaseCatalogError(f"new input does not exist: {overlay}")

    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    try:
        generated_input = str(payload.get("generated_input", "input.i"))
        shutil.copy2(input_template, staging / generated_input)

        copied_assets: list[dict[str, str]] = []
        for raw_name in payload.get("copy_assets", []):
            name = str(raw_name)
            source = case_dir / name
            if not source.is_file():
                raise SimpleCaseCatalogError(
                    f"{case.simple_case_id}: missing template asset {source}"
                )
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_assets.append({"path": name, "sha256": _sha256(target)})

        overlay_sha = None
        overlay_name = None
        if overlay is not None:
            shutil.copy2(overlay, staging / generated_input)
            overlay_sha = _sha256(overlay)
            overlay_name = overlay.name

        test_manifest = {
            "name": destination.name,
            "type": "diagnostic",
            "input": generated_input,
        }
        (staging / str(payload.get("generated_manifest", "test.json"))).write_text(
            json.dumps(test_manifest, indent=2) + "\n",
            encoding="utf-8",
        )

        origin = {
            "schema_version": 1,
            "status": "GENERATED_FROM_STABLE_TEMPLATE",
            "template_id": case.simple_case_id,
            "source_experiment_id": case.experiment_id,
            "source_status": case.status,
            "source_case_path": case.path,
            "source_template_sha256": _sha256(input_template),
            "generated_input": generated_input,
            "generated_input_sha256": _sha256(staging / generated_input),
            "overlay_input_name": overlay_name,
            "overlay_input_sha256": overlay_sha,
            "copied_assets": copied_assets,
            "qualification_inherited": False,
            "qualification_note": (
                "The source template is qualified, but a derived input must be "
                "validated independently before promotion."
            ),
        }
        (staging / str(payload.get("generated_provenance", "template_origin.json"))).write_text(
            json.dumps(origin, indent=2) + "\n",
            encoding="utf-8",
        )

        (staging / "README.md").write_text(
            "# Generated simple Physics case\n\n"
            f"Base template: {case.simple_case_id}\n\n"
            "This directory was created by physics simple-case create. "
            "It is runnable through the existing physics test command but "
            "is not scientifically qualified until its derived input is validated.\n",
            encoding="utf-8",
        )

        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return destination


def validate_simple_case_catalog(root: Path = ROOT) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        cases = load_simple_case_catalog(root / "experiments" / "simple_case_inventory.json")
    except SimpleCaseCatalogError as exc:
        return (str(exc),)

    for case in cases:
        if case.status == STABLE_STATUS:
            if not case.path:
                errors.append(f"{case.simple_case_id}: stable case missing path")
                continue
            case_dir = root / case.path
            if not case_dir.is_dir():
                errors.append(f"{case.simple_case_id}: missing case directory {case.path}")
                continue
            if not case.test_manifest or not (case_dir / case.test_manifest).is_file():
                errors.append(f"{case.simple_case_id}: missing baseline test manifest")
            if not case.provenance or not (case_dir / case.provenance).is_file():
                errors.append(f"{case.simple_case_id}: missing baseline provenance")
            else:
                provenance = _load_json(case_dir / case.provenance)
                if provenance.get("status") != STABLE_STATUS:
                    errors.append(
                        f"{case.simple_case_id}: baseline provenance is not {STABLE_STATUS}"
                    )
            if not case.template_manifest:
                errors.append(f"{case.simple_case_id}: stable case missing template manifest")
                continue
            try:
                source_dir, template = _template_payload(case, root)
            except SimpleCaseCatalogError as exc:
                errors.append(str(exc))
                continue
            baseline_input = source_dir / str(template.get("baseline_input", "input.i"))
            template_input = source_dir / str(template.get("input_template", "input.template.i"))
            if not baseline_input.is_file() or not template_input.is_file():
                errors.append(f"{case.simple_case_id}: baseline/template input missing")
            elif baseline_input.read_bytes() != template_input.read_bytes():
                errors.append(
                    f"{case.simple_case_id}: input.template.i drifted from qualified input.i"
                )
            for raw_name in template.get("copy_assets", []):
                if not (source_dir / str(raw_name)).is_file():
                    errors.append(
                        f"{case.simple_case_id}: missing template asset {raw_name}"
                    )
        elif case.template_manifest is not None:
            errors.append(
                f"{case.simple_case_id}: non-stable case must not advertise a template"
            )

    return tuple(errors)


def cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="physics simple-case")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("list", help="list known reusable and planned simple cases")

    show = sub.add_parser("show", help="show one catalog entry")
    show.add_argument("selector")

    sub.add_parser("check", help="validate the catalog and stable templates")

    template = sub.add_parser("template", help="materialize the qualified input template")
    template.add_argument("selector")
    template.add_argument("--output", required=True)
    template.add_argument("--force", action="store_true")

    create = sub.add_parser(
        "create",
        help="create a runnable derived case from a qualified template",
    )
    create.add_argument("selector")
    create.add_argument("destination")
    create.add_argument(
        "--input",
        help="replace generated input.i with this new input after scaffolding",
    )

    args = parser.parse_args(argv)
    try:
        if args.action == "list":
            for case in load_simple_case_catalog():
                print(
                    f"{case.order}\t{case.simple_case_id}\t"
                    f"{case.status}\t{case.path or '-'}"
                )
            return 0
        if args.action == "show":
            print(json.dumps(asdict(resolve_simple_case(args.selector)), indent=2, sort_keys=True))
            return 0
        if args.action == "check":
            errors = validate_simple_case_catalog()
            if errors:
                print("SIMPLE_CASE_CATALOG: FAIL")
                for error in errors:
                    print(f"  - {error}")
                return 1
            print("SIMPLE_CASE_CATALOG: PASS")
            return 0
        if args.action == "template":
            output = materialize_input_template(
                args.selector,
                Path(args.output),
                overwrite=args.force,
            )
            print(f"SIMPLE_CASE_TEMPLATE={output}")
            return 0
        if args.action == "create":
            destination = create_simple_case(
                args.selector,
                Path(args.destination),
                input_path=Path(args.input) if args.input else None,
            )
            print(f"SIMPLE_CASE_CREATED={destination}")
            print(f"RUN=python3 bin/physics.py test {destination} --qpx $PHYSICS_OPT")
            return 0
    except (OSError, SimpleCaseCatalogError, ValueError) as exc:
        print(f"simple-case error: {exc}")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(cli_main())
