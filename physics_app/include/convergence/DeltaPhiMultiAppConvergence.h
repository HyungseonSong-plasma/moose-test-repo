#pragma once

#include "DefaultMultiAppFixedPointConvergence.h"

/**
 * Gummel fixed-point convergence based on the electrostatic coupling variable:
 *
 *   max |phi^(k) - phi^(k-1)| <= delta_phi_abs_tol.
 *
 * The default MOOSE residual-norm check is disabled because its raw L2 norm mixes
 * equation units and therefore changes when a physically equivalent variable is
 * rescaled (for example, normalized electron energy -> eV/m^3).
 *
 * Legacy AND behavior can be restored explicitly by setting
 * disable_fixed_point_residual_norm_check = false.
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
