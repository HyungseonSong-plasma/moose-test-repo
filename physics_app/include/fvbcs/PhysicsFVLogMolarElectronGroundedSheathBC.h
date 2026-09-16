#pragma once

#include "FVQpFluxBC.h"

/**
 * Grounded electron-repelling sheath collection for a log-molar electron state.
 *
 * The solved variable is log_e = ln(c_e / (1 mol/m^3)), so exp(log_e) is the
 * numerical electron molar concentration in mol/m^3. The returned boundary
 * flux is therefore mol/(m^2 s), consistent with the transformed conservative
 * electron equation.
 */
class PhysicsFVLogMolarElectronGroundedSheathBC : public FVQpFluxBC
{
public:
  static InputParameters validParams();
  PhysicsFVLogMolarElectronGroundedSheathBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _mean_electron_energy;
  const Moose::Functor<ADReal> & _potential;
};
