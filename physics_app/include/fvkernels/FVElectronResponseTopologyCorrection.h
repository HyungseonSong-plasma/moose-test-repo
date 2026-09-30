#pragma once

#include "FVElementalKernel.h"

#include <vector>

/**
 * Topology-aware electron-response correction for multidimensional FV Poisson solves.
 *
 * Two row-sum-preserving support modes are available:
 *
 * graph shell:
 *   R_corr,i = beta_i * strength
 *              * sum_d a_d (delta_phi_i - mean_{j in S_d(i)} delta_phi_j)
 *
 * directional band:
 *   the same shell weights are applied to at most four directed paths
 *   (+radial, -radial, +axial, -axial), preserving the 1D +/- bandwidth
 *   character without averaging over every cell in a 2D graph-radius shell.
 *
 * Every shell term vanishes for a uniform potential shift, and the complete
 * correction vanishes exactly at the Gummel fixed point phi == phi_anchor.
 */
class FVElectronResponseTopologyCorrection : public FVElementalKernel
{
public:
  static InputParameters validParams();
  FVElectronResponseTopologyCorrection(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

private:
  const Elem * directionalNeighbor(const Elem * elem, unsigned int component, int sign) const;

  const Moose::Functor<ADReal> & _anchor;
  const Moose::Functor<ADReal> & _beta;
  const Real _strength;
  const unsigned int _graph_radius;
  std::vector<Real> _shell_weights;
  const bool _directional_band;
  const unsigned int _radial_component;
  const unsigned int _axial_component;
  const Real _directional_cosine_min;
};
