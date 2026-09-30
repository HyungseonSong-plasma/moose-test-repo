#pragma once

#include "FVElementalKernel.h"

#include <vector>

/**
 * Topology-aware electron-response correction for multidimensional FV Poisson solves.
 *
 * Applies a row-sum-preserving graph-shell stencil to
 * delta_phi = phi - phi_anchor:
 *
 *   R_corr,i = beta_i * strength
 *              * sum_d a_d (delta_phi_i - mean_{j in S_d(i)} delta_phi_j)
 *
 * where S_d(i) is the set of elements at exact face-graph distance d and the
 * shell weights a_d are normalized to sum to one.  Every shell term is
 * individually row-sum preserving, so a uniform potential shift remains in the
 * null space.  The correction also vanishes exactly at the Gummel fixed point.
 */
class FVElectronResponseTopologyCorrection : public FVElementalKernel
{
public:
  static InputParameters validParams();
  FVElectronResponseTopologyCorrection(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

private:
  const Moose::Functor<ADReal> & _anchor;
  const Moose::Functor<ADReal> & _beta;
  const Real _strength;
  const unsigned int _graph_radius;
  std::vector<Real> _shell_weights;
};
