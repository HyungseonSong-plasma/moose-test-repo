#pragma once

#include "ADIntegratedBC.h"

class PhysicsFEMElectronGroundedSheathBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMElectronGroundedSheathBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
  const ADVariableValue & _electron_energy_density;
  const ADVariableValue & _potential;
};

class PhysicsFEMElectronGroundedSheathEnergyBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMElectronGroundedSheathEnergyBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
  const ADVariableValue & _electron_density;
  const ADVariableValue & _potential;
};

class PhysicsFEMIonWallBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMIonWallBC(const InputParameters & parameters);

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

/** Grounded electron particle collection for a solved log-molar electron concentration. */
class PhysicsFEMLogMolarElectronGroundedSheathBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronGroundedSheathBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
  const ADVariableValue & _log_energy;
  const ADVariableValue & _potential;
};

/** Grounded electron energy loss for a solved log-molar electron energy density. */
class PhysicsFEMLogMolarElectronGroundedSheathEnergyBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronGroundedSheathEnergyBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
  const ADVariableValue & _log_electron_density;
  const ADVariableValue & _potential;
};

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
