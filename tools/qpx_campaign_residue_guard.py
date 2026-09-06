#!/usr/bin/env python3
"""Guard reusable performance/analysis ownership against campaign residue."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"CAMPAIGN_RESIDUE_GUARD: FAIL: {message}")
    raise SystemExit(1)


def text(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        fail(f"missing required production file: {path}")
    return target.read_text(encoding="utf-8")


def main() -> int:
    forbidden_campaign_modules = (
        "qpx_harness/analysis/performance/cache.py",
        "qpx_harness/analysis/performance/investigation.py",
        "qpx_harness/execution/performance/smoke.py",
        "qpx_harness/execution/performance/investigation.py",
    )
    present = [path for path in forbidden_campaign_modules if (ROOT / path).exists()]
    if present:
        fail("campaign modules remain in production: " + ", ".join(present))

    app = text("qpx_harness/cli/app.py")
    retired_commands = (
        '"scale-audit"', '"measure-smoke"', '"investigate"',
        '"transport-probe"', '"cache-audit"',
    )
    leaked = [token for token in retired_commands if token in app]
    if leaked:
        fail("campaign/default-specific CLI commands remain: " + ", ".join(leaked))

    perf_cli = text("qpx_harness/cli/commands/performance.py")
    for token in ("PF-1", "PF-3", "Issue22", "Issue 22", "qvt", "QVT", "D_mix"):
        if token in perf_cli:
            fail(f"generic performance CLI contains campaign/default residue: {token}")

    scale = text("qpx_harness/analysis/scale_audit.py")
    for token in (
        "Issue43", "Issue #43", "QVT", "qvt.msh", "DEFAULT_PRESSURE",
        "DEFAULT_ELECTRON_DENSITY", "DEFAULT_MU_N", "DEFAULT_D_N",
        "HEAVY_Q11_300K",
    ):
        if token in scale:
            fail(f"generic scale analysis contains policy anchor/residue: {token}")

    generic_perf_roots = (
        ROOT / "qpx_harness/analysis/performance",
        ROOT / "qpx_harness/execution/performance",
    )
    concrete_tokens = ("QPXThermalDiffusionMaterial", "QPX_TRANSPORT_TIME_SECTION")
    concrete_hits: list[str] = []
    for root in generic_perf_roots:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if any(token in source for token in concrete_tokens):
                concrete_hits.append(str(path.relative_to(ROOT)))
    if concrete_hits:
        fail("generic performance owns concrete solver instrumentation: " + ", ".join(concrete_hits))

    relocated = ROOT / "qpx_harness/adapters/moose/performance/transport_probe.py"
    if not relocated.is_file():
        fail("concrete transport probe was not preserved behind MOOSE boundary")

    print("PRODUCTION_PF_CAMPAIGN_API_IDENTITIES = 0")
    print("PRODUCTION_ISSUE_COUPLED_DEFAULT_CASES = 0")
    print("PRODUCTION_QVT_POLICY_ANCHORS_IN_GENERIC_ANALYSIS = 0")
    print("GENERIC_PERFORMANCE_TO_CONCRETE_SOLVER_INTROSPECTION_EDGES = 0")
    print("CAMPAIGN_BRANDING_IN_GENERIC_MODULE_IDENTITY = 0")
    print("CAMPAIGN_RESIDUE_GUARD = PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
