#!/usr/bin/env python3
from pathlib import Path
import copy, hashlib, json, os, re, sys

HERE=Path(__file__).resolve().parent
QPX_ROOT=Path(os.environ.get("QPX_ROOT", str(HERE.parents[4]))).resolve()
exp=json.loads((HERE/"expected.json").read_text())

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def structural_errors(t):
    fail=[]
    required=[
      "type = QPXFVConservativeMassFractionTimeDerivative",
      "type = WCNSFVMassTimeDerivative",
      "type = QPXFVMassFractionAdvection",
      "type = QPXFVMixtureAveragedDiffusion",
      "type = QPXFVElectrostaticDrift",
      "type = QPXFVHeavyMassElectromigrationCorrection",
      "scheme = implicit-euler",
      "expression = '-${E0_migration}*x'",
      "E0_migration = 0.01",
      "property_name = mu_O2p",
      "property_name = mu_Om",
      "property_name = mu_Op",
      "expression = '${e_over_kB_K_per_V}*dcoef/tgas'",
      "ion_mass_fractions = 'w_O2p w_Om w_Op'",
      "ion_mobilities = 'mu_O2p mu_Om mu_Op'",
      "ion_charges = '1 -1 1'",
    ]
    for tok in required:
        if tok not in t: fail.append("missing contract token: "+tok)

    counts={
      "time":t.count("type = QPXFVConservativeMassFractionTimeDerivative"),
      "adv":t.count("type = QPXFVMassFractionAdvection"),
      "diff":t.count("type = QPXFVMixtureAveragedDiffusion"),
      "drift":t.count("type = QPXFVElectrostaticDrift"),
      "corr":t.count("type = QPXFVHeavyMassElectromigrationCorrection"),
      "einstein_expr":t.count("expression = '${e_over_kB_K_per_V}*dcoef/tgas'"),
      "corr_species":t.count("ion_mass_fractions = 'w_O2p w_Om w_Op'"),
      "corr_mobility":t.count("ion_mobilities = 'mu_O2p mu_Om mu_Op'"),
      "corr_charge":t.count("ion_charges = '1 -1 1'"),
    }
    want={"time":6,"adv":6,"diff":6,"drift":3,"corr":6,
          "einstein_expr":3,"corr_species":6,"corr_mobility":6,"corr_charge":6}
    if t.count("E0_migration = 0.01") != 1:
        fail.append("accepted EVR2 prescribed forcing must be pinned exactly once: E0_migration = 0.01")
    for k,v in want.items():
        if counts[k]!=v: fail.append(f"{k} count={counts[k]}, expected {v}")

    # Exact direct species/charge/mobility map.
    direct=[
      ("O2p","mu_O2p","1"),
      ("Om","mu_Om","-1"),
      ("Op","mu_Op","1"),
    ]
    for s,mu,z in direct:
        pattern=(
          rf"\[{s}_electrostatic_drift\][\s\S]*?"
          rf"variable\s*=\s*w_{s}\b[\s\S]*?"
          rf"mobility\s*=\s*{mu}\b[\s\S]*?"
          rf"charge_number\s*=\s*{re.escape(z)}\b"
        )
        if not re.search(pattern,t):
            fail.append(f"direct drift mapping mismatch for {s}")

    # No direct drift on neutrals or constrained O2.
    for s in ["O2s","O","Os","O2"]:
        if re.search(rf"\[{s}_electrostatic_drift\]",t):
            fail.append(f"neutral/constrained direct drift present: {s}")

    # Q-1 ownership: O2 is constrained, never independently solved.
    if "property_name = w_O2_constraint" not in t:
        fail.append("missing Q-1 O2 constraint")
    if re.search(r"^\s*\[w_O2\]\s*$",t,re.MULTILINE):
        fail.append("O2 must not be an independent variable")

    # Path-B exclusivity.
    for tok in ["heavy_mass_correction_velocity","ion_drift_velocity_",
                "u_slip =","v_slip =","w_slip ="]:
        if tok in t: fail.append("Path-B exclusivity violation: "+tok)

    # Migration is internal-only in #15; wall loss and Poisson are downstream/out of scope.
    boundary_contract="boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'"
    if t.count(boundary_contract)!=9:
        fail.append("migration boundary-avoid contract must appear in all 9 migration/correction kernels")
    if "phi_charge_source" in t or "poisson_charge_source" in t:
        fail.append("#15 promotion must not include Poisson feedback")

    # Parser namespace gate.
    reserved={"x","y","z","t","pi","e"}
    for raw in re.findall(r"functor_symbols\s*=\s*'([^']+)'",t):
        bad=reserved.intersection(raw.split())
        if bad: fail.append("reserved parser symbols "+str(sorted(bad)))

    # Structural zero-net-flux proof prerequisites:
    # exact source hashes are checked separately; here ensure all six solved
    # species receive the same correction reconstruction and O2 remains Q-1.
    corr_vars=set(re.findall(
      r"\[[A-Za-z0-9_]+_heavy_mass_em_correction\][\s\S]*?variable\s*=\s*(w_[A-Za-z0-9]+)",
      t
    ))
    expected_corr={"w_O2s","w_O2p","w_O","w_Om","w_Op","w_Os"}
    if corr_vars!=expected_corr:
        fail.append("correction variable set mismatch: "+str(sorted(corr_vars)))

    return fail

def self_test():
    good=(HERE/"physics.i").read_text()
    if structural_errors(good):
        print("R15_EVR3_STATIC_SELFTEST: FAIL good input")
        for x in structural_errors(good): print("  -",x)
        return 1
    muts=[]
    muts.append(("drop_correction",good.replace("[Os_heavy_mass_em_correction]","[Os_heavy_mass_em_correction_REMOVED]",1)))
    muts.append(("flip_charge",good.replace("charge_number = -1","charge_number = 1",1)))
    muts.append(("wrong_mobility",good.replace("mobility = mu_Op","mobility = mu_O2p",1)))
    muts.append(("break_einstein",good.replace(
        "expression = '${e_over_kB_K_per_V}*dcoef/tgas'",
        "expression = '0.5*${e_over_kB_K_per_V}*dcoef/tgas'",1)))
    muts.append(("inject_slip",good.replace("rho = rho_mat\n    block = plasma",
        "rho = rho_mat\n    u_slip = mu_O2p\n    block = plasma",1)))
    muts.append(("forcing_amplification",good.replace("E0_migration = 0.01","E0_migration = 500",1)))
    muts.append(("poisson_feedback",good+"\n# phi_charge_source\n"))
    for name,t in muts:
        if not structural_errors(t):
            print("R15_EVR3_STATIC_SELFTEST: FAIL mutation escaped",name)
            return 1
    print("R15_EVR3_STATIC_SELFTEST: PASS")
    print("R15_EVR3_STATIC_NEGATIVE_CONTROLS: PASS")
    print("R15_EVR3_Q1_ZERO_NET_FLUX_STRUCTURE_P0: PASS")
    print("R23_FORCING_CONTINUITY_SELFTEST: PASS")
    return 0

def main():
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())

    fail=[]
    for fn,key in [
      ("qvt.msh","qvt_sha256"),
      ("mesh.i","mesh_i_sha256"),
      ("transport_data.txt","transport_data_sha256"),
    ]:
        p=HERE/fn
        if not p.is_file(): fail.append("missing "+fn)
        elif sha(p)!=exp[key]: fail.append(fn+" SHA mismatch")

    # Rebuild exact combined input.
    if (HERE/"mesh.i").is_file() and (HERE/"physics.i").is_file():
        (HERE/"input.i").write_bytes((HERE/"mesh.i").read_bytes()+b"\n"+(HERE/"physics.i").read_bytes())
    if sha(HERE/"physics.i")!=exp["physics_sha256"]:
        fail.append("physics.i SHA mismatch")
    if not (HERE/"input.i").is_file() or sha(HERE/"input.i")!=exp["input_sha256"]:
        fail.append("rebuilt input.i SHA mismatch")

    # Pin accepted #22 conservative accumulation source identity.
    for rel,want in exp["production_source_sha256"].items():
        p=QPX_ROOT/rel
        if not p.is_file(): fail.append("missing production source "+str(p))
        elif sha(p)!=want: fail.append("production source SHA mismatch "+rel)

    # Validate the audited #15 face-flux semantic source contract.
    # Exact SHA values were not part of the accepted audit evidence, so do not
    # manufacture an identity pin.  Instead require the source semantics that
    # establish the direct/correction face-flux identity.
    migration_source_paths=[]
    for rel,tokens in exp["migration_source_contract"].items():
        p=QPX_ROOT/rel
        migration_source_paths.append(p)
        if not p.is_file():
            fail.append("missing migration source "+str(p))
            continue
        text=p.read_text(errors="replace")
        for tok in tokens:
            if tok not in text:
                fail.append("migration source semantic contract mismatch "+rel+": "+tok)

    t=(HERE/"physics.i").read_text()
    fail.extend(structural_errors(t))

    cfg=json.loads((HERE/"test.json").read_text())
    if cfg.get("validation_schema")!=2: fail.append("validation_schema=2 required")
    specs=cfg.get("temporal_csv",[])
    if len(specs)!=1 or specs[0].get("initial_row_policy")!="exclude_observation":
        fail.append("runner-owned initialization-row exclusion missing")
    args=[str(x) for x in cfg.get("checker_args",[])]
    if "input_out.physical.csv" not in args or "input_out.csv" in args:
        fail.append("checker temporal CSV routing mismatch")

    # The executable must not predate any pinned production source.
    exe=Path(os.environ.get("QPX_EXECUTABLE",QPX_ROOT/"qpx-opt")).resolve()
    if exe.is_file():
        source_paths=[]
        for rel in list(exp["production_source_sha256"])+list(exp["migration_source_contract"]):
            p=QPX_ROOT/rel
            if p.is_file(): source_paths.append(p)
        if source_paths and exe.stat().st_mtime < max(p.stat().st_mtime for p in source_paths):
            fail.append("SOURCE_REBUILD_REQUIRED: qpx-opt older than pinned #15/#22 production source")

    print("R15_EVR3_STRUCTURAL_P0:", "PASS" if not fail else "FAIL")
    print("R15_EVR3_Q1_ZERO_NET_FLUX_STRUCTURE_P0:", "PASS" if not fail else "FAIL")
    print("R23_FORCING_CONTINUITY_P0:", "PASS" if not fail else "FAIL")
    if fail:
        for x in fail: print("  -",x)
        raise SystemExit(2)

if __name__=="__main__":
    main()
