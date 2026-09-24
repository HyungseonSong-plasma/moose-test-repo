#pragma once

#include "FVFluxKernel.h"

/**
 * Density-weighted FV advection of a species mass fraction using a prescribed
 * (read-only) velocity functor.
 *
 * Issue #331 Stage-B ownership adapter.  This object changes velocity
 * ownership only: the conservative flux remains
 *
 *   rho_f * (u_f . n) * w_{k,f}
 *
 * with the transported variable evaluated using the selected FV interpolation
 * and the upwind direction set by the prescribed face velocity.
 */
class PhysicsFVFrozenMassFractionAdvection : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVFrozenMassFractionAdvection(const InputParameters & parameters);

protected:
  virtual ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _rho;
  const Moose::Functor<ADRealVectorValue> & _velocity;
  const Moose::FV::InterpMethod _advected_interp_method;
};
