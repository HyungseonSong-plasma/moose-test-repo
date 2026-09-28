#pragma once

#include "FVTimeKernel.h"
#include "FVFluxKernel.h"
#include "FVDiffusionInterpolationInterface.h"

/**
 * Conservative backward-Euler accumulation for mean electron energy:
 *
 *   d(n_e * mean_en) / dt
 *
 * where mean_en [eV] is the solved FV variable and n_e [1/m^3] is supplied
 * as a functor.
 */
class PhysicsFVElectronMeanEnergyTimeDerivative : public FVTimeKernel
{
public:
  static InputParameters validParams();
  PhysicsFVElectronMeanEnergyTimeDerivative(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _electron_density;
};

/**
 * Diffusion of physical electron energy density n_e * mean_en:
 *
 *   -D_epsilon grad(n_e * mean_en)
 */
class PhysicsFVElectronMeanEnergyDiffusion : public FVFluxKernel,
                                             public FVDiffusionInterpolationInterface
{
public:
  static InputParameters validParams();
  PhysicsFVElectronMeanEnergyDiffusion(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _coeff;
  Moose::FV::InterpMethod _coeff_interp_method;
};

/**
 * Electrostatic drift of physical electron energy density n_e * mean_en.
 *
 * The face/upwind contract matches PhysicsFVElectrostaticDrift, but the
 * transported quantity is reconstructed from the solved mean energy.
 */
class PhysicsFVElectronMeanEnergyElectrostaticDrift : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVElectronMeanEnergyElectrostaticDrift(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Real _charge_number;
  Moose::FV::InterpMethod _advected_interp_method;
};
