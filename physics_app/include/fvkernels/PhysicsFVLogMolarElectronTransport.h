#pragma once

#include "FVElementalKernel.h"
#include "FVFluxKernel.h"

/**
 * Backward-Euler time derivative for c_e = exp(log_e), where c_e is the
 * numerical electron molar concentration in mol/m^3 referenced to 1 mol/m^3.
 *
 * The solved variable is log_e = ln(c_e / (1 mol/m^3)); the residual is the
 * conservative molar-density derivative (c_e^{n+1} - c_e^n) / dt.
 */
class PhysicsFVLogMolarElectronTimeDerivative : public FVElementalKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMolarElectronTimeDerivative(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
};

/**
 * Electron diffusion in log-molar representation.
 *
 * Continuous flux: Gamma_diff = -D_e * c_e * grad(log_e) = -D_e * grad(c_e).
 */
class PhysicsFVLogMolarElectronDiffusion : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMolarElectronDiffusion(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _coeff;
  Moose::FV::InterpMethod _coeff_interp_method;
};

/**
 * Electrostatic drift in log-molar representation.
 *
 * The solved variable is log_e, but the transported conservative state is
 * c_e = exp(log_e). The drift velocity/sign convention matches
 * PhysicsFVElectrostaticDrift.
 */
class PhysicsFVLogMolarElectrostaticDrift : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMolarElectrostaticDrift(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _carrier;
  const Real _charge_number;
  Moose::FV::InterpMethod _advected_interp_method;
};
