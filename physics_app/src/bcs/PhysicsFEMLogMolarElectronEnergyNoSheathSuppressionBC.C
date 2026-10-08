#include "ADIntegratedBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

#include <cmath>

class PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const ADVariableValue & _log_electron_density;
  const ADVariableValue & _potential;
};

registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC);

InputParameters
PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "FEM log-molar electron-energy wall loss with the multiplicative sheath suppression "
      "exp(-Delta phi/T_e) disabled for the energy BC only. The electron particle BC is "
      "unchanged, and the additive sheath energy Delta phi remains in the energy per lost electron.");
  params.addRequiredCoupledVar(
      "log_electron_density", "Solved log-molar electron concentration.");
  params.addRequiredCoupledVar("potential", "Plasma potential [V].");
  return params;
}

PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC::
PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _log_electron_density(adCoupledValue("log_electron_density")),
    _potential(adCoupledValue("potential"))
{
}

ADReal
PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC::computeQpResidual()
{
  using std::exp;

  const ADReal c_e = exp(_log_electron_density[_qp]);
  const ADReal mean_energy = exp(_u[_qp] - _log_electron_density[_qp]);
  const ADReal drop = PhysicsGroundedElectronSheath::smoothPositiveDropV(_potential[_qp]);
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);

  // Deliberately omit the multiplicative exp(-Delta phi / T_e) sheath suppression
  // from the ENERGY boundary condition. Keep the thermal collection prefactor and
  // the additive sheath-energy loss (+Delta phi) per collected electron.
  const ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(Te);
  const ADReal particle_molar_flux_for_energy_bc = alpha * c_e;
  const ADReal energy_molar_flux =
      particle_molar_flux_for_energy_bc * (2.5 * Te + drop);

  return _test[_i][_qp] * energy_molar_flux;
}
