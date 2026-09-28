#pragma once

#include "DefaultMultiAppFixedPointConvergence.h"

#include <memory>
#include <string>

class MultiApp;

/**
 * MultiApp fixed-point convergence that requires BOTH:
 *   1. the standard MOOSE fixed-point residual criterion; and
 *   2. max |phi^(k)-phi^(k-1)| <= delta_phi_abs_tol.
 *
 * The delta-phi quantity may be supplied either by a postprocessor in the
 * current application (legacy/current-app electron mode) or directly by a
 * postprocessor in a named sibling MultiApp (two-subapp mode).
 */
class DeltaPhiMultiAppConvergence : public DefaultMultiAppFixedPointConvergence
{
public:
  static InputParameters validParams();
  DeltaPhiMultiAppConvergence(const InputParameters & parameters);

  MooseConvergenceStatus checkConvergence(unsigned int n_iter) override;

protected:
  Real deltaPhi() const;

  const PostprocessorValue * const _delta_phi;
  const std::shared_ptr<MultiApp> _delta_phi_multiapp;
  const std::string _delta_phi_subapp_pp;
  const Real _delta_phi_abs_tol;
};
