#pragma once

#include "ADKernel.h"
#include "ADTimeKernel.h"
#include "MooseFunctor.h"

/**
 * Existing physical-state continuous-Galerkin drift-diffusion kernel.
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
 * Existing physical-state electron Joule-work kernel.
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

/**
 * Conservative backward-Euler time derivative of c=exp(u), where u is a log-molar state.
 */
class PhysicsFEMLogMolarTimeDerivative : public ADTimeKernel
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarTimeDerivative(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const VariableValue & _u_old;
};

/**
 * Continuous-Galerkin drift-diffusion for a log-molar state u=log(c):
 *
 *   Gamma = z mu c E - D grad(c),  c=exp(u), E=-grad(phi).
 *
 * The volume residual is grad(test).[D grad(c) + z mu c grad(phi)].
 */
class PhysicsFEMLogMolarDriftDiffusion : public ADKernel
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarDriftDiffusion(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const ADVariableGradient & _grad_potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _diffusion;
  const Real _charge_number;
};

/**
 * Electron Joule-work term for log-molar electron density and log-molar energy states.
 * The residual units are eV mol/(m^3 s), matching exp(log_energy).
 */
class PhysicsFEMLogMolarElectronJouleHeating : public ADKernel
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronJouleHeating(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const ADVariableValue & _log_electron_density;
  const ADVariableGradient & _grad_log_electron_density;
  const ADVariableGradient & _grad_potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _diffusion;
};
