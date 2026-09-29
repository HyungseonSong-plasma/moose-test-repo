#pragma once

#include "FVElementalKernel.h"

/**
 * Topology-aware electron-response correction for multidimensional FV Poisson solves.
 *
 * Applies a row-sum-preserving one-ring graph stencil to
 * delta_phi = phi - phi_anchor:
 *
 *   R_corr,i = beta_i * strength * (delta_phi_i - mean_{j in N(i)} delta_phi_j)
 *
 * where N(i) contains the face-neighbor elements of cell i.  The correction
 * therefore follows mesh connectivity rather than global element numbering,
 * vanishes for a uniform potential shift, and vanishes at the Gummel fixed point.
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
};
