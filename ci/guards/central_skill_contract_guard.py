#!/usr/bin/env python3
"""Regression guard for central Skill manifest/catalog drift.

Derived from Repository CI #251: the consumer manifest had already adopted a new
Skill, while CI duplicated an older closed-world Skill-name set and failed.
The manifest/catalog pair is authoritative; CI must validate their relationship,
not maintain a second hand-written inventory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class CentralSkillContractError(ValueError):
    pass


def validate(manifest: dict, catalog: dict) -> dict:
    if manifest.get("schema_version") != 2:
        raise CentralSkillContractError("central skill manifest schema_version must be 2")
    if catalog.get("schema_version") != 1:
        raise CentralSkillContractError("central catalog schema_version must be 1")

    manifest_entries = manifest.get("skills")
    catalog_entries = catalog.get("skills")
    if not isinstance(manifest_entries, list) or not isinstance(catalog_entries, list):
        raise CentralSkillContractError("skills must be lists")

    manifest_by_name = {item["name"]: item for item in manifest_entries}
    catalog_by_name = {item["name"]: item for item in catalog_entries}
    if len(manifest_by_name) != len(manifest_entries):
        raise CentralSkillContractError("duplicate Skill name in consumer manifest")
    if len(catalog_by_name) != len(catalog_entries):
        raise CentralSkillContractError("duplicate Skill name in central catalog")

    if set(manifest_by_name) != set(catalog_by_name):
        missing = sorted(set(catalog_by_name) - set(manifest_by_name))
        extra = sorted(set(manifest_by_name) - set(catalog_by_name))
        raise CentralSkillContractError(
            f"consumer/central Skill inventory drift: missing={missing}, extra={extra}"
        )

    revision = manifest["operating_system"]["revision"]
    for name, consumer in manifest_by_name.items():
        central = catalog_by_name[name]
        if consumer.get("revision") != revision:
            raise CentralSkillContractError(f"{name}: revision differs from OS pin")
        if consumer.get("path") != central.get("path"):
            raise CentralSkillContractError(f"{name}: path differs from central catalog")
        if consumer.get("load_on") != central.get("load_on"):
            raise CentralSkillContractError(f"{name}: load_on differs from central catalog")

    return {"status": "PASS", "skills": sorted(manifest_by_name), "count": len(manifest_by_name)}


def self_test() -> None:
    base_manifest = {
        "schema_version": 2,
        "operating_system": {"revision": "a" * 40},
        "skills": [{
            "name": "existing", "path": "skills/existing/README.md",
            "load_on": ["INIT"], "revision": "a" * 40,
        }],
    }
    base_catalog = {
        "schema_version": 1,
        "skills": [{"name": "existing", "path": "skills/existing/README.md", "load_on": ["INIT"]}],
    }
    validate(base_manifest, base_catalog)

    # Regression for Repository CI #251: adding a Skill to both authoritative
    # documents must not require editing a third hard-coded expected-name set.
    expanded_manifest = json.loads(json.dumps(base_manifest))
    expanded_catalog = json.loads(json.dumps(base_catalog))
    expanded_manifest["skills"].append({
        "name": "scientific-discriminator-controller",
        "path": "skills/scientific-discriminator-controller/README.md",
        "load_on": ["SCIENTIFIC_DISCRIMINATOR_CONTROLLER"],
        "revision": "a" * 40,
    })
    expanded_catalog["skills"].append({
        "name": "scientific-discriminator-controller",
        "path": "skills/scientific-discriminator-controller/README.md",
        "load_on": ["SCIENTIFIC_DISCRIMINATOR_CONTROLLER"],
    })
    result = validate(expanded_manifest, expanded_catalog)
    assert result["count"] == 2

    broken = json.loads(json.dumps(expanded_manifest))
    broken["skills"][-1]["load_on"] = ["WRONG_TRIGGER"]
    try:
        validate(broken, expanded_catalog)
    except CentralSkillContractError:
        pass
    else:
        raise AssertionError("load_on drift must fail closed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="docs/operating_system/central_skills.json")
    parser.add_argument("--catalog")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("CENTRAL_SKILL_CONTRACT=SELF_TEST_PASS")
        return 0
    if not args.catalog:
        parser.error("--catalog is required unless --self-test is used")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    result = validate(manifest, catalog)
    print("CENTRAL_SKILL_CONTRACT=PASS")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
