#pragma once

#include "INSFVScalarFieldAdvection.h"

/**
 * Density-weighted finite-volume advection of a species mass fraction.
 *
 * Implements the face flux
 *
 *   rho * (u . n) * w_k
 *
 * using the same Rhie-Chow velocity and advected-variable interpolation
 * as INSFVScalarFieldAdvection.
 */
class QPXFVMassFractionAdvection : public INSFVScalarFieldAdvection
{
public:
  static InputParameters validParams();

  QPXFVMassFractionAdvection(const InputParameters & parameters);

protected:
  virtual ADReal computeQpResidual() override;

  /// Mixture density rho [kg/m^3]
  const Moose::Functor<ADReal> & _rho;
};