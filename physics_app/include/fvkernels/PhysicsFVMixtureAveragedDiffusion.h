#pragma once

#include "FVFluxKernel.h"

/**
 * Mixture-averaged diffusion flux for a heavy-species mass fraction.
 *
 * Implements
 *
 *   j_k = rho * D_km *
 *         [ grad(w_k) + (w_k / Mn) grad(Mn) ]
 *
 * and contributes
 *
 *   div(j_k)
 *
 * to the finite-volume residual.
 *
 * Thermal diffusion, electric-field migration, and mixture-diffusion
 * correction are intentionally excluded in the first implementation.
 */
class PhysicsFVMixtureAveragedDiffusion : public FVFluxKernel
{
public:
  static InputParameters validParams();

  PhysicsFVMixtureAveragedDiffusion(const InputParameters & parameters);

protected:
  virtual ADReal computeQpResidual() override;

  /// Mixture density rho [kg/m^3]
  const Moose::Functor<ADReal> & _rho;

  /// Mixture-averaged species diffusivity D_km [m^2/s]
  const Moose::Functor<ADReal> & _diffusivity;

  /// Mean molar mass Mn [kg/mol]
  const Moose::Functor<ADReal> & _mean_molar_mass;

  /// Face interpolation method for rho*D
  Moose::FV::InterpMethod _coeff_interp_method;

  const bool _include_molar_mass_gradient;
};