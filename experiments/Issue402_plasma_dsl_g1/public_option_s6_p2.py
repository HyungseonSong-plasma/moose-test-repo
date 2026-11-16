#!/usr/bin/env python3
"""Public-data-only S6-417/941 native P2: original B versus option-first D.

Do not execute a solver time step. Never access archived private reference rates.
The C legacy migration is only an immutable source of the 10-layer no-ne_transport
base: its old migrated_continuity.i is replaced by an independently pinned overlay.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
P2_PATH = ROOT / "experiments/Issue493_s6_boltzmann/public_p2_check.py"
SPEC = importlib.util.spec_from_file_location("issue493_public_p2", P2_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load pinned public P2 preflight")
p2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p2)

HISTORICAL_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
OVERLAY = """# Review-only new option DSL overlay; NOT pinned P3 C input.
# Pair ONLY with the C candidate base (which removes the original ne_transport).
# No Material/Functor name is modified.
[Physics]
  [Plasmas]
    files = plasma_species_only.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
          fem_potential = potential
        []
      []
    []
  []
[]
[FunctorMaterials]
  [O2p_species_transport_alias]
    type = DDTransportMaterial
    model = functor
    species_id = O2p
    mobility_source = ion_mobility
    diffusivity_source = ion_diffusion
  []
  [Om_species_transport_alias]
    type = DDTransportMaterial
    model = functor
    species_id = Om
    mobility_source = negative_ion_mobility
    diffusivity_source = negative_ion_diffusion
  []
  [Op_species_transport_alias]
    type = DDTransportMaterial
    model = functor
    species_id = Op
    mobility_source = atomic_positive_ion_mobility
    diffusivity_source = atomic_positive_ion_diffusion
  []
[]
"""
OVERLAY_SHA256 = "edf3f8e8194927e93783d136066799d60df2673af9245d6d4b990fb7d267b513"
CASES = ("417", "941")
VARIANTS = ("B", "D")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def validate_overlay() -> None:
    if hashlib.sha256(OVERLAY.encode("utf-8")).hexdigest() != OVERLAY_SHA256:
        raise ValueError("Option-only review overlay SHA changed")
    for forbidden in ("variables =", "fem_kernel_names", "fem_mobility =",
                      "fem_diffusion =", "mobility =", "diffusivity =", "[ne_transport]"):
        if forbidden in OVERLAY:
            raise ValueError(f"Unexpected option/provider migration: {forbidden}")
    expected = {
        "fem_species": "'e'", "fvm_species": "'O2p Om Op'",
        "files": "plasma_species_only.json",
        "fem_potential": "potential",
    }
    for k, v in expected.items():
        if not re.search(r"(?m)^\s*" + k + r"\s*=\s*" + re.escape(v) + r"\s*$", OVERLAY):
            raise ValueError(f"Missing/modified binding: {k}")


# Compatibility belongs in an isolated *test-data migration*, not a runtime
# Physics option. B is byte-identical; only staged D inputs are canonicalized.
CANONICAL_STATE_NAMES = {
    "log_ne": "log_e",
    "log_ni": "log_O2p",
    "log_nm": "log_Om",
    "log_nop": "log_Op",
}
_STATE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, CANONICAL_STATE_NAMES)) +
    r")(?![A-Za-z0-9_])"
)


def canonicalize_staged_D_inputs(chemistry: Path, ordered: list[str]) -> dict:
    """Modify only disposable D copies, never immutable B/C or source archives.

    In the same bounded migration as ne_transport -> generated e_transport,
    remove the one original ne_time; ContinuityEq now generates e_time with
    the identical PhysicsFEMLogMolarTimeDerivative equation and block.
    """
    if len(ordered) != 11 or Path(ordered[-1]).name != "migrated_continuity.i":
        raise ValueError("Unexpected staged D input layer order")

    time_pattern = re.compile(
        r"(?m)^  \[ne_time\][ \t]*\r?\n"
        r"(?P<body>(?:^    [^\r\n]*\r?\n)+)"
        r"^  \[\][ \t]*(?:\r?\n|$)"
    )
    expected_time = {
        "type": "PhysicsFEMLogMolarTimeDerivative",
        "variable": "log_ne",
        "block": "plasma",
    }
    first_layer = Path(ordered[0]).name
    changes: dict[str, dict] = {}
    pending: list[tuple[Path, str]] = []
    removed_time: list[dict] = []
    total = 0
    for relative in ordered[:-1]:
        name = Path(relative).name
        if name != relative.split("/")[-1] or not name.endswith(".i"):
            raise ValueError("Unsafe staged D layer name")
        path = chemistry / name
        before = path.read_bytes()
        source = before.decode("utf-8")

        # The native-to-DSL substitution is exactly one known operator,
        # declared in the original base layer, with no extra parameters.
        matches = list(time_pattern.finditer(source))
        if len(matches) > 1 or ("[ne_time]" in source and not matches):
            raise ValueError("Ambiguous or malformed original ne_time block")
        if matches:
            if name != first_layer:
                raise ValueError("Original ne_time owner must reside in the first layer")
            match = matches[0]
            pairs = re.findall(
                r"(?m)^    ([a-z_]+)[ \t]*=[ \t]*([^\r\n]+)$",
                match.group("body"),
            )
            if len(pairs) != 3 or {key: value.strip() for key, value in pairs} != expected_time:
                raise ValueError("Original ne_time parameters differ from pinned Native S6")
            removed_time.append({
                "source_layer": name,
                "old_name": "ne_time",
                "generated_name": "e_time",
                "kernel_type": expected_time["type"],
                "original_block_sha256": hashlib.sha256(
                    match.group(0).encode("utf-8")).hexdigest(),
            })
            source = source[:match.start()] + source[match.end():]

        # D's C-derived base must have removed ne_transport already.
        if re.search(r"(?m)^[ \t]*\[ne_transport\][ \t]*$", source):
            raise ValueError("Staged D input still contains the original ne_transport")

        observed = {old: len(re.findall(
            r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?![A-Za-z0-9_])", source))
            for old in CANONICAL_STATE_NAMES}
        converted = _STATE_TOKEN.sub(
            lambda match: CANONICAL_STATE_NAMES[match.group()], source)
        if _STATE_TOKEN.search(converted) or "[ne_time]" in converted:
            raise ValueError("Staged D retains a legacy state or time owner")

        total += sum(observed.values())
        pending.append((path, converted))
        changes[name] = {
            "original_sha256": hashlib.sha256(before).hexdigest(),
            "staged_sha256": hashlib.sha256(converted.encode("utf-8")).hexdigest(),
            "state_name_substitutions": {k: v for k, v in observed.items() if v},
        }

    # Fail before writing any copy if ownership or source identity is unclear.
    if len(removed_time) != 1:
        raise ValueError("Expected exactly one original ne_time in staged S6 D")
    if total == 0:
        raise ValueError("No archived S6 solver states found in staged D input")
    for path, converted in pending:
        if path.read_text(encoding="utf-8") != converted:
            path.write_text(converted, encoding="utf-8")
    return {
        "status": "SCRATCH_ONLY_CANONICAL_STATE_AND_TIME_OWNER_REWRITE",
        "changed_reference_count": total,
        "removed_native_time": removed_time[0],
        "files": changes,
    }



# Historical archived decks retain old factory names only as provenance.
# No old Material object aliases are registered in the application.
# Rename the explicit type fields in disposable B/D scratch copies. No factory
# aliases are installed by the application and no archived input is rewritten.
RENAMED_FEM_KERNEL_TYPES = {
    "PhysicsFEMLogMolarTimeDerivative": "FEMLogMolarTimeDerivative",
    "PhysicsFEMLogMolarDriftDiffusion": "FEMLogMolarDriftDiffusion",
    "PhysicsFEMLogMolarElectronJouleHeating": "FEMLogMolarElectronJouleHeating",
    # Archived S6 inputs are rewritten only after their pinned byte hashes are checked.
    "PhysicsThermalDiffusionMaterial": "NVTransportMaterial",
    "DDMaterial": "DDTransportMaterial",
    "NVMaterial": "NVTransportMaterial",
    "ElectronImpactRateMaterial": "EIRateCoefMaterial",
    "PhysicsElectronImpactRateMaterial": "EIRateCoefMaterial",
}
_FEM_TYPE_LINE = re.compile(
    r"(?m)^(?P<indent>[ \t]*type[ \t]*=[ \t]*)(?P<name>"
    + "|".join(map(re.escape, RENAMED_FEM_KERNEL_TYPES))
    + r")(?P<end>[ \t]*\r?$)"
)


def remap_staged_fem_types(chemistry: Path, ordered: list[str]) -> dict:
    """Rebind only staged input type fields to registered canonical C++ classes."""
    if len(ordered) not in (10, 11):
        raise ValueError("Unexpected S6 input layer count for FEM type remap")
    files = {}
    writes = []
    totals = dict.fromkeys(RENAMED_FEM_KERNEL_TYPES, 0)
    for relative in ordered:
        name = Path(relative).name
        if name != relative.split("/")[-1] or not name.endswith(".i"):
            raise ValueError("Unsafe S6 staged layer name")
        path = chemistry / name
        original = path.read_bytes()
        counts = dict.fromkeys(RENAMED_FEM_KERNEL_TYPES, 0)

        def replace_type(match):
            old = match.group("name")
            counts[old] += 1
            return match.group("indent") + RENAMED_FEM_KERNEL_TYPES[old] + match.group("end")

        updated = _FEM_TYPE_LINE.sub(replace_type, original.decode("utf-8"))
        if _FEM_TYPE_LINE.search(updated):
            raise ValueError("Unconverted archived FEM Kernel type remains")
        for old, count in counts.items():
            totals[old] += count
        output = updated.encode("utf-8")
        writes.append((path, output))
        files[name] = {
            "original_sha256": hashlib.sha256(original).hexdigest(),
            "staged_sha256": hashlib.sha256(output).hexdigest(),
            "type_replacements": {old: count for old, count in counts.items() if count},
        }
    if not any(totals.values()):
        raise ValueError("Expected historical FEM Kernel types in staged S6 inputs")
    for path, output in writes:
        if path.read_bytes() != output:
            path.write_bytes(output)
    return {
        "status": "STAGED_TYPES_RENAMED_WITHOUT_FACTORY_ALIASES",
        "totals": totals,
        "files": files,
    }



# The archived S6 closures use log-molar electron states, but their old
# factory/output names are not registered in the present PhysicsApp.
# Transform disposable public P2 B/D inputs only. No old factory alias, no
# new physics model, and no claim of P3 or physical S6 equivalence.
_S6_CLOSURE_BLOCK = re.compile(
    r"(?m)^  \[(?P<name>mean_energy|electron_transport)\][ \t]*\r?\n"
    r"(?P<body>(?:^    [^\r\n]*\r?\n)+)"
    r"^  \[\][ \t]*(?:\r?\n|$)"
)


def migrate_staged_electron_closure(chemistry: Path, ordered: list[str],
                                    variant: str) -> dict:
    """Fail-closed, provenance-recorded S6 P2 mean energy + lookup cutover."""
    if variant not in ("B", "D") or len(ordered) != (10 if variant == "B" else 11):
        raise ValueError("Unexpected S6 closure variant or input layer count")
    if variant == "D" and Path(ordered[-1]).name != "migrated_continuity.i":
        raise ValueError("Unexpected D option sidecar")
    files = [chemistry / Path(name).name for name in ordered]
    if any(Path(name).name != name.split("/")[-1] or
           not name.endswith(".i") for name in ordered):
        raise ValueError("Unsafe S6 closure input layer")
    found = {}
    changes = {}
    writes = []
    replaced_consumers = 0
    for path in files:
        original = path.read_text(encoding="utf-8")
        revised = original
        matches = list(_S6_CLOSURE_BLOCK.finditer(original))
        for match in reversed(matches):
            owner = match.group("name")
            if owner in found:
                raise ValueError("S6_CLOSURE_DUPLICATE_OWNER: " + owner)
            values = {}
            for line in match.group("body").splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                item = re.fullmatch(
                    r"    ([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*([^\r\n]+)", line)
                if not item or item.group(1) in values:
                    raise ValueError("S6_CLOSURE_INVALID_PARAMETER: " + owner)
                values[item.group(1)] = item.group(2).strip()
            if owner == "mean_energy":
                expected = {
                    "type": "PhysicsElectronMeanEnergyMaterial",
                    "electron_energy_density": "log_energy",
                    "electron_density": "log_ne" if variant == "B" else "log_e",
                    "state_form": "log_molar_eV",
                    "block": "plasma",
                }
                if values != expected:
                    raise ValueError("S6_MEAN_ENERGY_IDENTITY_UNPROVED: " + repr(values))
                body = (
                    "    type = ElectronEnergyMaterial\n"
                    "    electron_energy_density = log_energy\n"
                    "    electron_density = " + expected["electron_density"] + "\n"
                    "    state_form = log_molar_eV\n"
                    "    block = plasma\n"
                )
            else:
                expected = {
                    "type": "PhysicsElectronTransportLookupMaterial",
                    "property_table_file": "'../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'",
                    "mean_energy": "mean_en_solved",
                    "pressure": "p",
                    "gas_temperature": "T_g_fixed",
                    "bounds_policy": "clamp",
                    "block": "plasma",
                }
                if values != expected:
                    raise ValueError("S6_LOOKUP_IDENTITY_UNPROVED: " + repr(values))
                body = (
                    "    type = DDTransportMaterial\n"
                    "    species_id = e\n"
                    "    model = lookup\n"
                    "    table_file = " + expected["property_table_file"] + "\n"
                    "    table_units = reduced\n"
                    "    pressure = p\n"
                    "    gas_temperature = T_g_fixed\n"
                    "    bounds_policy = clamp\n"
                    "    fluid_energy = true\n"
                    "    block = plasma\n"
                )
            old = match.group(0).encode("utf-8")
            new_block = (
                match.group(0)[:match.start("body") - match.start()]
                + body + match.group(0)[match.end("body") - match.start():]
            )
            found[owner] = {
                "source_layer": path.name,
                "original_block_sha256": hashlib.sha256(old).hexdigest(),
                "migrated_block_sha256": hashlib.sha256(new_block.encode("utf-8")).hexdigest(),
            }
            revised = revised[:match.start("body")] + body + revised[match.end("body"):]
        revised, count = re.subn(
            r"(?<![A-Za-z0-9_])mean_en_solved(?![A-Za-z0-9_])",
            "e_energy_eV", revised)
        replaced_consumers += count
        if ("PhysicsElectronMeanEnergyMaterial" in revised or
                "PhysicsElectronTransportLookupMaterial" in revised or
                "mean_en_solved" in revised):
            raise ValueError("S6_CLOSURE_RETIRED_REFERENCE_REMAINS")
        changes[path.name] = {
            "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
            "staged_sha256": hashlib.sha256(revised.encode("utf-8")).hexdigest(),
        }
        writes.append((path, revised))
    if set(found) != {"mean_energy", "electron_transport"} or replaced_consumers == 0:
        raise ValueError("S6_CLOSURE_OWNER_OR_CONSUMERS_MISSING")
    # Everything above is verified before modifying any staged file.
    for path, revised in writes:
        if path.read_text(encoding="utf-8") != revised:
            path.write_text(revised, encoding="utf-8")
    return {
        "status": "SCRATCH_ONLY_LOG_MOLAR_CLOSURE_MIGRATED",
        "owners": found,
        "consumer_renames": replaced_consumers,
        "files": changes,
        "P3": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }



def migrate_staged_wall_owners(chemistry: Path, ordered: list[str]) -> dict:
    """Reuse the independently tested wall-owner audit on disposable S6 P2 copies.

    Archive bytes and Chemistry/Physics C++ stay untouched. The helper proves
    each species/charge owner before rewriting *all* wall consumer references.
    """
    wall_path = (ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/"
                 "prepare_s6_run_input.py")
    spec = importlib.util.spec_from_file_location("issue402_s6_p2_wall_audit", wall_path)
    if spec is None or spec.loader is None:
        raise ValueError("S6_WALL_AUDIT_MODULE_UNAVAILABLE")
    wall = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wall)
    paths = [chemistry / Path(name).name for name in ordered]
    if any(Path(name).name != name.split("/")[-1] or
           not name.endswith(".i") for name in ordered):
        raise ValueError("S6_WALL_UNSAFE_STAGED_LAYER")
    if len(paths) != len(set(paths)):
        raise ValueError("S6_WALL_DUPLICATED_STAGED_LAYER")
    original = {path: path.read_text(encoding="utf-8") for path in paths}
    updated, audit = wall.canonicalize_staged_wall_inputs(original)
    if set(updated) != set(original):
        raise ValueError("S6_WALL_UNEXPECTED_STAGED_FILE_SET")
    owners = audit.get("wall_material_owners", [])
    if (audit.get("owner_count") != 4 or
            {item["species_id"] for item in owners} != {"O2p", "Om", "Op", "e"}):
        raise ValueError("S6_WALL_OWNER_COUNT_OR_SPECIES_UNPROVED")
    if not audit.get("consumer_and_reference_replacements"):
        raise ValueError("S6_WALL_CONSUMER_CUTOVER_MISSING")
    for text in updated.values():
        if ("PhysicsIonWallTotalFluxMaterial" in text or
                "PhysicsElectronAdjacentSheathWallFluxMaterial" in text or
                "PhysicsElectronWallFluxMaterial" in text):
            raise ValueError("S6_WALL_RETIRED_FACTORY_REMAINS")
    audit["files"] = {
        path.name: {
            "original_sha256": hashlib.sha256(original[path].encode("utf-8")).hexdigest(),
            "staged_sha256": hashlib.sha256(updated[path].encode("utf-8")).hexdigest(),
        }
        for path in paths
    }
    # Atomic validation before any scratch write; fail closed on every owner.
    for path in paths:
        if original[path] != updated[path]:
            path.write_text(updated[path], encoding="utf-8")
    audit["P3"] = "NOT_RUN"
    audit["science"] = "SCIENCE_HOLD"
    return audit


def check_source(expected_head: str, historical: Path, binary: Path) -> dict:
    if git_head(ROOT) != expected_head or git_head(historical) != HISTORICAL_SHA:
        raise ValueError("Candidate or historical Git source HEAD mismatch")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "--",
                       "physics_app"], check=False).returncode != 0:
        raise ValueError("Candidate PhysicsApp tracked source is dirty")
    if binary.resolve() != (ROOT / "physics_app/physics-opt").resolve():
        raise ValueError("Binary path is not the exact checkout's PhysicsApp binary")
    if not binary.is_file() or binary.stat().st_size == 0:
        raise ValueError("Native build binary missing/empty")
    mesh = historical / p2.CHEM / "baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
    if not mesh.is_file() or not mesh.stat().st_size:
        raise ValueError("Prepared original S6 public mesh absent")
    if (historical / p2.CHEM / "private_rates").exists():
        raise ValueError("Protected rate folder must not exist in historical checkout")
    provenance_path = ROOT / "experiments/Issue402_plasma_dsl_g1/evidence/native_p1_identity.json"
    if not provenance_path.is_file():
        raise ValueError("Same-job native P1 provenance is absent")
    provenance = json.loads(provenance_path.read_text())
    build_log = ROOT / "experiments/Issue402_plasma_dsl_g1/evidence/native_build.log"
    if (provenance.get("schema") != "issue402.native_p1.job_local.v1" or
        provenance.get("reusable_scope") != "same_exact_head_ci_job_only" or
        provenance.get("source_sha") != expected_head or
        provenance.get("oci_image") != OCI or
        provenance.get("binary_sha256") != sha_file(binary) or
        provenance.get("build_log_sha256") != sha_file(build_log) or
        provenance.get("P1") != "PASS"):
        raise ValueError("Exact-head native P1 build provenance/binary SHA mismatch")
    return {"source_sha": expected_head, "historical_sha": HISTORICAL_SHA,
            "binary_sha256": sha_file(binary), "historical_mesh_sha256": sha_file(mesh),
            "build_image": OCI}


def run_one(binary: Path, binary_sha: str, workspace: Path,
            inputs: list[str], log: Path, timeout_seconds: int) -> dict:
    if sha_file(binary) != binary_sha:
        raise ValueError("Native P1 executable mutated before P2")
    command = ("/workspace/physics_app/physics-opt --check-input -i " +
               " ".join(shlex.quote(x) for x in inputs))
    args = ["docker", "run", "--rm", "--network", "none",
            "--entrypoint", "/bin/bash", "--user", "0:0",
            "--workdir", "/case",
            "--env", "OXYGEN_RESEARCH_400=1",
            "--env", "OXYGEN_RESEARCH_FULL24=0",
            "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
            "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
            "--mount", f"type=bind,src={ROOT.resolve()},dst=/workspace,readonly",
            "--mount", f"type=bind,src={workspace.resolve()},dst=/case",
            OCI, "-lc",
            ("set -euo pipefail; source /environment; "
             # Clean the root-owned scratch .jitcache in the isolated case
             # container before host TemporaryDirectory removes the workspace.
             "trap 'rm -rf /case/.jitcache' EXIT; " + command)]
    try:
        result = subprocess.run(args, capture_output=True, text=True,
                                timeout=timeout_seconds, check=False)
        out = result.stdout + "\n" + result.stderr
        log.write_text(out)
        good = result.returncode == 0 and "Syntax OK" in out
        if good:
            classification = "NATIVE_CHECK_INPUT_PASS"
        elif result.returncode == 127 and "error while loading shared libraries" in out:
            classification = "NATIVE_RUNTIME_LINKER_ERROR"
        elif result.returncode == 127:
            classification = "NATIVE_PROCESS_FAILED_BEFORE_INPUT"
        else:
            classification = "NATIVE_CHECK_INPUT_REJECTED"
        return {"P2": "PASS" if good else "HOLD",
                "exit_code": result.returncode, "log_sha256": sha_file(log),
                "syntax_ok": "Syntax OK" in out, "classification": classification}
    except subprocess.TimeoutExpired:
        log.write_text("P2 timeout, no solve was launched\n")
        return {"P2": "HOLD", "classification": "NATIVE_CHECK_INPUT_TIMEOUT",
                "log_sha256": sha_file(log)}


def persist_report(evidence: Path, report: dict) -> None:
    """Atomic checkpoint independent of root-owned Native scratch cleanup."""
    evidence.mkdir(parents=True, exist_ok=True)
    target = evidence / "issue402_option_s6_p2_status.json"
    pending = evidence / "issue402_option_s6_p2_status.json.tmp"
    pending.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.replace(pending, target)


def execute(historical: Path, binary: Path, expected_head: str,
            evidence: Path, timeout_seconds: int = 1200) -> dict:
    validate_overlay()
    gate_file = evidence / "option_s6_environment.json"
    if not gate_file.is_file():
        raise ValueError("Independent public P0/environment gate evidence missing")
    gate = json.loads(gate_file.read_text())
    if (gate.get("source_sha") != expected_head or gate.get("image") != OCI or
        any(gate.get(k) != "PASS" for k in
            ("public_p0", "docker_mount", "root_scratch_create_and_cleanup", "host_cleanup"))):
        raise ValueError("Independent P0/environment gate evidence does not match exact source/OCI")
    public = p2.preflight(ROOT)
    identity = check_source(expected_head, historical, binary)
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"gate": "Issue402 S6 option-only public P2",
              "status": "HOLD", "science": "SCIENCE_HOLD", "P0": "PASS",
              "P1": "PASS_SOURCE_BOUND_BINARY",
              "P2": "HOLD", "P3": "NOT_RUN", "P4": "NOT_RUN",
              "identity": identity,
              "original_immutable_candidate_sha": p2.PINNED_CANDIDATE,
              "public_deck_manifest_sha256": sha_file(
                  ROOT / p2.DECKS / "manifest.json"),
              "option_overlay_sha256": OVERLAY_SHA256,
              "checks": {}}
    if public.get("P0") != "PASS":
        raise ValueError("Public reference P0 is not PASS")
    persist_report(evidence, report)
    try:
        with tempfile.TemporaryDirectory(prefix="issue402_option_s6_p2_",
                                         dir=os.getenv("RUNNER_TEMP", None)) as tmp:
            root = Path(tmp)
            manifest = json.loads((ROOT / p2.DECKS / "manifest.json").read_text())
            for case in CASES:
                report["checks"][case] = {}
                for variant in VARIANTS:
                    label = f"{case}_{variant}"
                    staged = root / label
                    try:
                        old_variant = "B" if variant == "B" else "C"
                        scratch_migration = None
                        # Original B stays byte-identical. D starts directly
                        # from the pinned debug-free physics base; no injection
                        # and no subsequent stripping of obsolete D1 probes.
                        d_base = (ROOT / "experiments/Issue402_plasma_dsl_g1/native/"
                                  "s6_c0_physics_base_no_d1.i") if variant == "D" else None
                        ordered = p2.stage(ROOT, historical, case, old_variant,
                                           staged, manifest, d_base_source=d_base)
                        if variant == "D":
                            overlay = staged / p2.CHEM / "migrated_continuity.i"
                            # Rewrite only the temporary D copies of the ten
                            # archived input layers. B and source archives are untouched.
                            # The resulting D input is a syntax-only migration candidate.
                            if not overlay.is_file():
                                raise ValueError("Expected original C migration sidecar is missing")
                            scratch_migration = canonicalize_staged_D_inputs(
                                staged / p2.CHEM, ordered)
                            # The FileName parameter is resolved from the staged input directory.
                            # Only a disposable JSON copy is created; the repository file is immutable.
                            shutil.copy2(ROOT / "experiments/Issue402_plasma_dsl_g1/plasma_species_only.json",
                                         staged / p2.CHEM / "plasma_species_only.json")
                            overlay.write_text(OVERLAY, encoding="utf-8")
                            if sha_file(overlay) != OVERLAY_SHA256:
                                raise ValueError("Staged D sidecar SHA is incorrect")
                        scratch_closure = migrate_staged_electron_closure(
                            staged / p2.CHEM, ordered, variant)
                        scratch_wall = migrate_staged_wall_owners(
                            staged / p2.CHEM, ordered)
                        scratch_types = remap_staged_fem_types(staged / p2.CHEM, ordered)
                        log = evidence / f"S6_{label}_P2.log"
                        report["checks"][case][variant] = run_one(
                            binary, identity["binary_sha256"], staged, ordered,
                            log, timeout_seconds)
                        report["checks"][case][variant]["layers"] = len(ordered)
                        report["checks"][case][variant]["scratch_fem_type_remap"] = scratch_types
                        report["checks"][case][variant]["scratch_electron_closure"] = scratch_closure
                        report["checks"][case][variant]["scratch_wall_owners"] = scratch_wall
                        if scratch_migration is not None:
                            report["checks"][case][variant]["scratch_migration"] = scratch_migration
                    except Exception as exc:
                        report["checks"][case][variant] = {
                            "P2": "HOLD", "classification": type(exc).__name__,
                            "error": str(exc)[:250]}
                    persist_report(evidence, report)

            checks = [report["checks"][c][v]["P2"] for c in CASES for v in VARIANTS]
            report["P2"] = "PASS" if checks == ["PASS"] * 4 else "HOLD"
            report["status"] = "P2_PASS_CLEANUP_PENDING" if report["P2"] == "PASS" else "HOLD"
            report["cleanup"] = "PENDING"
            persist_report(evidence, report)

    except OSError as exc:
        # Never erase actual P2 results when host cleanup of OCI-owned scratch
        # fails. The overall G2 gate still HOLDs until cleanup is resolved.
        report["cleanup"] = "HOLD"
        report["cleanup_error_class"] = type(exc).__name__
        report["status"] = "HOLD_INFRASTRUCTURE_CLEANUP"
        persist_report(evidence, report)
        return report
    report["cleanup"] = "PASS"
    report["status"] = "PASS" if report["P2"] == "PASS" else "HOLD"
    persist_report(evidence, report)
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.historical.resolve(), args.binary.resolve(),
                         args.expected_head, args.evidence.resolve())
        exit_code = 0 if (result["P2"] == "PASS" and result.get("cleanup") == "PASS" and result["status"] == "PASS") else 3
    except Exception as exc:
        result = {"gate": "Issue402 S6 option-only public P2",
                  "status": "HOLD", "P2": "HOLD", "P3": "NOT_RUN", "P4": "NOT_RUN",
                  "science": "SCIENCE_HOLD",
                  "classification": type(exc).__name__, "blocker": str(exc)[:400]}
        exit_code = 3
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / "issue402_option_s6_p2_status.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
