#pragma once

#include "FVFluxKernel.h"

/**
 * Finite-volume electrostatic drift flux for a scalar transported variable.
 *
 * Flux:
 *
 *   F_n = c_f * u_up * z * mu_f * E_f . n
 *
 * with
 *
 *   E = -grad(phi)
 *
 * The transported scalar is interpolated with the same FV advection
 * machinery used by the framework FVAdvection kernel. In transient runs the
 * limiter state is taken from the previous time level, while the current AD
 * solution is retained for the transported value and electrostatic field.
 */
class PhysicsFVElectrostaticDrift : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVElectrostaticDrift(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _carrier;
  const Real _charge_number;

  Moose::FV::InterpMethod _advected_interp_method;
};
