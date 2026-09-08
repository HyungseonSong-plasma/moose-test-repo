#pragma once

#include "FVTimeKernel.h"

/**
 * Discretely conservative finite-volume time derivative for a species mass fraction.
 *
 * Backward-Euler / implicit-Euler contract:
 *
 *   d(rho w_k)/dt
 *     ~= [rho^n w_k^n - rho^(n-1) w_k^(n-1)] / dt
 *
 * This object is intentionally separate from PhysicsFVMassFractionTimeDerivative,
 * which implements rho * d(w_k)/dt.
 *
 * Current supported temporal contract:
 *   - transient problems
 *   - backward Euler / implicit Euler
 *
 * Generalized multi-step product differentiation (for example BDF2) is outside
 * the current object contract and must not be inferred from this implementation.
 */
class PhysicsFVConservativeMassFractionTimeDerivative : public FVTimeKernel
{
public:
  static InputParameters validParams();

  PhysicsFVConservativeMassFractionTimeDerivative(const InputParameters & parameters);

protected:
  virtual ADReal computeQpResidual() override;

  /// Mixture density rho [kg/m^3]
  const Moose::Functor<ADReal> & _rho;
};
