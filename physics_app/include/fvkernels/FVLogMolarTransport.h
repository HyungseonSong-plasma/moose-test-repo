#pragma once

#include "FVElementalKernel.h"
#include "FVFluxKernel.h"
#include "FVDiffusionInterpolationInterface.h"

/** Conservative backward-Euler time derivative of c = exp(log_c) [mol/m^3]. */
class FVLogMolarTimeDerivative : public FVElementalKernel
{
public:
  static InputParameters validParams();
  FVLogMolarTimeDerivative(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
};

/** Conservative species diffusion for c = exp(log_c) on FV cells. */
class FVLogMolarDiffusion : public FVFluxKernel,
                                           public FVDiffusionInterpolationInterface
{
public:
  static InputParameters validParams();
  FVLogMolarDiffusion(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _coeff;
  Moose::FV::InterpMethod _coeff_interp_method;
};

/** Electrostatic drift of c = exp(log_c) while log_c is the solved FV variable. */
class FVLogMolarElectrostaticDrift : public FVFluxKernel
{
public:
  static InputParameters validParams();
  FVLogMolarElectrostaticDrift(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _carrier;
  const Real _charge_number;
  const bool _use_element_gradient_for_potential;
  const bool _use_limited_linear_reconstruction;
  Moose::FV::InterpMethod _advected_interp_method;
};
