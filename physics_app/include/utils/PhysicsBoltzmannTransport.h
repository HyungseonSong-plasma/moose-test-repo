#pragma once

#include "PhysicsBoltzmannElasticSolver.h"

namespace PhysicsBoltzmann
{
// M7a: electron particle/energy transport moments for a given normalized
// EEPF and ELASTIC-ONLY momentum-transfer cross sections. No non-Maxwellian
// transport is forced into a Maxwellian 5/3 or Einstein closure.
struct ElasticTransportMoments
{
  double reduced_mobility_N_per_m_V_s = 0.0; // mu_e * N; m^-1 V^-1 s^-1
  double reduced_diffusion_N_per_m_s = 0.0; // D_e * N; m^-1 s^-1
  double reduced_energy_mobility_N_per_m_V_s = 0.0; // mu_epsilon * N
  double reduced_energy_diffusion_N_per_m_s = 0.0; // D_epsilon * N
  double high_energy_tail_ratio = 0.0;
};

// Published Hagelaar/Pitchford 2005, equations 55,56,61,62. This standalone
// M7a reference is intentionally restricted to the ELASTIC-only two-term
// momentum denominator; excitation/superelastic and growth-dependent effective
// scattering must be included/validated before production Physics coupling.
// f0 is piecewise constant on energy cells, derivative is represented by
// its interface jumps plus an explicitly monitored upper-energy boundary.
ElasticTransportMoments evaluateElasticTransportMoments(
    const ElasticInput & input,
    const ElasticResult & distribution);
}
