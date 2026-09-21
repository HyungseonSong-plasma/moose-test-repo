#pragma once

#include "FVQpFluxBC.h"

/**
 * Primary-electron collection at a grounded conducting wall.
 *
 * By default the solved variable is the historical normalized density and the
 * residual is Gamma_e/n_ref. With log_molar_state=true the solved variable is
 * log_e=ln(c_e/[1 mol/m^3]); the object reconstructs n_e=N_A exp(log_e) and
 * returns the physical particle flux. This preserves the accepted sheath law
 * while removing n_ref from the T1 particle equation.
 */
class PhysicsFVElectronGroundedSheathCollectionBC : public FVQpFluxBC
{
public:
  static InputParameters validParams();
  PhysicsFVElectronGroundedSheathCollectionBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _mean_electron_energy;
  const Moose::Functor<ADReal> & _potential;
  const bool _log_molar_state;
};
