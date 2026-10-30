# Issue #419 — HPEM numerical electron-collision source request / acquisition contract

**Prepared:** 2026-10-30. **STATUS: REQUEST DRAFTED; NOT SENT; NUMERIC DATA NOT ACQUIRED.**
**Target:** [HPEM official data/reaction catalog](https://cpseg.eecs.umich.edu/data.html), source listing [e_reactions.pdf v174a (2026-02-16)](https://cpseg.eecs.umich.edu/pub/data/e_reactions.pdf).

## Scope: 22 user-approved electron-impact Chemistry reactions

`401, 407, 411, 412, 413, 414, 415, 417, 2259, 2058, 2067, 2068, 2069, 2072, 2073, 2074, 943, 944, 2738, 935, 936, 941`

This list is a subset of the canonical **33 entries** in [the final registry](OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_33.csv). It excludes 3 QDB heavy-particle formula rows and all kinetic-only sources, and **does not request** unapproved O2 three-body attachment, KIN-R01, KIN-E01 or KIN-E02.

## Request to HPEM maintainer — prepared, NOT dispatched

**Intended recipient:** Prof. Mark J. Kushner, `mjkush@umich.edu` (as listed by the official provider).

**Subject:** Request for numerical HPEM oxygen electron-collision cross sections (22 special numbers)

Dear Professor Kushner,

For scientific validation of an oxygen Boltzmann solver, I would like to request the original numerical electron-impact collision cross sections from the HPEM `RFXSECS_NEW.FOR` database corresponding to the following 22 special numbers:

`401, 407, 411, 412, 413, 414, 415, 417, 2259, 2058, 2067, 2068, 2069, 2072, 2073, 2074, 943, 944, 2738, 935, 936, 941`

The requested energy window is **0–200 eV**, with an indicative linear output grid of **0.1 eV** (2001 values including endpoints) *where supported*. More importantly, please preserve and identify the **native tabulated energy knots, near-threshold structure and original source/reference** wherever possible; native knots are preferred over resampling or fitting. If HPEM's native energy support differs from 0–200 eV, please identify the valid interval and extrapolation convention rather than generating unsupported values. Values in energy/eV and sigma/m² (or explicitly annotated original units) are preferred.

In particular, please confirm the source-specific reaction identity, threshold, product state/branching and electron energy-loss convention for special numbers **411, 413, 414, 2068, 2073 and 2074**. The public v174a catalog lists **2068 = 3.52 eV**, **2073 = 13.72 eV** and **2074 = 16.02 eV**. Distinguishing an effective electronic-energy-loss channel from a state-resolved dissociation channel is important for our solver.

Please also indicate any redistribution/use restrictions and the recommended source attributions for each dataset.

Thank you.

## Actual acquisition gating

- **Phelps** original document: [A. V. Phelps compilation](https://us.lxcat.net/notes/index.php?download=phelps5) is externally readable, but an **unchanged, locally stored, SHA256-identified PDF** has **not** been acquired in the current execution environment. The PR extractor selects **14** channels from the 18 source sections. It must not publish licensed tables to a PR; see [LXCat redistribution policy](https://us.lxcat.net/instructions/redistribution.php).
- **HPEM:** Public catalog identifies special numbers and thresholds; provider explicitly asks for a message listing collision IDs, energy range, point resolution, and energy vs velocity grid. Source **numerical sigma(E) is NOT in the public catalog**. No email has been sent.
- **Atomic oxygen elastic (`KIN-EL-O`):** Identify an authoritative numeric e + O(3P) momentum/recoil dataset; Itikawa & Ichimura (1990), DOI [10.1063/1.555857](https://doi.org/10.1063/1.555857), is bibliographic, not a source-validated numerical file in this repo.
- **Effective O2 momentum (`KIN-M01`):** Use Phelps effective Qm for first-harmonic scattering but do NOT mistake effective Qm for independently determined pure elastic recoil or add O2 elastic a second time.
- **Figure vs source:** 411=4.50, 413=8.40, 414=10.00 eV are confirmed in both the user-provided 25-row reaction screenshot and HPEM v174a listing. Their *identity review* may close, but 411 dissociation energetics and 413/414 excited product branching remain **science gates**. 2068=3.52 despite ~4.14 eV 2O(3P) product asymptote from O2(a1Delta) merits separate HPEM interpretation, not a silent threshold override. 2073/2074 supersede obsolete 5.023/19.023 eV model mappings.
- **Duplicate sink:** 412 Phelps `6.0 LOSS` and Cosby explicit O2 dissociation cannot be appended as two independent full energy sinks without a validated energy closure.
- **Status taxonomy:** `IDENTITY_VERIFIED` ≠ `NUMERIC_SIGMA_VERIFIED` ≠ `CHEMICAL_SOURCE_ACCEPTED` ≠ `BOLTZMANN_PHYSICS_PASS`.
- **Policy:** The 33-row chemistry+kinetic inventory is frozen. All numerical source datasets must carry origin URL, retrieval timestamp, native units and grid, checksum, transfer/license restrictions, energy threshold/product mapping, and state-matched references. Only then produce solver EEDF and rate lookup, validate normalization, positivity, sensitivity, electron/energy balance and independent BOLSIG+ comparison.

## Links / evidence

- **Canonical machine-readable gates:** [OXYGEN_33_SOURCE_ACQUISITION_GATE_MATRIX.csv](OXYGEN_33_SOURCE_ACQUISITION_GATE_MATRIX.csv)
- **Canonical scope:** [OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_33.csv](OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_33.csv)
- **Source extraction preparation:** [collect_phelps_o2_core_set.py](collect_phelps_o2_core_set.py)
- **HPEM original catalog:** <https://cpseg.eecs.umich.edu/pub/data/e_reactions.pdf>
- **HPEM provider:** <https://cpseg.eecs.umich.edu/data.html>
- **Phelps original:** <https://us.lxcat.net/notes/index.php?download=phelps5>

**No physical calculation, rate lookup or runtime chemistry activation has been performed in this acquisition phase.**
