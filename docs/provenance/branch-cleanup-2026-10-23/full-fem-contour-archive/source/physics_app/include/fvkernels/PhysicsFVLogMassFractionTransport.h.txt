#pragma once

#include "FVElementalKernel.h"
#include "FVFluxKernel.h"
#include "INSFVScalarFieldAdvection.h"

/**
 * Conservative backward-Euler accumulation for a heavy-species mass fraction
 * represented by a logarithmic nonlinear coordinate.
 *
 * The nonlinear variable identifies the residual row. The physical mass fraction
 * is supplied as an AD functor so the coordinate may be either a simple
 * Y=Y_ref*exp(eta) map or a coupled log-ratio/simplex reconstruction.
 */
class PhysicsFVLogMassFractionTimeDerivative : public FVElementalKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMassFractionTimeDerivative(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _rho;
  const Moose::Functor<ADReal> & _mass_fraction;
};

/** Density-weighted advection of a reconstructed physical heavy mass fraction. */
class PhysicsFVLogMassFractionAdvection : public INSFVScalarFieldAdvection
{
public:
  static InputParameters validParams();
  PhysicsFVLogMassFractionAdvection(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _rho;
  const Moose::Functor<ADReal> & _mass_fraction;
};

/** Mixture-averaged diffusion of a reconstructed physical heavy mass fraction. */
class PhysicsFVLogMixtureAveragedDiffusion : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMixtureAveragedDiffusion(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _rho;
  const Moose::Functor<ADReal> & _mass_fraction;
  const Moose::Functor<ADReal> & _diffusivity;
  const Moose::Functor<ADReal> & _mean_molar_mass;
  Moose::FV::InterpMethod _coeff_interp_method;
  const bool _include_molar_mass_gradient;
};

/** Electrostatic drift of a reconstructed physical heavy mass fraction. */
class PhysicsFVLogMassFractionElectrostaticDrift : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVLogMassFractionElectrostaticDrift(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _mass_fraction;
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _carrier;
  const Real _charge_number;
  Moose::FV::InterpMethod _advected_interp_method;
};

/**
 * Zero-net-heavy-mass electromigration correction for a log-coordinate equation.
 *
 * All physical mass fractions are AD functors, preserving the full chain rule
 * through a log-ratio/simplex reconstruction in a monolithic Jacobian.
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
