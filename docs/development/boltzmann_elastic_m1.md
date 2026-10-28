# Electron Boltzmann solver — M1 elastic DC energy-space kernel

**Status:** DEVELOPMENT, not a qualified BOLSIG+ equivalent or a promoted Physics runtime coefficient provider.

Reference: Hagelaar & Pitchford (2005), Plasma Sources Science and Technology 14, 722–733, DOI:10.1088/0963-0252/14/4/011, equations (39)–(43). Independent implementation from published mathematics; no BOLSIG+ proprietary source incorporated.

## Scope

The standalone C++ function PhysicsBoltzmann::solveElasticSteadyState handles a spatially homogeneous, steady-state, two-term **elastic-only** electron-neutral EEPF under a uniform DC E/N, finite gas temperature, and a prescribed elastic momentum-transfer cross-section table for each mixture constituent. It has no MOOSE includes, no input syntax change and no connection to the production plasma residual or accepted chemistry. It is an M1 **subset** only. All target mass ratios, cross-section provenance and number fractions are explicit inputs; there is no invented Ar/O2 physical dataset.

Energy grids are uniform with centers and interfaces in eV. Cross-section interpolation is piecewise linear, with explicit failure on insufficient coverage, invalid signs, nonmonotone abscissas or zero elastic collision frequency. E/N is in Td (1 Td = 1e-21 V m^2). The returned isotropic EEPF f0 is normalized as integral sqrt(energy_eV) f0 denergy_eV = 1 and has units eV^(-3/2). This is not the probability density sqrt(energy) f0.

At a positive interior interface energy epsilon, the published elastic operator is:

    sigma_eps = sum_targets [2 (m_e/M_k) x_k sigma_m,k]
    sigma_m   = sum_targets [x_k sigma_m,k]
    W = -gamma epsilon^2 sigma_eps
    D = (gamma/3) (E/N)^2 epsilon/sigma_m
        + gamma (k_B*T_g/e) epsilon^2 sigma_eps
    gamma = sqrt(2 e / m_e)
    J = W f0 - D d(f0)/d(epsilon)

The exponential-fitting flux J_face = (D/h)[B(-P)f_left - B(P)f_right], P=W*h/D and B(x)=x/expm1(x), gives interface ratio f_right/f_left=exp(P) for zero flux. This recurrence solves the discrete conservative elastic nullspace, not a general nonlocal inelastic linear system. Log-EEPF recurrence prevents overflow; normalization uses exact cell integrals for piecewise constant f0.

## Current verification

Run standalone without MOOSE (or simply run pytest -q tests/test_boltzmann_elastic_core.py):

    g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
      -Iphysics_app/include/utils \
      physics_app/src/utils/PhysicsBoltzmannElasticSolver.C \
      tests/boltzmann/elastic_core_test.C -o /tmp/physics_boltzmann_elastic_test
    /tmp/physics_boltzmann_elastic_test

Expected standalone P0/P1: finite nonnegative EEPF, normalization, conservative flux residual, zero-field Maxwellian mean energy 3/2 k_B T_g, observed grid refinement, positive field-heating response and negative input tests. These **do not establish** real production physics-opt compatibility, Ar/O2 reference parity, inelastic collision transfer, electron energy closure or scientific validation.

## Next real gate

Implement and independently validate: nonlocal excitation/superelastic operators and energy transfer, ionization/attachment/growth conventions, conservation, full EEDF moments and transport coefficients, LXCat cross-section import/provenance, E/N and mean-energy inversion, adaptive energy bounds and BOLSIG+ reference comparisons at pinned physical data. MOOSE wrapper should follow a complete scientifically accepted subset. Do not overwrite any existing production oxygen ICP coefficient table using the elastic-only EEPF.


## M2 development extension — excitation-only source

The existing M1 C++ file also provides `solveExcitationSteadyState`, a bounded, direct, pivoted reference implementation of the nonlocal excitation kernel. Input channels specify a named target, positive threshold u [eV], and energy/cross-section data. Source/sink follow Hagelaar–Pitchford (2005), eq. (28): the donor at epsilon is removed with weight gamma*x*epsilon*sigma(epsilon)*f0(epsilon), then reintroduced at epsilon-u (not in the donor's original cell). Each donor-to-receiver overlap integrates epsilon*sigma against the piecewise-linear cross section, conserving number exactly for the discretized transfer. The gain operator is nonlocal; it cannot be replaced by an extra local energy-loss constant without changing EEPF shape.

Steady algebra: [div(Scharfetter–Gummel elastic flux) - (excitation_gain - excitation_loss)] f0 = 0. One redundant conservation row is replaced by integral sqrt(epsilon) f0 d epsilon = 1. The original, full row balance is checked afterward. This is a dense partial-pivot reference solve limited to <=512 energy cells, not a scalable production matrix solver. The solver reports per-target reaction rate coefficients [m^3/s], excitation energy-loss coefficients [eV m^3/s] and the normalized equation/number balance residuals. Elastic flux itself is **not zero** in the presence of excitation: the inherited elastic-only zero-flux diagnostic is NaN; the inelastic acceptance metric is the full conservative equation residual.

New native tests cover nontrivial energy cooling, energy-grid convergence, nonnegative normalized EEPF, exact donor/recipient number accounting, independent constant-cross-section rate integration, zero-amplitude backward parity, invalid inputs, and the 512-cell ceiling. These tests use deliberately synthetic constant cross sections. Their passing does not qualify an Ar/O2 reaction mechanism, channel provenance, numerical energy closure in a full kinetic plasma chemistry model, higher-energy inelastic dynamics, or production physics-opt integration. No MOOSE input or existing production coefficient/material/chemistry path is changed.

**Remaining gates:** independent BOLSIG+ dataset parity at exact source revisions, excitation/superelastic detailed balance with explicitly modeled excited target populations, ionization/attachment and growth conventions, energy-moment transport, physical mesh/energy-upper-bound sensitivity and sparse production-viable operator. M2 is development-only pending independent numerical and Physics runtime validation.

**Momentum-scattering convention:** `ElasticTarget.momentum_transfer_m2` must contain **elastic-only** momentum-transfer cross sections, not an `EFFECTIVE` set that already includes excitation. The two-term field-heating denominator adds the active excitation total cross sections (assuming isotropic excitation scattering) to the elastic momentum-transfer sum. Supplying an effective elastic total would double count excitation scattering; input dataset provenance/type remains a mandatory preflight gate.
