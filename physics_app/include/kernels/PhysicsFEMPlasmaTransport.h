#pragma once

#include "ADKernel.h"
#include "MooseFunctor.h"

/**
 * Continuous-Galerkin drift-diffusion kernel for a physical density-like state u:
 *
 *   Gamma = z mu u E - D grad(u),   E = -grad(phi)
 *
 * After integration by parts the volume contribution is
 *
 *   grad(test) . [D grad(u) + z mu u grad(phi)].
 *
 * Boundary fluxes are supplied separately through integrated BCs.
 */
class PhysicsFEMPlasmaDriftDiffusion : public ADKernel
{
public:
  static InputParameters validParams();
  PhysicsFEMPlasmaDriftDiffusion(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const ADVariableGradient & _grad_potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _diffusion;
  const Real _charge_number;
};

/**
 * Electron Joule-work term for a physical electron-energy density equation [eV/m^3].
 * Adds +E.Gamma_e to the residual, corresponding to Q_J=-E.Gamma_e on the RHS.
 */
class PhysicsFEMElectronJouleHeating : public ADKernel
{
public:
  static InputParameters validParams();
  PhysicsFEMElectronJouleHeating(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const ADVariableValue & _electron_density;
  const ADVariableGradient & _grad_electron_density;
  const ADVariableGradient & _grad_potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _diffusion;
};
