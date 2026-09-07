#pragma once

#include "FVTimeKernel.h"

/**
 * Density-weighted time derivative for a species mass fraction.
 *
 * Implements
 *
 *   rho * d(w_k)/dt
 *
 * for the heavy-species mass-fraction equation
 *
 *   rho * d(w_k)/dt
 *   + rho * u.grad(w_k)
 *   + div(j_k)
 *   = R_k
 *
 * Current scope:
 *   - density-weighted accumulation only
 *   - convection and reactions are handled by separate kernels
 */
class QPXFVMassFractionTimeDerivative : public FVTimeKernel
{
public:
  static InputParameters validParams();

  QPXFVMassFractionTimeDerivative(const InputParameters & parameters);

protected:
  virtual ADReal computeQpResidual() override;

  /// Mixture density rho [kg/m^3]
  const Moose::Functor<ADReal> & _rho;
};