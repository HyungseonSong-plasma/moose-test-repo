# Boltzmann reference data and BOLSIG+ comparison contract

**Status: SPECIFICATION / HOLD — NOT yet an implemented loader or validated real-gas dataset.**

## Data origin, ownership and redistribution

Reference: https://www.lxcat.net/ and https://master.lxcat.net/instructions/how_reference.php ;
LXCat Policy on Redistribution (https://nl.lxcat.net/notes/index.php?download=lxcat_team23).

LXCat collision data remain the contributors' property; data access does **not** imply a license to redistribute data in this public repository. Test data committed to the repository must be independently authored synthetic fixtures or carry explicit redistributable rights. Real Ar and O2 cross-section downloads must be supplied via user-local paths, with any user acceptance of the source's terms performed at the provider, not by automatic scraping or bundling.

The future loader and reference suite SHALL require the following immutable, machine-recorded source evidence for every imported set:

- Source platform (e.g. LXCat), named contributor database, direct source URL, retrieval UTC date, original record identifier/revision when available.
- Exact raw downloaded file SHA-256, byte count, and independently enumerated process identifiers.
- Gas target and electronic/rovibrational state identifiers; number fractions and masses, with provenance.
- Reaction type (ELASTIC, EFFECTIVE, EXCITATION, IONIZATION, ATTACHMENT, etc.); threshold [eV] and mass-ratio provenance; collision energy [eV], cross section [m^2].
- References supplied in dataset/process headers; no fabricated provenance or dropped citations.
- Provenance of any preprocessing, filtering, unit conversion, threshold handling, or interpolation and SHA-256 of the canonical transformed dataset.
- Explicit statement whether the input elastic momentum cross section excludes or *already includes* inelastic contributions.

No missing datum may silently be replaced with a physics fallback. When a dataset uses EFFECTIVE total momentum cross sections, the current M2 interface (elastic-only momentum + separately added excitation total) MUST reject it or use a separately implemented and validated effective-to-elastic conversion with energy-by-energy nonnegative controls. Directly loading EFFECTIVE as ELASTIC would double count excitation. Never silently collapse isotropic and anisotropic differential/total/momentum-transfer cross sections.

## Reproducible BOLSIG+ reference case identity

Before treating any external comparison as physics validation, pin the following:

- Exact BOLSIG+ solver version and reference output artifact hash or independently verified executable identity.
- Database/download hash, all active process metadata, mixture composition and gas temperature.
- E/N in Townsend, energy grid/upper energy bound, any extrapolation behavior and interpolation convention.
- Two-term stationary DC model, collision model variants (including superelastic, ionization/attachment and growth), and target-state densities.
- EEPF normalization (integral sqrt(e) f0 de = 1), comparison axis and units.
- Mean energy [eV], EEPF difference with energy-weighted metric and a documented high-energy tail exclusion rule if needed, process-resolved k_j [m^3/s], and later mobility/diffusion/energy coefficients.
- Numeric tolerances chosen and justified **before** interpreting comparison results; changing tolerances to fit a candidate requires a new explicitly identified validation round.

Current M1/M2/M3 synthetic results are independent analytic/numerical invariants, **not** BOLSIG+ reproduction or physical Ar/O2 validation. At this revision, LXCat raw import, BOLSIG+ executable/oracle outputs, and real-Physics application coupling are NOT implemented.

## Ordered acceptance gates

1. Source-use rights, raw file hash, process metadata and citation completeness.
2. Parsed table positivity, strictly increasing energy, target species identification, units, domain coverage and threshold consistency; corruption/omission mutation controls.
3. EXACT raw-to-canonical collision identity and cross-section interpolation/range boundary controls.
4. Sparse-to-dense excitation parity and independent process-rate integration (already synthetic M3).
5. Pinned BOLSIG+ reference comparison over E/N points with physically complete collision set, documented growth/ionization assumptions and tail sensitivity.
6. Electron-mobility, diffusion and energy transport moments after their kinetic definitions are implemented and independently verified.
7. Real PhysicsApp `physics-opt` preflight and coupled P3 numerical/physical acceptance with the accepted imported data; no production coefficient promotion beforehand.

Reference theory: G. J. M. Hagelaar and L. C. Pitchford, Plasma Sources Science and Technology 14 (2005), 722–733, DOI:10.1088/0963-0252/14/4/011.

## M4 actual implementation — ingestion and oracle contract

### Source ingestion

The MOOSE-independent C++ utility `PhysicsBoltzmannCrossSections` reads text collision blocks per the BOLSIG+ published input convention:

```text
ELASTIC
Ar
1.37e-5
Reference: synthetic example only, not measured data
------
0.0 5.0e-20
2.0 5.0e-20
------
EXCITATION
Ar -> Ar_test_excited
0.27
Reference: synthetic example only, not measured data
------
0.0 0.0
2.0 2.0e-20
------
```

All numbers in this example are **invented synthetic test inputs**, not LXCat Argon cross sections. The parser retains comments/citations and source line, creates typed collision records and refuses malformed columns, nonfinite/negative cross sections, nonascending energy axes and incomplete blocks. It records unsupported types rather than silently filtering them. The explicit `prepareElasticExcitation` step rejects EFFECTIVE/MOMENTUM, IONIZATION, ATTACHMENT, ROTATION and reversible/superelastic excitation, unsupported target/thresholds and coverage gaps. These rejections are **physics-model HOLD**, not assertions that real Ar/O2 data are invalid. Accepting a complex dataset will require implementing the missing collision operators, not deleting their records.

The existing native C++ regression uses a **synthetic Ar/O2-labeled mixture**, compares imported input to independent direct C++ construction, and mutation-tests the fail-closed boundaries. Source/target nomenclature is realistic, but its cross section values do **not** represent either gas. No externally obtained LXCat bytes are committed.

### External BOLSIG+ numeric comparison

`python3 physics_app/ci/boltzmann_reference_compare.py --case /path/to/local/case_directory`

The directory must contain `case.json` and external source, raw BOLSIG+ export, reference JSON and candidate JSON. The case references the **SHA-256 of each of those four files**. Source metadata includes database, URL, retrieval UTC timestamp and unique process IDs. The reference metadata includes `solver=BOLSIG+`, exact version and raw export path/hash; the candidate identifies its code revision. All four declared hashes are verified against the bytes before numerical comparison.

Both JSON distribution payloads must be independently normalized to the same **energy-cell representation**:

```json
{
  "schema_version": 1,
  "conditions": {
    "reduced_field_Td": 10,
    "gas_temperature_K": 300,
    "mixture": {"Ar": 1.0},
    "model": "exactly-matched-dc-two-term-physics",
    "collision_source_sha256": "<verified-64-char-hex>"
  },
  "energy_cell_edges_eV": [0.0, 1.0, 2.0],
  "eepf_eV_minus_3_halves": [0.53033, 0.53033],
  "mean_energy_eV": 1.2,
  "rates_m3_per_s": {"Ar:excitation:1": 1e-14}
}
```

The values above are **illustrative only**, not a valid published reference and not necessarily a numerically self-consistent input to the checker. Use full-precision canonical values and exact source IDs.

The comparator requires identical physical conditions, source SHA and cell edges; rejects mismatched or unnormalized EEPF, inconsistent energy moments, nonmatching reaction inventories and missing input provenance. Given a complete predeclared tolerance set, it reports weighted EEPF L1, mean-energy relative error and per-reaction relative/zero-rate absolute error. It returns `BOLSIG_REFERENCE_PREFLIGHT_HOLD` for a construction/provenance error; `BOLSIG_REFERENCE_NUMERIC_FAIL` for a quantitatively valid but different reference; and `BOLSIG_REFERENCE_NUMERIC_PASS` only when all declared metrics pass.

**Important limitation:** The existing checker does **not** convert original native BOLSIG+ run-by-run output to the canonical cell-average JSON, and the existing implementation does **not** automatically generate candidate JSON from arbitrary imported production inputs. Those two independent, auditable export stages and a genuine BOLSIG+ reference dataset are still required before external physics parity can be claimed. The checker tests its correctness using manufactured synthetic files and mutation controls, not a genuine BOLSIG+ run. Regridding must be explicit and independently validated; the checker does not silently interpolate mismatched energy grids.

### Current evidence gate

`pytest -q tests/test_boltzmann_cross_section_import.py tests/test_boltzmann_reference_compare.py` validates the import and science-checker structure. It is **P0/P1 only**. The existing Physics runtime CI container smoke does not prove that a production MOOSE input uses this new importer. Keep PR #408 in DRAFT/HOLD pending real source process coverage, reference provenance, energy-grid equivalence, versioned physics-model comparison, and production P2/P3.

### M4 candidate-export developer tool (implemented)

The MOOSE-independent development runner `physics_app/ci/boltzmann_candidate_export.C` now connects the actual text-file reader to the accepted M3 EEPF solver and emits the canonical candidate JSON used by the comparison checker. It reads a user-local, externally supplied BOLSIG-format source file; **it does not fetch or redistribute LXCat content**. The separate comparison checker validates the user-declared source SHA-256 against the raw file bytes. Candidate export accepts a SHA-256 argument solely to preserve the declared source identity; it does not independently hash the file at this stage, so its output is **not** verified evidence unless case preflight succeeds.

Build the development runner (not a production Physics command):

```sh
g++ -std=c++17 -O2 -Iphysics_app/include/utils \
  physics_app/src/utils/PhysicsBoltzmannElasticSolver.C \
  physics_app/src/utils/PhysicsBoltzmannCrossSections.C \
  physics_app/ci/boltzmann_candidate_export.C -o /tmp/boltzmann_candidate_export
```

Invocation requires external `SOURCE_TXT SHA256 EoverN_Td Tg_K emax_eV CELLS species=fraction [species=fraction...]`; its stdout is JSON and errors return exit 2 with `BOLTZMANN_CANDIDATE_PREFLIGHT_HOLD`. The initial solver supports only elastic and one-way excitation: unsupported source reactions **will not** be discarded to force a result. When a complete real gas collision set includes ionization, attachment and reversible excitation, the current exporter must HOLD until those operators are implemented.

The C++ executable and importer are compiled by dedicated pytest cases. For a fully documented external reference case, source `process_ids` lists all relevant source reaction identifiers, and `rate_process_ids` specifically enumerates which process coefficients the reference and candidate are required to report. Distinct lists are needed because elastic momentum-transfer processes generally do not have an excitation rate coefficient. A missing or silently renamed rate process causes a preflight HOLD.

Synthetic fixtures use the decision statuses `BOLSIG_REFERENCE_SELFTEST_PASS` / `_FAIL`, **never** `BOLSIG_REFERENCE_NUMERIC_PASS`. A genuine external reference still requires a trusted raw BOLSIG+ run-by-run export and independently audited conversion to the exact comparison-cell representation. The checker verifies the raw reference export's file hash, but does not yet establish that the normalized reference JSON was faithfully transcribed from it.
