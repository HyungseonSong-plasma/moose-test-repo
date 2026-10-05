#pragma once

#include "FVElementalKernel.h"
#include "FVFluxKernel.h"
#include "INSFVScalarFieldAdvection.h"

/**
 * Conservative backward-Euler accumulation for a heavy-species mass fraction
 * represented by the nonlinear variable eta_k = log(Y_k).
 *
 * The residual remains the physical conservative equation:
 *
 *   [rho^n exp(eta_k^n) - rho^(n-1) exp(eta_k^(n-1))] / dt.
 */
class PhysicsFVLogMassFractionTimeDerivative : public FVElementalKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMassFractionTimeDerivative(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _rho;
};

/**
 * Density-weighted advection of Y_k = exp(eta_k), with eta_k the solved FV variable.
 */
class PhysicsFVLogMassFractionAdvection : public INSFVScalarFieldAdvection
{
public:
  static InputParameters validParams();
  PhysicsFVLogMassFractionAdvection(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _rho;
};

/**
 * Mixture-averaged diffusion of Y_k = exp(eta_k), preserving the physical
 * mass-fraction flux and optional mean-molar-mass-gradient correction.
 */
class PhysicsFVLogMixtureAveragedDiffusion : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMixtureAveragedDiffusion(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _rho;
  const Moose::Functor<ADReal> & _diffusivity;
  const Moose::Functor<ADReal> & _mean_molar_mass;
  Moose::FV::InterpMethod _coeff_interp_method;
  const bool _include_molar_mass_gradient;
};

/**
 * Electrostatic drift of Y_k = exp(eta_k), with eta_k the solved FV variable.
 *
 * For a heavy mass-fraction equation use carrier=rho.
 */
class PhysicsFVLogMassFractionElectrostaticDrift : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMassFractionElectrostaticDrift(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _carrier;
  const Real _charge_number;
  Moose::FV::InterpMethod _advected_interp_method;
};

/**
 * Zero-net-heavy-mass electromigration correction for a log mass-fraction equation.
 *
 * The solved variable identifies the residual row. Physical mass fractions are
 * supplied as AD functors, so the Jacobian retains the eta -> exp(eta) chain rule.
 */
class PhysicsFVLogHeavyMassElectromigrationCorrection : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogHeavyMassElectromigrationCorrection(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _rho;
  const Moose::Functor<ADReal> & _species_mass_fraction;

  const std::vector<MooseFunctorName> _ion_mass_fraction_names;
  const std::vector<MooseFunctorName> _ion_mobility_names;
  const std::vector<Real> _ion_charges;

  std::vector<const Moose::Functor<ADReal> *> _ion_mass_fractions;
  std::vector<const Moose::Functor<ADReal> *> _ion_mobilities;

  Moose::FV::InterpMethod _advected_interp_method;
};
