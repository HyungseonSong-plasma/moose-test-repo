#!/usr/bin/env python3
from pathlib import Path
import hashlib
import re
import sys

EXPECTED_C_SHA = "4533a3a2fe0d77f3d85ca171f9093907a76514dd024c5392c08dd8d17a2f4b7e"
EXPECTED_H_SHA = "8f97db663781c5788e18bb98cca284a9173597a2b7bfe44f148ca2beef9391c5"

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def has(text, pattern, flags=0):
    return re.search(pattern, text, flags) is not None

def checks(c, h):
    # These checks intentionally focus on the accepted R14 contract and
    # retained R3 dynamic-screening path, not broad C++ formatting.
    return {
        "candidate_C_sha256": sha256(C_PATH) == EXPECTED_C_SHA,
        "candidate_H_sha256": sha256(H_PATH) == EXPECTED_H_SHA,
        "D_mix_param": has(c, r'"D_mix_names"'),
        "D_mix_result_field": has(h, r"\bVec\s+D_mix\s*;"),
        "D_mix_member": has(h, r"\b_D_mix_names\b"),
        "D_mix_property": has(c, r"addFunctorProperty<ADReal>[\s\S]*?_D_mix_names", re.M),
        "number_density": has(c, r"number_density\s*=\s*p\s*/\s*\(\s*QPX_CONSTANTS::k_boltz\s*\*\s*T\s*\)"),
        "Dij_from_nDij": has(c, r"Dij\s*=\s*nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*/\s*number_density"),
        "skip_self": has(c, r"if\s*\(\s*j\s*==\s*i\s*\)\s*continue\s*;"),
        "mass_fraction_numerator": has(c, r"one_minus_Y\s*=\s*1\.0\s*-\s*Y\s*\[\s*i\s*\]"),
        "mole_fraction_denominator": has(c, r"denominator\s*\+=\s*X\s*\[\s*j\s*\]\s*/\s*Dij"),
        "Dmix_formula": has(c, r"D_mix\s*\[\s*i\s*\]\s*=\s*one_minus_Y\s*/\s*denominator"),
        "no_D_ref": not has(c + h, r"\bD_ref\b"),
        "legacy_DT_retained": has(c, r"_D_T_names") and has(h, r"_D_T_names"),
        "legacy_kT_retained": has(c, r"_kT_names") and has(h, r"_kT_names"),
        "electron_temperature_param": has(c, r'"electron_temperature"'),
        "electron_number_density_param": has(c, r'"electron_number_density"'),
        "debye_named_or_screening_path": has(c, r"debyeHuckel", re.I),
        "uses_eps0": has(c, r"\bEPS0\b"),
        "uses_elementary_charge": has(c, r"\bQE\b"),
        "has_attractive_repulsive_branch": has(c, r"ATTRACTIVE|REPULSIVE", re.I),
    }

def report(name, ok):
    print(f"{name}: {'PASS' if ok else 'FAIL'}")

def mutation_selftest(c, h):
    # Mutations are applied to source text, then the same contract is tested.
    # A mutation is DETECTED only when at least one intended gate flips false.
    muts = []

    m1 = c.replace("const ADReal one_minus_Y = 1.0 - Y[i];",
                   "const ADReal one_minus_Y = 1.0 - X[i];", 1)
    muts.append(("M1_Y_to_X_numerator",
                 not has(m1, r"one_minus_Y\s*=\s*1\.0\s*-\s*Y\s*\[\s*i\s*\]")))

    m2 = re.sub(r"if\s*\(\s*j\s*==\s*i\s*\)\s*continue\s*;", "", c, count=1)
    muts.append(("M2_remove_skip_self",
                 not has(m2, r"if\s*\(\s*j\s*==\s*i\s*\)\s*continue\s*;")))

    m3 = re.sub(r"Dij\s*=\s*nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*/\s*number_density",
                "Dij = nDij[i][j] * number_density", c, count=1)
    muts.append(("M3_wrong_Dij_scale",
                 not has(m3, r"Dij\s*=\s*nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*/\s*number_density")))

    m4 = re.sub(r"denominator\s*\+=\s*X\s*\[\s*j\s*\]\s*/\s*Dij",
                "denominator += Y[j] / Dij", c, count=1)
    muts.append(("M4_wrong_denominator_fraction",
                 not has(m4, r"denominator\s*\+=\s*X\s*\[\s*j\s*\]\s*/\s*Dij")))

    m5 = c.replace("_D_mix_names[i]", "_BROKEN_D_mix_names[i]", 1)
    muts.append(("M5_remove_property",
                 not has(m5, r"addFunctorProperty<ADReal>[\s\S]*?_D_mix_names", re.M)))

    m6 = c + "\nconst Real D_ref = 1.0;\n"
    muts.append(("M6_insert_D_ref", has(m6, r"\bD_ref\b")))

    all_ok = True
    for name, detected in muts:
        print(f"{name}: {'DETECTED' if detected else 'MISSED'}")
        all_ok &= detected
    print(f"R14_DMIX_SOURCE_MUTATION_SELFTEST: {'PASS' if all_ok else 'FAIL'}")
    return all_ok

if len(sys.argv) != 3:
    raise SystemExit("usage: r14_source_contract.py QPXThermalDiffusionMaterial.C QPXThermalDiffusionMaterial.h")

C_PATH = Path(sys.argv[1]).resolve()
H_PATH = Path(sys.argv[2]).resolve()
c = C_PATH.read_text(errors="replace")
h = H_PATH.read_text(errors="replace")

print("=" * 78)
print("R14 — SOURCE CANDIDATE CONTRACT")
print("=" * 78)

items = checks(c, h)
overall = True
for k, v in items.items():
    report(k, v)
    overall &= v

print(f"R14_DMIX_SOURCE_CONTRACT: {'PASS' if overall else 'FAIL'}")

print("=" * 78)
print("R14 — MUTATION SELF-TEST")
print("=" * 78)
mut_ok = mutation_selftest(c, h)

raise SystemExit(0 if overall and mut_ok else 1)
