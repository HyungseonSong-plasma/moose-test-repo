# Boltzmann CI EEPF artifact: native C++ development controls (S5)

**Scientific acceptance: HOLD_REAL_COLLISION_PROCESS_EQUIVALENCE.**

## Actual CI execution

Repository CI workflow has an independent parallel job named
"Native Boltzmann EEPF development controls" that compiles
PhysicsBoltzmannElasticSolver.C into a native executable and runs it
for six explicit, matched-metadata representative BOLSIG+ 07/2024
cases. Actual C++ output is preserved by actions/upload-artifact@v4
under the name boltzmann-native-eepf-synthetic-controls.

First verified execution: GitHub Actions run 40680402838, commit
d5ff81b0b9b2f634ed7550331d073706aaa59fe3.
Job conclusion: SUCCESS.
Artifact ID: 12812582216.

The EEPF values come from executing the repository's C++ solver, **not**
from invented plotted curves or Python emulation of the Boltzmann
equation. The new runner is
physics_app/ci/boltzmann_ci_eepf_controls.C,
with compiler/validation orchestrated by
physics_app/ci/export_boltzmann_ci_eepf.py.

All collision cross sections in these experiments are *invented*
elastic constants equal to 5.0e-20 m2, with approximate target mass
ratios. These are not the native source PHELPS/SIGLO collision
cross sections. The C++ CI model omits all of the native EXCITATION,
IONIZATION, ATTACHMENT and EFFECTIVE momentum scattering. It cannot
represent RF nonzero angular frequency for Example 2 cases R2–R10.
A diagnostic overlay is scientifically legitimate ONLY when
both curves are explicitly distinguished by physics model and
marked *not parity*. No meaningful relative-error PASS threshold
may be applied across these mismatched process inventories.

## Actual selected native CI output compared against user references

Case                       BOLSIG mean eV    C++ synthetic mean eV
example1_R21                  4.96374           7.669102863508882
example2_R1_DC                6.94903          27.433428675214910
example3_R31                  5.37619          10.549126648407675
example3_R33                  5.01202           9.014187981220920
example3_R35                  5.97496           7.365158210811475
example4_R1                   1.35694           8.636201906025788

The examples use exactly the printed E/N, gas fractions, temperature
and BOLSIG+ auto-selected maximum energy from the relevant native
runs, but intentionally use different collision process physics.
Example 2 only R1 uses DC; other Example 2 RF cases are not claimed.
The CI exporter checks finite nonnegative EEPFs, finite mean energy,
energy cell-center mapping, 1e-10 normalized EEPF mass tolerance,
positive valid gas fractions, and no missing run output.

## S7: EFFECTIVE reconstruction and independent native N2-cooling discriminator (2026-10-28)

The C++ BOLSIG-format steady elastic+excitation projector now accepts an
EFFECTIVE (or MOMENTUM) record *only for its supported excitation-only process
inventory*. It reconstructs the elastic energy-loss contribution as
sigma_elastic = sigma_effective - sum(sigma_excitation), using a union of
source energy knots and threshold positions. The existing two-term transport
operator adds excitation momentum only once. It rejects a negative elastic
remainder and duplicate ELASTIC/EFFECTIVE momentum suppliers for a target.
Ionization, attachment and rotation in the same steady input remain
unsupported: a complete real BOLSIG+ process inventory must NOT be projected
into this subset by dropping those channels. Temporal-growth and full
first-harmonic momentum correction are not solved by this change.

Independent synthetically constructed equivalent ELASTIC versus EFFECTIVE
inputs, rates and conservation regressions are encoded in
`tests/boltzmann/cross_section_import_test.C`; these are P0/P1 tests, not
an experimental LXCat/BOLSIG+ cross-section match.

[Repository CI run 40683761894](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40683761894)
at development head `da04277170db968204b6d708fcbb2b5936c5cf99`
completed its dedicated **Native Boltzmann EEPF development controls** job
successfully. Its [artifact 12813253936](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40683761894/artifacts/12813253936)
contains eleven real, compiled-C++ EEPFs, including two entirely
first-party *invented* N2 vibrational excitation controls. Exact same
synthetic constant elastic collision physics, E/N = 10 Td and mixture
Ar/He/N2/O2 = 0.70/0.20/0.08/0.02:

| Emax (eV), cells | Elastic only mean (eV) | Elastic + two synthetic N2 excitations mean (eV) |
| --- | ---: | ---: |
| 15.8367, 200 | 8.6362019 | 0.5383772 |
| 31.6734, 400 | 12.978518 | 0.5383772 |

The added excitation channels use **invented**, not BOLSIG+/PHELPS/SIGLO,
cross sections: 0.3 eV threshold and 5e-20 m2 above threshold; 1.0 eV
threshold and 4e-20 m2 above threshold. They are a mechanism discriminator
demonstrating conservative low-energy cooling and cutoff stability for
this synthetic subset, **not** a fitted or physically accepted N2 operator.
Their 0.5384 eV mean *undershoots* the actual BOLSIG+ Example4 mean
1.35694 eV; therefore this is emphatically **not** improved quantitative
BOLSIG+ parity. Both models' absolute EEPFs remain non-equivalent to the
47-process real source, and no physical-rate/transport PASS is allowed.
The dedicated job PASS does not promote overall Repository CI or P2/P3.

For genuine BOLSIG+ parity, retain source-provenance-controlled **complete**
47-process data including effective momentum semantics, excitation,
ionization, attachment, electron temporal growth and inverse populations
where applicable, plus independent raw reference EEPF export. Then require
cutoff/cell-size convergence and independent EEPF, rates and four transport
moments comparisons. The imported third-party source must not be redistributed
without authorization. Keep PR #408 in DRAFT / SCIENCE HOLD.


## S8: independent energy-grid refinement and external source/native process ledger

The S7 energy-domain 1x/2x/4x/8x ablation held the energy-cell width
constant while extending the domain. S8 independently holds Emax fixed at
15.8367 eV and doubles the number of cells (200 -> 400) for the SAME
invented N2 two-excitation operator. Its normalized EEPF comparison uses
the exact cell-number mass integral `(2/3)*(upper**1.5-lower**1.5)`,
not a simple arithmetic average of cell-center values. This checks
discretization separately from energy-domain truncation.

Native C++ output observed in the dedicated CI job on
[run 40685556551](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40685556551):

- 200 cells at 15.8367 eV: 0.5383772 eV mean;
- 400 cells at 15.8367 eV: 0.53819462 eV mean;
- relative mean change: 0.000339234455 (0.0339234%);
- number-mass-weighted EEPF L1 difference: 0.0485320284;
- predeclared synthetic-grid thresholds: mean <0.02 and L1 <0.05;
- result `SYNTHETIC_N2_GRID_REFINEMENT_PASS`.

This remains entirely synthetic development verification. Its grid-PASS
does NOT mean an equivalent physical BOLSIG+ collision operator has
been implemented; changing synthetic model/cross sections changes the EEPF.

`physics_app/ci/boltzmann_collision_coverage_audit.py` now recognizes
EFFECTIVE+EXCITATION as a bounded steady-state supported form instead of
categorically rejecting EFFECTIVE; it still reports
`EFFECTIVE_GROWTH_COUPLING_UNSUPPORTED` for EFFECTIVE with
ionization/attachment, and explicitly flags duplicate momentum providers,
missing momentum records, out-of-domain inelastic thresholds, unsupported
rotation and one-point/power-law source types. Structural support is
never a physical validation claim.

`bolsig_native_scalar_audit.py --native-output <native-output> --cross-sections <user-local-collision-file>`
now cross-checks native run-by-run process census with independently parsed
source gas/kind counts, records both raw-byte SHA-256 values, and reports
missing/excess counts. Mismatches are a fail-closed exit status 2; count
equality means `PROCESS_CENSUS_MATCH_PHYSICAL_PARITY_NOT_ESTABLISHED`.
The check cannot establish individual threshold/table equivalence,
density-normalized three-body attachment, Coulomb/e-e effects, superelastic
populations, or full growth/transport parity.

These are practical controls that can be applied once the user-local,
rights-controlled BOLSIG+/LXCat original collision file and the native
output are accessible in the SAME environment. No third-party table bytes
have been committed to the repository. Keep PR #408 Draft and preserve
production Oxygen ICP coefficients.


## S9: uploaded genuine collision source and native 07/2024 output, first real-input reconciliation

The user supplied BOTH original local files for analysis, and neither raw
file is redistributed or committed:

- `SigloDataBase-LXCat-04Jun2013.txt`: 166491 bytes; SHA256
  `b8b1ff807d0586795dcabf4511a2a44b8b04828626b45e0fd95a319817c01063`.
- `example4-eepf(1).dat`: 20252 bytes; SHA256
  `aa6c7c0ce00c61095934defa70f40e415474562b5e3e53374766c1ab7d6912d3`.
- Native header confirms BOLSIG+ 07/2024, 10 Td, 300 K,
  0.70 Ar/0.20 He/0.08 N2/0.02 O2, temporal-growth model,
  200 requested automatic grid points, **actual Emax 15.8367 eV**,
  mean energy 1.35694 eV.
- The native `Energy (eV) EEDF (eV-3/2) Anisotropy` section contains
  195 printed positive-energy f0/EEPF nodes from 0.0002477092 to
  14.97833 eV. Printed-interval trapezoid normalization is 0.9998661043.
  The requested manual max 200 eV in CONDITIONS is NOT the actual
  automatic solver max: use the latter for any numeric comparison.

**New discrepancy identified using original raw bytes:** the source contains
48 relevant process blocks (Ar 3, He 3, N2 25, O2 17), but the native
rate ledger has **47** (Ar 3, He 3, N2 25, O2 16). The source contains
two O2 ATTACHMENT blocks: line 5235 (a density-normalized three-body
attachment, target `O2`) and line 5279 (dissociative two-body
`O2 -> O^-+O`). The native output has only `C32 O2 Attachment`,
`3.80265e-37 m3/s`.

An independently integrated source-to-native rate comparison, using
`k = sqrt(2e/m_e) * integral(epsilon * sigma(epsilon) * f0(epsilon) d epsilon)`,
piecewise-linear source/printed f0 and cubic-exact per-interval Simpson
quadrature, evaluated both candidate O2 attachment blocks WITHOUT
silently applying unverified three-body density conversion:

- line 5235 raw three-body table: 3.8025568983e-37 m3/s, matching C32
  within ~0.00245%;
- line 5279 two-body: 2.5899679684e-18 m3/s, not remotely compatible
  with the native C32 rate.

Thus numerical rate evidence strongly identifies the **second O2 two-body
attachment block (line 5279) as omitted from the native 47-process run**.
The first, three-body-labelled record was apparently used as **unscaled
tabulated input** for C32. The LXCat source header, however, explicitly
says its three-body attachment tables require multiplication by neutral
gas density in cm^-3 before use. The reference number density is
1e18 m^-3 = 1e12 cm^-3; whether/how BOLSIG+ intends that correction
requires an explicit physical convention check. **Do not claim full
collision-model parity or silently add/remove/scale either channel.**

Across the 47 aligned processes, 43 positive native rates were
independently reconstructed over the printed EEPF interval;
the relative-error median was ~0.1938%, the maximum ~1.19%.
This is strong evidence that original cross-section records and printed
EEPF are coherently paired with the native process ledger, NOT evidence
that the independent C++ solver produces the same EEPF. Four zero/native
out-of-range cases are not falsely scored as positive-rate agreement.

Mandatory follow-ups: preserve both hashes in local case metadata;
make BOLSIG's exact 47/48 process selection and three-body convention
an explicit reproducible input, implement the full EFFECTIVE/inelastic/
ionization/attachment momentum and temporal-growth operator without
silent dropped reactions, lift the dense 128-cell limit or validate a
separate high-resolution solver, and independently compare full EEPF and
transport. PR remains science HOLD/DRAFT; no third-party source raw
tables or native original output are committed.


### S9 reproducible source/native evidence (user-local; no raw uploads to GitHub)

Run the now-implemented `physics_app/ci/bolsig_native_full_process_audit.py`
against an original source file and its run-by-run numerical output:

```sh
python3 physics_app/ci/bolsig_native_full_process_audit.py \
  --cross-sections "/private/local/SigloDataBase-LXCat-04Jun2013.txt" \
  --native-output "/private/local/example4-eepf.dat"
```

For the two user-supplied files identified above, the deterministic
JSON preflight has `status=HOLD_NATIVE_OMITTED_PROCESS` (exit code 2),
not a fake physics PASS. It identifies the extra line-5279 O2
dissociative attachment after independent source/native rate integration.
The rate diagnostic compares the observed native output against the
raw cross-section INPUT; it is not a new C++ kinetic prediction.

The check is regression-tested with **synthetic, author-generated**
ELASTIC+two-ATTACHMENT fixtures, native process omission, extra
native process and original-source SHA mutation tests in
`tests/test_bolsig_native_full_process_audit.py`. Reference bytes,
collision tables and real EEPF rows are intentionally absent from Git.


## S10/M6b3: complete first-harmonic collision-scattering separation

The independent developer M6 importer now admits EFFECTIVE with explicitly
enumerated excitation, ionization and attachment instead of categorically
rejecting this combination. The projection distinguishes *elastic recoil*
(energy relaxation) and *total first-harmonic momentum scattering* (electric
field heating). For EFFECTIVE, elastic recoil is constructed as the
nonnegative remainder after subtracting **all** included inelastic channels
at the piecewise-linear knot union; the field-scattering table is the
original effective value. For ELASTIC, elastic recoil is unchanged and the
field-scattering table adds each included inelastic channel once. M5's
first-harmonic excitation term is skipped when a complete field-scattering
table is already supplied, preventing double-counting. The temporal-growth
SG flux also uses the total field-scattering data while retaining elastic
recoil. Existing five-argument ElasticTarget construction is preserved.

This is a bounded *operator integration* improvement, not real BOLSIG+
Example4 EEPF parity. Native C++ synthetic ELASTIC/EFFECTIVE+excitation+
ionization+attachment equivalent records test both recoil and momentum
equality as well as conservative EEPF behavior. The developer candidate
CLI additionally tests an independent synthetic full-set effective/elastic
frozen-growth EEPF and process-rate comparison. Invalid negative effective
residuals remain rejected and the MOOSE production closure is unchanged.

`physics_app/ci/bolsig_local_matched_source.py` prepares a **USER-LOCAL
ONLY** derived 47-process collision file from the independently audited
48-process original source: it requires both original hashes, the
explicit native-identified omitted source line 5279, and an explicit
`as-tabulated-unscaled` three-body convention. It never silently drops
the omitted process: it records the exclusion and source identity.
This native-output convention is not a validated physical three-body
normalization. Generated third-party table bytes MUST remain local.

### Additional actual source blockers found from raw process metadata

For the 47 explicitly selected source records at native Emax=15.8367 eV:

- **37/47** tabulated cross sections start above 0 eV.
- **12/47** terminate below the solver's actual energy ceiling;
  N2 contributes 9 such short-range records and O2 contributes 3.
- Native BOLSIG+ input sets `READCOLLISIONS Extrapolate=1`.
  The 07/2024 BOLSIG+ documentation describes piecewise-linear
  interpolation and controlled high-energy continuation. Exact
  prethreshold zero behavior and high-end continuation must be
  implemented/tested against the native output before running all 47.
  The current strict C++ projector correctly continues to HOLD rather
  than invent cross sections outside the tabulated range.
- Some ionization/excitation thresholds are above the selected Emax and
  require process-preserving zero-rate handling, not deletion.
- Full 200-cell temporal-growth still needs numerical qualification;
  current dense implementation caps at 128 cells. Physical
  three-body attachment density normalization remains unresolved.

The source preflight machine report is generated locally and only
contains source hashes, source line/target identifiers and counts, not
third-party cross-section rows. **Scientific gate remains HOLD.**

Source: BOLSIG+ 07/2024 manual,
https://www.bolsig.laplace.univ-tlse.fr/wp-content/uploads/2024/07/bolsigdoc0724.pdf


## S11: BOLSIG+ 07/2024 source-boundary normalization, explicit opt-in

Independent documentation basis: Hagelaar, *Brief documentation of
BOLSIG+ version 07/2024*, 18 July 2024, pp. 9–10,
https://www.bolsig.laplace.univ-tlse.fr/wp-content/uploads/2024/07/bolsigdoc0724.pdf.
This manual specifies (1) linear interpolation between source points;
(2) constant cross section below the first point; (3) at `Extrapolate=1`,
extra high-energy source points at energies multiplied by 1.5, following
`ln(E)/E`, with LINEAR interpolation between the newly generated points;
and (4) threshold-zero insertion and removal of nonzero entries below
excitation/ionization threshold.

The new standalone `normalizeBolsig2024CollisionFile` is **opt-in** and
does not mutate raw collision records or their ordered identities. It
prepares coverage through the first high-end 1.5x knot strictly ABOVE
the selected energy ceiling (this preserves last-segment interpolation),
and clamps lower-energy scattering. For excitation/ionization it inserts
zero at the threshold and leaves out-of-range channels in the source
ledger, with a separate zero-rate inactive-channel inventory. Because
the `ln(E)/E` continuation cannot be safely anchored with a source
last energy <=1 eV, that case explicitly rejects rather than assuming
an unreferenced physical law. The default unmodified strict import
remains unchanged.

The developer-only exporter accepts `--bolsig-2024-boundaries`, and
outputs explicit `source_process_count`,
`inactive_above_energy_ceiling` and `scientific_acceptance=HOLD...`.
Only opt-in growth import can treat an excitation/ionization whose
threshold exceeds Emax as an audited zero-rate process. It never
drops the source record without a ledger, silently repairs omitted
source processes, or alters O2 three-body attachment densities.

Local actual 47-process preflight (source identity SHA
`daf82ef4927fabec32bed5b5b19214b432f580931518d21e1aa6d3a438751bac`):
- At Emax=15.8367 eV, physical inactive He excitation threshold 19.8 eV
  and He ionization threshold 24.58 eV are explicitly retained.
- Independent first-harmonic EFFECTIVE-minus-all-inelastic residual
  scan on the actual ordered 47-process source knot union found
  **no negative elastic residual** for Ar, He or O2. This is necessary
  input compatibility evidence, NOT evidence that the C++ solver
  generated the actual BOLSIG+ EEPF.
- Raw original source SHA `b8b1ff807d0586795dcabf4511a2a44b8b04828626b45e0fd95a319817c01063`,
  native reference SHA `aa6c7c0ce00c61095934defa70f40e415474562b5e3e53374766c1ab7d6912d3`.
- BOLSIG's automatic energy grid is not thereby reproduced by
  a uniform-cell C++ solver. Actual 47-process EEPF, scalar transport,
  e-e, superelastic and temporal-growth parity still require direct
  independent 200-cell native C++ comparison and source-unit review.

S11 synthetic regression includes native C++ threshold, extrapolation
knot, no-opt-in, inactive-channel and candidate CLI zero-rate/unchanged
EEPF controls. No third-party cross-section rows are committed.
