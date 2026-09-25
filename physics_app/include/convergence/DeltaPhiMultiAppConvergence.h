#pragma once

#include "DefaultMultiAppFixedPointConvergence.h"

/**
 * MultiApp fixed-point convergence that requires BOTH:
 *   1. the standard MOOSE fixed-point residual criterion; and
 *   2. max |phi^(k)-phi^(k-1)| <= delta_phi_abs_tol.
 *
 * The delta-phi quantity is supplied by a postprocessor executed on
 * MULTIAPP_FIXED_POINT_CONVERGENCE.
 */
class DeltaPhiMultiAppConvergence : public DefaultMultiAppFixedPointConvergence
{
public:
  static InputParameters validParams();
  DeltaPhiMultiAppConvergence(const InputParameters & parameters);

  MooseConvergenceStatus checkConvergence(unsigned int n_iter) override;

protected:
  const PostprocessorValue & _delta_phi;
  const Real _delta_phi_abs_tol;
};
