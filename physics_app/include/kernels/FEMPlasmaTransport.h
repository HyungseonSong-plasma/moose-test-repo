#pragma once

#include "ADKernel.h"
#include "ADTimeKernel.h"
#include "MooseFunctor.h"

/**
 * Conservative backward-Euler time derivative of c=exp(u), where u is a log-molar state.
 */
class FEMLogMolarTimeDerivative : public ADTimeKernel
{
public:
  static InputParameters validParams();
  FEMLogMolarTimeDerivative(const InputParameters & parameters);

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
class FEMLogMolarDriftDiffusion : public ADKernel
{
public:
  static InputParameters validParams();
  FEMLogMolarDriftDiffusion(const InputParameters & parameters);

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
class FEMLogMolarElectronJouleHeating : public ADKernel
{
public:
  static InputParameters validParams();
  FEMLogMolarElectronJouleHeating(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const ADVariableValue & _log_electron_density;
  const ADVariableGradient & _grad_log_electron_density;
  const ADVariableGradient & _grad_potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _diffusion;
};
