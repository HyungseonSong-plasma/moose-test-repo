#pragma once

#include "FVFluxKernel.h"

/**
 * Heavy-species thermal diffusion flux.
 *
 * Implements
 *
 *   j_T = -D_T * grad(T) / T
 *
 * where D_T is the multicomponent thermal diffusion coefficient
 * with units kg/(m s).
 */
class QPXFVThermalDiffusion : public FVFluxKernel
{
public:
  static InputParameters validParams();

  QPXFVThermalDiffusion(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  /// Gas temperature [K]
  const Moose::Functor<ADReal> & _temperature;

  /// Thermal diffusion coefficient [kg/(m s)]
  const Moose::Functor<ADReal> & _thermal_diffusion_coefficient;

  /// Enable/disable term for regression testing
  const bool _include_thermal_diffusion;
};
