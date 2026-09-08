#pragma once

#include "FVElementalKernel.h"

/**
 * Applies a signed species mass-source functor to a finite-volume equation.
 *
 * The supplied source is interpreted as the right-hand-side source S in
 *
 *   d(rho w_k)/dt + div(...) = S
 *
 * so the residual contribution is -S.
 */
class PhysicsFVSpeciesReactionSource : public FVElementalKernel
{
public:
  static InputParameters validParams();
  PhysicsFVSpeciesReactionSource(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _source;
};
