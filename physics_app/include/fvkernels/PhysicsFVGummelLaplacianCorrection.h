#pragma once

#include "FVFluxKernel.h"

/**
 * Row-sum-preserving Gummel Jacobian correction for the Poisson block.
 *
 * On each internal FV face, this kernel adds a diffusive flux proportional to
 *
 *   -kappa * grad(phi - phi_anchor)
 *
 * where phi_anchor is the entering outer Gummel iterate.  Therefore the
 * correction vanishes exactly at a converged fixed point and for a uniform
 * potential shift.  The discrete contribution has the graph-Laplacian sign
 * pattern (+ diagonal, - nearest-neighbor off diagonal).
 */
class PhysicsFVGummelLaplacianCorrection : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVGummelLaplacianCorrection(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _anchor;
  const Moose::Functor<ADReal> & _coeff;
};
