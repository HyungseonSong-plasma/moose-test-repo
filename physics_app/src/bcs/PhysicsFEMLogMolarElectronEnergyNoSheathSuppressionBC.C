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
};

registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC);

InputParameters
PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "FEM log-molar electron-energy wall loss with both the multiplicative sheath suppression "
      "exp(-Delta phi/T_e) and the additive sheath-energy term Delta phi disabled for the energy "
      "BC only. The electron particle BC is unchanged. Energy loss is purely thermal: "
      "Gamma_eps = (1/4 c_e vbar_e) (5/2 T_e).");
  params.addRequiredCoupledVar(
      "log_electron_density", "Solved log-molar electron concentration.");
  return params;
}

PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC::
PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _log_electron_density(adCoupledValue("log_electron_density"))
{
}

ADReal
PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC::computeQpResidual()
{
  using std::exp;

  const ADReal c_e = exp(_log_electron_density[_qp]);
  const ADReal mean_energy = exp(_u[_qp] - _log_electron_density[_qp]);
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);

  // Diagnostic energy-wall model:
  //   1) no exp(-Delta phi / T_e) sheath suppression in the energy BC,
  //   2) no +Delta phi sheath-energy contribution per collected electron.
  // The electron particle wall BC remains the standard sheath-suppressed model.
  const ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(Te);
  const ADReal particle_molar_flux_for_energy_bc = alpha * c_e;
  const ADReal energy_molar_flux = particle_molar_flux_for_energy_bc * (2.5 * Te);

  return _test[_i][_qp] * energy_molar_flux;
}
