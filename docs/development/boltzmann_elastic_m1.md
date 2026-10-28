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
