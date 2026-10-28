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
