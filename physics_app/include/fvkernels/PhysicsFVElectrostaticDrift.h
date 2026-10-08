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
 * By default the potential gradient is evaluated directly on the FV face.
 * For mixed FE/FV systems, continuous FEM variables do not provide a FaceArg
 * gradient.  In that case use_element_gradient_for_potential reconstructs the
 * face electric field from adjacent element gradients (and uses the adjacent
 * element gradient on an external boundary).
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
  const bool _freeze_upwind_direction_to_old_potential;
  const bool _lag_advected_variable_to_old_time;
  const bool _use_element_gradient_for_potential;

  Moose::FV::InterpMethod _advected_interp_method;
};
