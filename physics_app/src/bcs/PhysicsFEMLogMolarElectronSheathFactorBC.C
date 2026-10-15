#include "ADIntegratedBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

#include <cmath>

class PhysicsFEMLogMolarElectronSheathFactorBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronSheathFactorBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const ADVariableValue & _log_energy;
  const Real _sheath_factor;
};

class PhysicsFEMLogMolarElectronEnergySheathFactorBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronEnergySheathFactorBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const ADVariableValue & _log_electron_density;
  const Real _sheath_factor;
};

registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronSheathFactorBC);
registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronEnergySheathFactorBC);

InputParameters
PhysicsFEMLogMolarElectronSheathFactorBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "FEM log-molar electron wall collection with an explicit multiplicative sheath factor. "
      "This controlled discriminator scales the thermal half-Maxwellian particle flux without "
      "using the Dirichlet wall value of potential as a sheath-edge voltage.");
  params.addRequiredCoupledVar("log_energy", "Solved log-molar electron energy density.");
  params.addRequiredParam<Real>("sheath_factor", "Dimensionless multiplier on thermal electron wall flux.");
  return params;
}

PhysicsFEMLogMolarElectronSheathFactorBC::
PhysicsFEMLogMolarElectronSheathFactorBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _log_energy(adCoupledValue("log_energy")),
    _sheath_factor(getParam<Real>("sheath_factor"))
{
  if (_sheath_factor <= 0.0 || _sheath_factor > 1.0)
    paramError("sheath_factor", "sheath_factor must satisfy 0 < sheath_factor <= 1.");
}

ADReal
PhysicsFEMLogMolarElectronSheathFactorBC::computeQpResidual()
{
  using std::exp;

  const ADReal c_e = exp(_u[_qp]);
  const ADReal mean_energy = exp(_log_energy[_qp] - _u[_qp]);
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);
  const ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(Te);
  const ADReal molar_flux = _sheath_factor * alpha * c_e;

  return _test[_i][_qp] * molar_flux;
}

InputParameters
PhysicsFEMLogMolarElectronEnergySheathFactorBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "FEM log-molar electron-energy wall loss with the same explicit multiplicative sheath "
      "factor as the particle BC. The energy per collected electron remains the thermal-only "
      "5/2 T_e closure; no additive Delta-phi term is introduced in this discriminator.");
  params.addRequiredCoupledVar(
      "log_electron_density", "Solved log-molar electron concentration.");
  params.addRequiredParam<Real>("sheath_factor", "Dimensionless multiplier on thermal electron-energy wall flux.");
  return params;
}

PhysicsFEMLogMolarElectronEnergySheathFactorBC::
PhysicsFEMLogMolarElectronEnergySheathFactorBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _log_electron_density(adCoupledValue("log_electron_density")),
    _sheath_factor(getParam<Real>("sheath_factor"))
{
  if (_sheath_factor <= 0.0 || _sheath_factor > 1.0)
    paramError("sheath_factor", "sheath_factor must satisfy 0 < sheath_factor <= 1.");
}

ADReal
PhysicsFEMLogMolarElectronEnergySheathFactorBC::computeQpResidual()
{
  using std::exp;

  const ADReal c_e = exp(_log_electron_density[_qp]);
  const ADReal mean_energy = exp(_u[_qp] - _log_electron_density[_qp]);
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);
  const ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(Te);
  const ADReal particle_molar_flux = _sheath_factor * alpha * c_e;
  const ADReal energy_molar_flux = particle_molar_flux * (2.5 * Te);

  return _test[_i][_qp] * energy_molar_flux;
}
