#pragma once

#include "PhysicsBoltzmannGrowth.h"

#include <cstddef>

namespace PhysicsBoltzmann
{
// M6b1/M6b2 — self-consistent DC energy-space transport coupled to
// binary ionization/attachment. Optional excitation/superelastic channels use
// the exact same SG+nonlocal conservative assembly as M5; dense shifted inverse
// iteration remains a bounded reference. No real BOLSIG+ parity.
// The normalized stationary temporal-growth generalized eigenproblem is
//
//   (T - Q) f = -lambda M f
//   sum_i M_i f_i = 1
//
// where T is conservative elastic Scharfetter-Gummel energy flux, Q is the
// particle-changing collision operator, and M is the EEPF mass metric.
struct TemporalGrowthResult
{
  ElasticResult distribution;
  GrowthDiagnostics growth;
  double reduced_growth_eigenvalue_m3_per_s = 0.0;
  double maximum_normalized_eigen_residual = 0.0;
  std::size_t inverse_iterations = 0;
};

// Reference-grade O(N^3) LU, O(N^2) iteration, N <= 128, no hidden sparse
// or Maxwellian fallback. This is intentionally not yet production-scalable.
TemporalGrowthResult solveElasticTemporalGrowth(
    const ElasticInput & input,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments,
    const std::vector<ExcitationChannel> & excitations = {});
}
