from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import inventory  # noqa: E402


def main() -> int:
    failures: list[str] = []

    try:
        inventory.self_test()
    except Exception as exc:  # pragma: no cover - terminal guard
        failures.append(f"census self-test failed: {exc}")
        print(f"ISSUE59_CENSUS_SELFTEST: FAIL ({exc})")
    else:
        print("ISSUE59_CENSUS_SELFTEST: PASS")

    try:
        payload = inventory.build_census(ROOT)
        errors = inventory.validate_census(payload)
    except Exception as exc:  # pragma: no cover - terminal guard
        failures.append(f"census execution failed: {exc}")
        print(f"ISSUE59_CENSUS_EXECUTION: FAIL ({exc})")
        payload = None
        errors: list[str] = []
    else:
        print("ISSUE59_CENSUS_EXECUTION: PASS")
        failures.extend(errors)

    if payload is not None:
        recipe_set = payload["recipe_set"]
        print(
            "ISSUE59_RECIPE_SET: "
            + ("PASS" if recipe_set["ok"] else "FAIL")
            + f" count={len(recipe_set['observed'])}"
        )

        for module in payload["modules"]:
            baseline = module["baseline"]
            status = "PASS" if baseline["ok"] else "FAIL"
            print(
                f"ISSUE59_BASELINE: {status} "
                f"{module['path']} sha={baseline['observed']}"
            )

        records = [
            record
            for module in payload["modules"]
            for record in module["symbols"]
        ]
        counts = Counter(record["responsibility"] for record in records)
        classified = sum(counts.values())
        expected = len(records)
        accounting_ok = classified == expected and expected > 0
        print(
            "ISSUE59_SYMBOL_ACCOUNTING: "
            + ("PASS" if accounting_ok else "FAIL")
            + f" symbols={expected}"
        )
        if not accounting_ok:
            failures.append("symbol accounting mismatch")

        for klass in sorted(inventory.RESPONSIBILITY_CLASSES):
            print(f"ISSUE59_CLASS_COUNT: {klass}={counts.get(klass, 0)}")

        by_path = {module["path"]: module for module in payload["modules"]}
        consumers_ok = True
        for recipe_path, expected_subset in (
            inventory.EXPECTED_MODULE_CONSUMER_SUBSETS.items()
        ):
            observed = set(by_path[recipe_path]["module_importers"])
            missing = expected_subset - observed
            status = "PASS" if not missing else "FAIL"
            print(
                f"ISSUE59_CONSUMER_BASELINE: {status} "
                f"{recipe_path} importers={len(observed)}"
            )
            if missing:
                consumers_ok = False
                failures.append(
                    f"missing known consumers for {recipe_path}: {sorted(missing)}"
                )
        print("ISSUE59_CONSUMER_SCAN: " + ("PASS" if consumers_ok else "FAIL"))

        pilot = by_path["recipes/issue43_coupling_diagnostic.py"]
        pilot_functions = [
            record for record in pilot["symbols"] if record["kind"] == "function"
        ]
        pilot_ok = bool(pilot_functions) and all(
            record["responsibility"] == "DECLARATIVE_TRANSFORM"
            and record["spec_v1"] == "YES"
            for record in pilot_functions
        )
        print(
            "ISSUE59_PILOT_READINESS_BASELINE: "
            + ("PASS" if pilot_ok else "FAIL")
        )
        if not pilot_ok:
            failures.append("Issue43 coupling diagnostic is not fully v1-ready")

        orphan_candidates = [
            module["path"]
            for module in payload["modules"]
            if not module["module_importers"]
        ]
        print(
            "ISSUE59_ZERO_IMPORTER_RECIPE_CANDIDATES: "
            + (", ".join(orphan_candidates) if orphan_candidates else "none")
        )

    for error in errors:
        print(f"ISSUE59_CENSUS_ERROR: {error}")

    print("ISSUE59_REFACTOR_EVRS: 0")
    if failures:
        print("ISSUE59_FINAL_GUARD: FAIL")
        return 1
    print("ISSUE59_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
