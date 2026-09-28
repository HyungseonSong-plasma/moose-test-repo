#pragma once

#include "FVElementalKernel.h"
#include "FVFluxKernel.h"
#include "FVDiffusionInterpolationInterface.h"
#include "PhysicsFVElectrostaticDrift.h"

/** Conservative backward-Euler time derivative of c_e = exp(log_e) [mol/m^3]. */
class PhysicsFVLogMolarElectronTimeDerivative : public FVElementalKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMolarElectronTimeDerivative(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
};

/** Conservative electron diffusion for c_e = exp(log_e) on FV cells. */
class PhysicsFVLogMolarElectronDiffusion : public FVFluxKernel,
                                           public FVDiffusionInterpolationInterface
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
 * Backward-compatible alias for the canonical PhysicsFVElectrostaticDrift
 * configured with transported_state=exponential.
 *
 * New inputs should use PhysicsFVElectrostaticDrift directly.
 */
class PhysicsFVLogMolarElectrostaticDrift : public PhysicsFVElectrostaticDrift
{
public:
  static InputParameters validParams();
  PhysicsFVLogMolarElectrostaticDrift(const InputParameters & parameters);
};

/** Convert a physical electron number source [1/(m^3 s)] to molar source [mol/(m^3 s)]. */
class PhysicsFVLogMolarElectronReactionSource : public FVElementalKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMolarElectronReactionSource(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _number_source;
};
