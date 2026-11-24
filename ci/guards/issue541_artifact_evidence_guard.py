#!/usr/bin/env python3
"""#541/#15: fail-closed proof files for upload-artifact evidence lanes.

Positive job status never excuses missing or invalid local evidence. A failed
Native/public-S6 gate remains a failure; this script does not promote science.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github/workflows/ci.yml"
TEMPLATE = ROOT / "physics_harness/workflow/definitions/general-ci.yml"
PHYSICS_CODE_CI = ROOT / ".github/workflows/physics-code-ci.yml"
PHYSICS_NATIVE_CI = ROOT / ".github/workflows/physics-native-ci.yml"
CORE = "experiments/Issue402_plasma_dsl_g1/evidence/core_four"
REGRESSION = "experiments/Issue402_plasma_dsl_g1/evidence"

P0_FILES = (
    "issue541_core_four_p0.log",
    "issue541_core_four_routes.json",
    "issue541_core_four_routes.md",
    "issue541_recovered_p0.log",
)
NATIVE_FILES = ("p1_identity.json", "p1.log", "p2.log")
REGRESSION_FILES = ("numerical_parity.json", "native_parity_negative_controls.json")
MANDATORY_UPLOADS = (
    "Upload architecture census",
    "Upload migration source snapshot",
    "Upload C++ EEPF data, explicitly marked not real-gas parity",
    "Store four-workflow P0 and inventory evidence",
    "Publish exact-head P1/P2 source-bound evidence (no P3)",
    "Upload native regression evidence",
)
UPLOAD_OWNERS = {
    "Upload architecture census": "core",
    "Upload migration source snapshot": "code",
    "Upload C++ EEPF data, explicitly marked not real-gas parity": "native",
    "Store four-workflow P0 and inventory evidence": "code",
    "Publish exact-head P1/P2 source-bound evidence (no P3)": "native",
    "Upload native regression evidence": "native",
}
CHECK_OWNERS = {
    "Require complete CORE P0 artifact evidence": ("code", "--check-core-p0"),
    "Require source-bound CORE Native P1/P2 artifact evidence": ("native", "--check-core-native"),
    "Require actual native regression evidence before success": ("native", "--check-regression"),
    "Require explicit Public D KEEP_HOLD evidence, not Native D PASS": ("native", "p6_legacy_hold_receipt.py --mode public"),
}



def require_file(path: Path) -> str:
    assert path.is_file() and path.stat().st_size > 0, "REQUIRED_ARTIFACT_FILE_MISSING:" + str(path)
    return path.read_text(encoding="utf-8")


def check_core_p0(tmp_dir: Path) -> None:
    files = {name: require_file(tmp_dir / name) for name in P0_FILES}
    assert re.search(r"\b\d+ passed in ", files["issue541_core_four_p0.log"]), "CORE_P0_PASS_LOG_MISSING"
    assert re.search(r"\b\d+ passed in ", files["issue541_recovered_p0.log"]), "RECOVERED_P0_PASS_LOG_MISSING"
    json.loads(files["issue541_core_four_routes.json"])


def check_core_native(root: Path, head: str, oci: str) -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", head), "EXPECTED_HEAD_INVALID"
    assert "@sha256:" in oci and len(oci.split("@sha256:", 1)[1]) == 64, "PINNED_OCI_INVALID"
    evidence = root / CORE
    files = {name: require_file(evidence / name) for name in NATIVE_FILES}
    identity = json.loads(files["p1_identity.json"])
    assert identity.get("source_sha") == head, "NATIVE_SOURCE_HEAD_MISMATCH"
    assert identity.get("oci_image") == oci, "NATIVE_OCI_MISMATCH"
    assert identity.get("P1") == "PASS", "NATIVE_P1_NOT_PROVEN"
    assert re.fullmatch(r"[0-9a-f]{64}", str(identity.get("binary_sha256", ""))), "NATIVE_BINARY_HASH_MISSING"
    assert "ISSUE541_CORE_FOUR_P1_SOURCE_BINARY_OCI_VERIFIED" in files["p2.log"], "NATIVE_P1_BINDING_MISSING"
    assert "ISSUE541_CORE_FOUR_NATIVE_P2_PASS; P3=NOT_RUN; SCIENCE_HOLD" in files["p2.log"], "NATIVE_P2_RECEIPT_MISSING"


def check_regression(root: Path) -> None:
    evidence = root / REGRESSION
    for name in REGRESSION_FILES:
        json.loads(require_file(evidence / name))
    receipt = json.loads((evidence / "native_parity_negative_controls.json").read_text(encoding="utf-8"))
    assert receipt.get("result") == "NATIVE_PARITY_FALSE_PASS_REJECTED", "NATIVE_PARITY_NEGATIVE_CONTROLS_MISSING"


def step_block(ci: str, name: str) -> str:
    marker = "      - name: " + name + "\n"
    assert ci.count(marker) == 1, "UPLOAD_STEP_MISSING_OR_DUPLICATED:" + name
    tail = ci.split(marker, 1)[1]
    end = re.search(r"(?m)^      - name: |^  [A-Za-z0-9_-]+:", tail)
    return tail[:end.start()] if end else tail


def policy_sources(ci: str) -> dict[str, str]:
    return {
        "core": ci,
        "code": PHYSICS_CODE_CI.read_text(encoding="utf-8"),
        "native": PHYSICS_NATIVE_CI.read_text(encoding="utf-8"),
    }


def check_policy(
    ci: str, template: str, *,
    domain_sources: dict[str, str] | None = None,
) -> None:
    """Preserve every evidence lane across its authorized Workflow owner."""
    assert ci == template, "CI_TEMPLATE_SOURCE_DIVERGED"
    sources = policy_sources(ci)
    if domain_sources is not None:
        sources.update(domain_sources)
    for name in MANDATORY_UPLOADS:
        marker = "      - name: " + name + "\n"
        assert sum(text.count(marker) for text in sources.values()) == 1, (
            "UPLOAD_OWNER_MISSING_OR_DUPLICATED:" + name
        )
        step = step_block(sources[UPLOAD_OWNERS[name]], name)
        assert "uses: actions/upload-artifact@v4" in step, "UPLOAD_ACTION_MISSING:" + name
        assert "if-no-files-found: error" in step, "ARTIFACT_MISSING_MUST_FAIL:" + name
    p0 = step_block(sources["code"], "Store four-workflow P0 and inventory evidence")
    assert "/tmp/issue541_recovered_p0.log" in p0, "RECOVERED_P0_NOT_UPLOADED"
    for name, (owner, check) in CHECK_OWNERS.items():
        assert check in step_block(sources[owner], name), "ARTIFACT_CHECKER_NOT_WIRED:" + name
    assert "--self-test" in "\n".join(sources.values()), "ARTIFACT_MUTATION_SELF_TEST_NOT_WIRED"


def must_reject(fn, label: str) -> None:
    try:
        fn()
    except (AssertionError, ValueError, json.JSONDecodeError):
        return
    raise AssertionError("ARTIFACT_FALSE_PASS_NOT_CAUGHT:" + label)


def self_test() -> None:
    head, oci = "a" * 40, "registry.example/image@sha256:" + "b" * 64
    with tempfile.TemporaryDirectory(prefix="issue541-artifact-guard-") as workspace:
        root = Path(workspace)
        tmp = root / "tmp"
        tmp.mkdir()
        samples = {
            "issue541_core_four_p0.log": "87 passed in 3.5s\n",
            "issue541_core_four_routes.json": '{"routes":[]}\n',
            "issue541_core_four_routes.md": "# routes\n",
            "issue541_recovered_p0.log": "70 passed in 2.5s\n",
        }
        for name, data in samples.items():
            (tmp / name).write_text(data)
        check_core_p0(tmp)
        for name, data in samples.items():
            path = tmp / name
            path.unlink()
            must_reject(lambda: check_core_p0(tmp), "P0_MISSING_" + name)
            path.write_text(data)
        (tmp / "issue541_core_four_routes.json").write_text("{")
        must_reject(lambda: check_core_p0(tmp), "P0_CORRUPT_ROUTES")
        (tmp / "issue541_core_four_routes.json").write_text(samples["issue541_core_four_routes.json"])
        (tmp / "issue541_recovered_p0.log").write_text("0 failed\n")
        must_reject(lambda: check_core_p0(tmp), "P0_FALSE_PASS")
        (tmp / "issue541_recovered_p0.log").write_text(samples["issue541_recovered_p0.log"])

        native = root / CORE
        native.mkdir(parents=True)
        identity = {"source_sha": head, "oci_image": oci, "binary_sha256": "c" * 64, "P1": "PASS"}
        (native / "p1_identity.json").write_text(json.dumps(identity))
        (native / "p1.log").write_text("compiled PhysicsApp\n")
        (native / "p2.log").write_text(
            "ISSUE541_CORE_FOUR_P1_SOURCE_BINARY_OCI_VERIFIED\n"
            "ISSUE541_CORE_FOUR_NATIVE_P2_PASS; P3=NOT_RUN; SCIENCE_HOLD\n")
        check_core_native(root, head, oci)
        for name in NATIVE_FILES:
            path = native / name
            data = path.read_text()
            path.unlink()
            must_reject(lambda: check_core_native(root, head, oci), "NATIVE_MISSING_" + name)
            path.write_text(data)
        must_reject(lambda: check_core_native(root, "d" * 40, oci), "NATIVE_WRONG_HEAD")
        must_reject(lambda: check_core_native(root, head, "other@sha256:" + "b" * 64), "NATIVE_WRONG_OCI")
        data = (native / "p2.log").read_text()
        (native / "p2.log").write_text("ISSUE541_CORE_FOUR_P1_SOURCE_BINARY_OCI_VERIFIED\n")
        must_reject(lambda: check_core_native(root, head, oci), "NATIVE_P2_FALSE_PASS")
        (native / "p2.log").write_text(data)

        regression = root / REGRESSION
        regression.mkdir(parents=True, exist_ok=True)
        (regression / "numerical_parity.json").write_text('{"result":"PASS"}')
        (regression / "native_parity_negative_controls.json").write_text(
            '{"result":"NATIVE_PARITY_FALSE_PASS_REJECTED"}')
        check_regression(root)
        for name in REGRESSION_FILES:
            path = regression / name
            data = path.read_text()
            path.unlink()
            must_reject(lambda: check_regression(root), "REGRESSION_MISSING_" + name)
            path.write_text(data)
        (regression / "native_parity_negative_controls.json").write_text('{"result":"NOT_EVALUATED"}')
        must_reject(lambda: check_regression(root), "REGRESSION_FALSE_PASS")

    ci = CI.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    check_policy(ci, template)
    source_by_owner = policy_sources(ci)
    for name in MANDATORY_UPLOADS:
        owner = UPLOAD_OWNERS[name]
        marker = "      - name: " + name + "\n"
        original = source_by_owner[owner]
        before, after = original.split(marker, 1)
        altered = before + marker + after.replace(
            "if-no-files-found: error", "if-no-files-found: warn", 1
        )
        if owner == "core":
            must_reject(lambda: check_policy(altered, altered),
                        "UPLOAD_WARNING_" + name)
        else:
            must_reject(
                lambda: check_policy(ci, template, domain_sources={owner: altered}),
                "UPLOAD_WARNING_" + name,
            )
    must_reject(
        lambda: check_policy(
            ci, ci.replace("if-no-files-found: error",
                           "if-no-files-found: warn", 1)
        ),
        "TEMPLATE_DRIFT",
    )
    print("ISSUE541_ARTIFACT_EVIDENCE_MUTATION_SELF_TEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    for flag in ("--self-test", "--check-policy", "--check-core-p0", "--check-core-native", "--check-regression"):
        group.add_argument(flag, action="store_true")
    parser.add_argument("--expected-head")
    parser.add_argument("--pinned-oci")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.check_policy:
        check_policy(CI.read_text(encoding="utf-8"), TEMPLATE.read_text(encoding="utf-8"))
        print("ISSUE541_ARTIFACT_UPLOAD_POLICY=PASS")
    elif args.check_core_p0:
        check_core_p0(Path("/tmp"))
        print("ISSUE541_ARTIFACT_EVIDENCE_CORE_P0=PASS")
    elif args.check_core_native:
        check_core_native(ROOT, args.expected_head or "", args.pinned_oci or "")
        print("ISSUE541_ARTIFACT_EVIDENCE_CORE_NATIVE=PASS; P3=NOT_RUN; SCIENCE_HOLD")
    elif args.check_regression:
        check_regression(ROOT)
        print("ISSUE541_ARTIFACT_EVIDENCE_NATIVE_REGRESSION=PASS; SCIENCE_HOLD")


if __name__ == "__main__":
    main()
