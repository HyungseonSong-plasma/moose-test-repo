# Oxygen electron collision set — approximation policy (2026-10-30)

**Scope remains frozen at 33** (25 Chemistry, 7 Boltzmann kinetic support, 1 atomic-O elastic). This decision implements the user's **reduced-complexity model**, NOT a physics/chemistry validation waiver.

## Two detailed-balance channels (source-informed)

| ID | Parent | Formula | Status |
|---|---|---|---|
| EI-2067 | EI-407, `e+O2(X)->e+O2(a1Delta_g)` | `(3/2)*(E+0.977)/E * sigma407(E+0.977)` | DERIVED_REVIEW |
| EI-943 | EI-935, `e+O(3P)->e+O(1D)` | `(9/5)*(E+1.967)/E * sigma935(E+1.967)` | DERIVED_REVIEW |

The reverse zero-energy value is calculated from a **linear near-threshold limit** of the forward data; this numerical assumption is **not a measurement**. Parent data, degeneracy conventions, and EEDF transport are still subject to independent review. Source numeric arrays are NOT committed to this repository.

## Four candidate shifted sigma(E) curves

Given a known parent `sigma_parent(E)`, use
`sigma_child(E)=S * sigma_parent(E+E_th_parent-E_th_child)` on the parent-supported interval above the target threshold; zero below threshold, no extrapolation.

| ID | Parent | Parent -> Child threshold (eV) | S | Review status |
|---|---|---:|---:|---|
| EI-2058 | EI-401 O2(X) dissociative attachment | 4.90 -> 3.50 | Data-derived peak fit to Burrow maximum 4.6×10^-22 m²; **S=2.94871795 for current Cantera/Phelps table** | PROVISIONAL_REVIEW |
| EI-2069 | EI-412 O2(X) effective 6.0eV loss | 6.00 -> 5.02 | 1.0 screening assumption | **PROVISIONAL_PRODUCT_HOLD**: 6eV Phelps LOSS is not proven O+O dissociation |
| EI-2072 | EI-415 O2(X) molecular ionization | 12.06 -> 11.08 | 1.0 screening assumption | PROVISIONAL_REVIEW |
| EI-944 | EI-941 O(3P) atomic ionization | 13.60 -> 11.65 | 1.0 screening assumption | PROVISIONAL_REVIEW |

**Critical EI-2058 caveat:** shift **1.40 eV**, not the O2(a) internal energy 0.977 eV. This is an empirical threshold-matching operation, NOT an ab initio metastable transform. The experimental Burrow peak has ±1.3×10^-22 m² uncertainty; do not infer the entire cross-section shape is experimentally verified. [Burrow 1973](https://digitalcommons.unl.edu/physicsburrow/17/).

**Energy support:** Cantera/Phelps EI-401 and EI-407 contain a far-right artificial 10,000 eV **zero** knot. The local candidate generator removes it rather than interpolating thousands of unmeasured eV. For supplied source files, EI-2058 ends at **9.95 eV** and EI-2067 at **44.023 eV**; no silent extrapolation beyond these. That fact can materially affect high-energy EEDF completeness. Source is a manually edited derivative from LXCat/Phelps, not authenticated HPEM.

## Rate-only comparisons (not valid EEDF sigma input)

- **EI-2259:** Peverall et al. (2001), O2+(v=0), `k=2.4e-13*(300/Te_K)^0.70 m3/s`, `Te_K>200`. **The 1–7 eV ICP electron temperature interval is far above the tested near-thermal rate regime; do not silently extrapolate.** Sample values at 300–5000 K are reported as benchmarks only. [AMOLF source](https://ir.amolf.nl/pub/1211/).
- **EI-417:** Kim 2006 previously recorded reference fit `k=1.88e-16*Te_eV^1.699*exp(-16.81/Te_eV) m3/s`, screening fit for Maxwellian Te≈1–7 eV. Not O+ **partial** sigma(E).
- **EI-2058:** Kim reference rate `k=4.19e-15*Te_eV^-1.376*exp(-5.19/Te_eV) m3/s` (Maxwellian benchmark, NOT proof of agreement with the provisional shifted `sigma(E)`).
- **EI-2072:** Kim reference rate `k=2.34e-15*Te_eV^1.03*exp(-11.31/Te_eV) m3/s` (same caveat).

**Temperature conventions matter**: `Te_K=Te_eV/(8.617333262145e-5)`. Rate benchmarks are NOT valid substitutes for integration over a non-Maxwellian EEDF.

## Four explicit blocked models — never automatically synthesize

| ID | HOLD reason |
|---|---|
| EI-2068 | HPEM 3.52eV threshold vs 2O(3P) products and energy asymptote unresolved |
| EI-2073 | HPEM 13.72eV 130nm-associated effective excitation/fragment branching unresolved |
| EI-2074 | No process-validated EI-417 O+ **partial** sigma(E); whole O2 total ionization is **not** a replacement |
| EI-2738 | O- detachment amplitude and low-energy fit require original experiment data |

The existing chemistry source terms are **not changed or activated**. Only a separate `APPROX_NOT_VERIFIED` local output is allowed.

## Repository implementation and local production

- [`oxygen_approximation_policy.py`](oxygen_approximation_policy.py) contains fail-closed pure functions `detailed_balance`, `threshold_shift`, `derive`, `maxwellian_rate_m3_s`, and a `derive_local_csv` entry point, without original Phelps or Zenodo numeric arrays.
- [`test_oxygen_approximation_policy.py`](../../tests/characterization/test_oxygen_approximation_policy.py) guards threshold, degeneracy, source SHA256 tracking and excludes HOLD/reaction scope drift using **synthetic** data.
- In the current conversation, six CSVs were generated **locally** from the two user-provided source files. The local archive also contains provenance manifest, rate benchmark and review status table. These numeric outputs remain **outside public GitHub** pending licensing checks.

### What remains before solver integration

1. Validate inferred branching for 2058/2069/2072/944 against reaction-specific experiments or trusted papers.
2. Check EEDF E/N sensitivity and O(3P) density responses under *on/off* toggles, including missing source energy tails.
3. Verify detailed-balance state weights and energy-closure to chemistry before turning either reverse channel on.
4. Confirm that rate-only comparisons and sigma(E) candidate processes are not double-counted in the source term.

**No complete EEDF/Boltzmann run, EEDF rate lookup or calibrated physical accuracy is claimed by this implementation.**
