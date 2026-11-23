#!/usr/bin/env python3
"""Bounded, *secret-free* micro-mesh PETSc AD charge/Poisson Jacobian diagnostic.

Uses exact PhysicsApp ELF from the completed G6B P1 build, without rebuilding
or rerunning the original 100us transient. This tests a synthetic 3x3 FE mesh
with the same charge ADParsed Functor chain and Poisson RHS/ADMatDiffusion types
as the source; it is not the full 417/941 Jacobian or an Old/New parity proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from contextlib import contextmanager

from physics_harness.adapters.petsc.jacobian import parse_comparisons

SOURCE = "26e84a4a33cf93d9e278a4f0b2d78c53cae2d6ce"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
BINARY_SHA_RE = re.compile("[0-9a-f]{64}\\Z")
MAX_TIMEOUT = 300
RELATIVE_JAC_TOL = 1e-8  # Declared before the Native run; no post-hoc tuning.


class NativeJacobianHold(ValueError):
    pass


def generated_input() -> str:
    """Small ADPoisson component fixture using the exact G3 charge chain."""
    return """# G7 diagnostic: not the original S6 model, no private rates.
[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 3
  ny = 3
[]
[Variables]
  [potential]
    initial_condition = 0.0
  []
  [log_O2p]
    initial_condition = -15.0
  []
  [log_Op]
    initial_condition = -16.5
  []
  [log_e]
    initial_condition = -16.0
  []
  [log_Om]
    initial_condition = -17.0
  []
[]
[Materials]
  [eps_plasma]
    type = ADGenericConstantMaterial
    prop_names = relative_permittivity
    prop_values = '1.0'
  []
[]
[FunctorMaterials]
  [g7_n_O2p]
    type = ADParsedFunctorMaterial
    property_name = O2p_number_density
    functor_names = log_O2p
    functor_symbols = u
    expression = '6.02214076e23*exp(u)'
  []
  [g7_n_Op]
    type = ADParsedFunctorMaterial
    property_name = Op_number_density
    functor_names = log_Op
    functor_symbols = u
    expression = '6.02214076e23*exp(u)'
  []
  [g7_n_e]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = log_e
    functor_symbols = u
    expression = '6.02214076e23*exp(u)'
  []
  [g7_n_Om]
    type = ADParsedFunctorMaterial
    property_name = Om_number_density
    functor_names = log_Om
    functor_symbols = u
    expression = '6.02214076e23*exp(u)'
  []
  [g7_charge_number_density]
    type = ADParsedFunctorMaterial
    property_name = charge_number_density
    functor_names = 'O2p_number_density Op_number_density n_e_physical Om_number_density'
    functor_symbols = 'ni nop ne nm'
    expression = 'ni+nop-ne-nm'
  []
  [g7_charge_density_C_m3]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = charge_number_density
    functor_symbols = nq
    expression = '1.602176634e-19*nq'
  []
  [g7_poisson_source]
    type = ADParsedFunctorMaterial
    property_name = poisson_source
    functor_names = charge_number_density
    functor_symbols = nq
    expression = '1.8095128179727827e-08*nq'
  []
[]
[Kernels]
  [poisson_diffusion]
    type = ADMatDiffusion
    variable = potential
    diffusivity = relative_permittivity
  []
  [poisson_charge_source]
    type = FunctorKernel
    variable = potential
    functor = poisson_source
    functor_on_rhs = true
  []
  [o2p_diffusion]
    type = Diffusion
    variable = log_O2p
  []
  [op_diffusion]
    type = Diffusion
    variable = log_Op
  []
  [e_diffusion]
    type = Diffusion
    variable = log_e
  []
  [om_diffusion]
    type = Diffusion
    variable = log_Om
  []
[]
[BCs]
  [potential_zero]
    type = DirichletBC
    variable = potential
    boundary = 'left right top bottom'
    value = 0
  []
  [o2p_fixed]
    type = DirichletBC
    variable = log_O2p
    boundary = 'left right top bottom'
    value = -15.0
  []
  [op_fixed]
    type = DirichletBC
    variable = log_Op
    boundary = 'left right top bottom'
    value = -16.5
  []
  [e_fixed]
    type = DirichletBC
    variable = log_e
    boundary = 'left right top bottom'
    value = -16.0
  []
  [om_fixed]
    type = DirichletBC
    variable = log_Om
    boundary = 'left right top bottom'
    value = -17.0
  []
[]
[Executioner]
  type = Steady
  nl_max_its = 5
  nl_abs_tol = 1e-10
[]
[Outputs]
  exodus = false
  csv = false
  checkpoint = false
[]
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_binary_and_source(source: Path, bundle_manifest: Path) -> dict:
    git = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        text=True, capture_output=True, timeout=10, check=True,
    ).stdout.strip()
    if git != SOURCE:
        raise NativeJacobianHold("PINNED_PHYSICS_SOURCE_DRIFT")
    manifest = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    binary = source / "physics_app/physics-opt"
    if (
        manifest.get("source_sha") != SOURCE
        or manifest.get("oci_ref") != OCI
        or manifest.get("schema_version") != 1
        or manifest.get("protected_input_in_build_bundle") is not False
        or not isinstance(manifest.get("files"), dict)
        or not BINARY_SHA_RE.fullmatch(str(manifest["files"].get("physics_app/physics-opt")))
        or not binary.is_file() or binary.is_symlink()
        or sha256(binary) != manifest["files"]["physics_app/physics-opt"]
    ):
        raise NativeJacobianHold("EXACT_PINNED_BINARY_MANIFEST_MISMATCH")
    return {"source_sha": git, "binary_sha256": sha256(binary),
            "manifest_sha256": sha256(bundle_manifest), "oci_ref": OCI}


def docker_command(source: Path, temp: Path, *, check: bool) -> list[str]:
    args = "/workspace/physics_app/physics-opt -i g7_micro_poisson.i"
    if check:
        args += " --check-input"
    else:
        args += " -snes_test_jacobian -snes_converged_reason"
    return [
        "docker", "run", "--rm", "--network", "none",
        "--entrypoint", "/bin/bash", "--user", "0:0",
        "--workdir", "/case",
        "--mount", "type=bind,src=" + str(source.resolve()) + ",dst=/workspace,readonly",
        "--mount", "type=bind,src=" + str(temp.resolve()) + ",dst=/case",
        OCI, "-lc", "set -euo pipefail; source /environment; " + args,
    ]


def interpret(log: str, *, check_rc: int, solve_rc: int, timeout: bool) -> dict:
    parsed = parse_comparisons(log)
    valid = [
        item for item in parsed
        if math.isfinite(item["relative_frobenius_error"])
        and math.isfinite(item["absolute_frobenius_error"])
        and item["relative_frobenius_error"] >= 0
        and item["absolute_frobenius_error"] >= 0
    ]
    worst = max((x["relative_frobenius_error"] for x in valid), default=None)
    # A failed solve may still emit a comparison; only a complete run can PASS.
    valid_run = check_rc == 0 and solve_rc == 0 and not timeout
    bounded_pass = (
        valid_run and len(valid) >= 1 and len(valid) == len(parsed)
        and worst is not None and worst <= RELATIVE_JAC_TOL
    )
    return {
        "native_p2": "PASS" if check_rc == 0 else "HOLD",
        "native_solver_rc": solve_rc,
        "timed_out": timeout,
        "petsc_jacobian_comparison_count": len(parsed),
        "finite_comparisons": len(valid),
        "worst_relative_frobenius_error": worst,
        "predeclared_relative_tolerance": RELATIVE_JAC_TOL,
        "component_jacobian": "PASS_SYNTHETIC_AD_COMPONENT" if bounded_pass else "HOLD",
        "actual_s6_coupled_ad_jacobian": "UNVERIFIED",
        "old_new_poisson_parity": "UNVERIFIED",
        "science": "SCIENCE_HOLD",
    }


@contextmanager
def private_workspace():
    """Bounded repair of OCI-created root-owned JIT cache before host deletion."""
    with tempfile.TemporaryDirectory(prefix="g7-petsc-ad-") as folder:
        root = Path(folder)
        if (root.is_symlink() or root.parent != Path(tempfile.gettempdir())
                or not root.name.startswith("g7-petsc-ad-")):
            raise NativeJacobianHold("PRIVATE_DIRECTORY_SCOPE_INVALID")
        try:
            yield root
        finally:
            subprocess.run(
                ["sudo", "chown", "-Rh", f"{os.getuid()}:{os.getgid()}",
                 "--", str(root)],
                check=True, timeout=60, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def run(*, source: Path, manifest: Path, output: Path,
        timeout: int, authorize: bool) -> dict:
    if not authorize:
        raise NativeJacobianHold("NATIVE_EXPLICIT_AUTHORIZATION_REQUIRED")
    if not 1 <= timeout <= MAX_TIMEOUT:
        raise NativeJacobianHold("NATIVE_JACOBIAN_TIMEOUT_OUT_OF_BOUNDS")
    if output.exists():
        raise NativeJacobianHold("REPORT_OVERWRITE_DENIED")
    identity = verify_binary_and_source(source, manifest)
    evidence = {
        "schema": "issue652.g7.synthetic_ad_jacobian.v1",
        **identity, "fixture": "3x3_generatedmesh_G3_charge_functor_ADMatDiffusion_FunctorKernel",
        "native_p2": "HOLD", "component_jacobian": "HOLD",
        "actual_s6_coupled_ad_jacobian": "UNVERIFIED",
        "science": "SCIENCE_HOLD",
    }
    with private_workspace() as temp:
        (temp / "g7_micro_poisson.i").write_text(generated_input(), encoding="utf-8")
        evidence["fixture_sha256"] = sha256(temp / "g7_micro_poisson.i")
        def invoke(check: bool):
            try:
                p = subprocess.run(
                    docker_command(source, temp, check=check),
                    capture_output=True, text=True, timeout=timeout, check=False,
                    env={k: v for k, v in os.environ.items()
                         if k != "PROTECTED_ARCHIVE_B64"},
                )
                return p.returncode, (p.stdout or "") + "\n" + (p.stderr or ""), False
            except subprocess.TimeoutExpired:
                return 124, "", True
        rc0, log0, timed0 = invoke(True)
        evidence["native_check_log_sha256"] = hashlib.sha256(log0.encode()).hexdigest()
        evidence["native_check_returncode"] = rc0
        # This one-off synthetic fixture contains no private rates. Expose only
        # bounded, allowlisted error sentences; never raw full Native logs.
        diagnostic_lines = [
            line.strip()[:200] for line in log0.splitlines()
            if any(term in line.lower() for term in (
                "error", "unknown", "failed", "input", "syntax",
                "not found", "parameter", "functor", "exception",
                "usage", "invalid", "unrecognized"))
        ]
        evidence["synthetic_p2_diagnostic"] = diagnostic_lines[-8:]
        if rc0 != 0 or "Syntax OK" not in log0 or timed0:
            # Public synthetic test has no private rates; still avoid native logs.
            if "Functor" in log0 or "functor" in log0:
                evidence["native_p2_failure_category"] = "FUNCTOR_BINDING"
            elif "not registered" in log0 or "Unknown" in log0 or "not found" in log0:
                evidence["native_p2_failure_category"] = "TYPE_OR_PARAMETER_BINDING"
            elif timed0:
                evidence["native_p2_failure_category"] = "TIMEOUT"
            else:
                evidence["native_p2_failure_category"] = "OTHER_NATIVE_INPUT"
        if rc0 == 0 and "Syntax OK" in log0 and not timed0:
            rc, log, timed = invoke(False)
            evidence["native_solver_log_sha256"] = hashlib.sha256(log.encode()).hexdigest()
            evidence.update(interpret(log, check_rc=rc0, solve_rc=rc, timeout=timed))
        else:
            evidence.update(interpret("", check_rc=rc0, solve_rc=-1, timeout=timed0))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print("G7_PETSC_MICRO_JACOBIAN_RESULT", evidence["component_jacobian"],
          "P2", evidence.get("native_p2"), "P2_CATEGORY",
          evidence.get("native_p2_failure_category", "NONE"),
          "P2_RC", evidence.get("native_check_returncode"),
          "P2_DIAGNOSTIC", json.dumps(evidence.get("synthetic_p2_diagnostic", [])),
          "RC", evidence.get("native_solver_rc"),
          "REL", evidence.get("worst_relative_frobenius_error"),
          "ACTUAL_S6_AD_UNVERIFIED SCIENCE_HOLD", flush=True)
    return evidence


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--timeout", type=int, default=MAX_TIMEOUT)
    p.add_argument("--authorize-native", action="store_true")
    a = p.parse_args()
    try:
        result = run(source=a.source, manifest=a.manifest, output=a.output,
                     timeout=a.timeout, authorize=a.authorize_native)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("G7_NATIVE_JACOBIAN_HOLD " + type(exc).__name__, flush=True)
        return 2
    return 0 if result["component_jacobian"] == "PASS_SYNTHETIC_AD_COMPONENT" else 3


if __name__ == "__main__":
    raise SystemExit(main())
