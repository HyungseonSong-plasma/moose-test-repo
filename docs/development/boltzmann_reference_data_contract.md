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

## M5 development slice — reversible excitation / superelastic collisions

**Physics convention:** a reversible BOLSIG+ `EXCITATION` record can use `Ar <-> Ar*` and a third line `u g_upper/g_lower`. The parser preserves both parameters and explicitly requires the caller to opt in to reverse-channel projection. A separate excited target with an **explicit mole fraction and elastic cross-section table** is mandatory in the current implementation. This intentionally stricter convention avoids inventing excited-state momentum transport or population densities. This is not yet a complete real Ar*/O2* population model.

For a lower-to-upper excitation with energy threshold `u`, detailed balancing constructs the inverse cross section at electron energy `epsilon`:

```text
sigma_superelastic(epsilon)
 = (g_lower/g_upper) * (epsilon+u)/epsilon
   * sigma_excitation(epsilon+u)
```

The implementation never divides by zero at the origin in the collision source: its energy-space nonlocal transfer integrates `(epsilon+u) sigma_excitation(epsilon+u)` exactly against each piecewise-constant EEPF donor cell. An electron is deposited at `epsilon+u`, with the destination-cell overlap integrated using the forward cross section. The upper-state number fraction multiplies the reverse source operator; the lower-state fraction multiplies excitation. Both are included in the total momentum-scattering cross section for the two-term field-driven energy transport. Exact per-channel conservation and full residuals apply equally to both directions. Superelastic donors whose shifted energy would lie beyond `epsilon_max` are omitted as an explicit bounded-grid truncation; sensitivity to the energy ceiling remains a mandatory physics gate.

Returned output includes (1) excitation rate per lower-state molecule, (2) superelastic rate per upper-state molecule, and (3) the **mixture-weighted net energy loss** `u * (x_lower*k_excitation - x_upper*k_superelastic)` in `eV m^3/s`. The forward-only loss field is retained for backwards compatibility; consumers must not mistake it for net energy loss in reversible cases.

The development-only candidate exporter accepts `--enable-superelastic` and emits separate reverse-rate keys `<upper_state>:superelastic:<index>`; the model tag is `elastic_excitation_superelastic_steady_dc`. With no opt-in, existing reversible input remains a hard preflight HOLD. The synthetic reference validation compares zero-field Maxwellian mean energy, forward-versus-inverse event-rate detailed balance under a Boltzmann excited-state population, dense/sparse EEPF parity and rejects invalid upper-state metadata. These controls are **not** BOLSIG+ quantitative parity or evidence of actual Ar metastable chemistry.

Current remaining gates: physical cross-section/target-state provenance, excited-state elastic assumptions, upper-energy cutoff convergence for reverse rates, detailed-balance error under grid refinement, genuine BOLSIG+ reference output conversion, particle-changing ionization and attachment source/growth formulation, and real PhysicsApp P2/P3. In particular, M5 must not cause any existing Oxygen ICP coefficient/energy source to change without accepted new physics validation.

Scientific background: Hagelaar & Pitchford, Plasma Sources Science Technology 14 (2005) 722–733; BOLSIG+ official 07/2024 documentation.

## M6a particle-changing electron collisions and growth — DEVELOPMENT/HOLD

The independent C++ PhysicsBoltzmannGrowth utility now assembles binary ionization and electron attachment source operators Q on a uniform electron-energy finite-volume grid. This is a **frozen-EEPF growth diagnostic**, NOT the self-consistent temporal-growth electron Boltzmann eigenproblem.

The discrete collision contribution is

    M_i d(n_e f0_i)/d(Nt) = sum_j Q_ij n_e f0_j
    M_i = integral_cell_i sqrt(epsilon) d(epsilon)

Ionization (e + A -> 2e + A+) with threshold u removes one incident electron at epsilon and deposits exactly two electrons at (epsilon-u)/2: equal sharing, per the explicitly selected BOLSIG+ option. Each ionization event has net electron number +1. Electron attachment removes one electron (net -1) and has no product electron deposited. Off-grid donor/recipient overlaps integrate epsilon*sigma(epsilon) with exact piecewise-linear cross-section quadrature.

The acceptance invariant is columnwise:

    sum_i Q_ij = ionization_event_column_j - attachment_event_column_j

Rate coefficients per target molecule have units m^3/s and use sqrt(2e/m_e)*integral(epsilon*sigma_j(epsilon)*f0(epsilon) d(epsilon)). The **reduced temporal-growth diagnostic** from the pre-existing M5 EEPF is

    (1/(N*n_e)) dn_e/dt = sum(x_k*k_ion,k) - sum(x_k*k_attachment,k)

with units m^3/s. The mixture-weighted ionization threshold energy loss per electron and neutral is sum(x_k*u_k*k_ion,k) [eV m^3/s]. This is NOT the complete electron-energy balance: electron birth/dilution, attachment energy removal, and other collision power terms are not included.

The new explicit prepareGrowthPhysics import mode retains ionization and attachment records rather than silently dropping them to pass the excitation-only filter. Unsupported EFFECTIVE/MOMENTUM, ROTATION, missing targets, incomplete energy coverage and unsupported model variants fail closed. All Ar/O2-named fixtures are **synthetic values authored for tests**, not real LXCat cross sections.

The developer candidate exporter now supports --diagnose-frozen-growth to emit M5 EEPF, process-resolved ionization and attachment rates, and a clearly distinct frozen_eepf_reduced_temporal_growth_m3_per_s field. The source file and SHA-256 are supplied by the caller; independent raw-byte verification remains the external reference checker responsibility. Without the explicit opt-in, a full particle-changing collision file remains rejected by the M5-only path.

M6a regression covers +1/-1 electron events, independent analytical constant-cross-section moments, number/threshold energy transfer at grid resolution, 100/250/800-cell audit, invalid input mutation, complete typed importer and explicit developer CLI opt-in. This is numerical P0/P1 evidence only.

**M6b mandatory remaining gate:** self-consistently solve the full energy-space elastic+excitation+superelastic+ionization+attachment temporal-growth generalized eigenvalue problem with the mass metric M, independent eigenpair residual and growth-rate convergence, and independently captured BOLSIG+ temporal-growth parity. BOLSIG+ spatial growth (SST) is a separate model; never label frozen-EEDF rates as SST or temporal-growth EEPF validation. Do not merge or promote production Oxygen ICP coefficients until real source provenance and P2/P3 physics acceptance.

References: Hagelaar & Pitchford (2005), DOI:10.1088/0963-0252/14/4/011; BOLSIG+ documentation 07/2024, growth and ionization energy-sharing options: https://www.bolsig.laplace.univ-tlse.fr/wp-content/uploads/2024/07/bolsigdoc0724.pdf .

## M6b1: bounded temporal-growth generalized eigenproblem (experimental)

Unlike M6a, the independent PhysicsBoltzmannTemporalGrowth C++ module changes the EEPF self-consistently for **elastic-only** DC momentum/energy transport and ionization/attachment (no excitation or superelastic channels). It solves:

    (T - Q) f0 = -lambda M f0
    sum_i M_i f0_i = 1

with elastic two-term Scharfetter–Gummel flux matrix T, M6a ionization/attachment gain/loss matrix Q and cell mass M_i = integral sqrt(epsilon) d(epsilon). The growth eigenvalue lambda has reduced units m^3/s (physical temporal electron density growth per time = N * lambda). The ionization energy sharing remains the explicit equal sharing option.

A bounded dense shifted-inverse iteration first factors (T-Q+s M) using partial-pivoted LU and then applies the inverse repeatedly. The initial shift s exceeds an a priori maximum ionization source per mass; subsequent shifts are reduced toward the current growth estimate only after a candidate shifted solve is checked for a positive eigenvector. Each epoch recomputes the original generalized-eigen residual. Iterations normalize f0 and reject non-convergence rather than silently accepting an approximate eigenpair. After solving, the code independently recomputes the actual growth from reaction rate moments and validates the *original generalized eigen-equation residual*, including the mass term; a normalized distribution without a correct eigen residual does not count as success. Numerically positive electron growth, negative attachment growth, mixed signed growth and the weak-growth elastic-only limit are acceptance controls.

**Severe limitations:** maximum 128 cells, O(N^3) dense factorization and O(N^2) inverse iterations; no extrapolation, sparse growth eigensolver, excitation/superelastic coupling, e-e collisions, field frequency, diffusion-gradient growth, or real Ar/O2 collision set. This implementation is not the production BOLSIG+ temporal growth mode and does NOT supersede the M6a explicit frozen-growth diagnostic. No PhysicsApp coefficient material is changed. This path needs independent boundary/energy-ceiling sensitivity and pinned BOLSIG+ reference-case parity.

The developer-only candidate exporter accepts --solve-elastic-temporal-growth on collision files that have **no excitation or superelastic processes** and at most 128 cells. It labels output elastic_ionization_attachment_temporal_growth_eigen_dense and includes the generalized eigen-residual and inverse-iteration count. A frozen-growth diagnostic remains a separate explicitly requested output and cannot be used simultaneously with this eigensolver mode.
