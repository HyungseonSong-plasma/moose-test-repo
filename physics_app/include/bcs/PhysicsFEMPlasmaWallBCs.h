#pragma once

#include "ADIntegratedBC.h"

/** O2+ wall loss for a solved log-molar ion concentration. */
class PhysicsFEMLogMolarIonWallBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarIonWallBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
  const ADVariableGradient & _grad_potential;
  const Real _mobility;
  const Real _gas_temperature;
  const Real _molar_mass;
  const Real _charge_number;
  const Real _sticking;
  const Real _migration_gate_smoothing_width;
};
