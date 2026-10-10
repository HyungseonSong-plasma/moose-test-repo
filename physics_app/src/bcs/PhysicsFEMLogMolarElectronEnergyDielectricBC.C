#include "ADIntegratedBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

#include <cmath>

class PhysicsFEMLogMolarElectronEnergyDielectricBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronEnergyDielectricBC(const InputParameters & parameters);

  // Both log_energy and log_electron_density intentionally live only in the
  // plasma block while this sideset is internal to plasma|dielectric.
  bool checkVariableBoundaryIntegrity() const override { return false; }

protected:
  ADReal computeQpResidual() override;

  const ADVariableValue & _log_electron_density;
};

registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronEnergyDielectricBC);

InputParameters
PhysicsFEMLogMolarElectronEnergyDielectricBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "One-sided FEM log-molar electron-energy loss on an internal plasma-dielectric "
      "interface. For the SEE=0 practical pilot it preserves the baseline no-sheath-"
      "suppression energy-wall law: Gamma_eps = (1/4 c_e vbar_e) (5/2 T_e). "
      "The electron variables may be restricted to the plasma block.");
  params.addRequiredCoupledVar(
      "log_electron_density", "Solved log-molar electron concentration.");
  return params;
}

PhysicsFEMLogMolarElectronEnergyDielectricBC::
PhysicsFEMLogMolarElectronEnergyDielectricBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _log_electron_density(adCoupledValue("log_electron_density"))
{
}

ADReal
PhysicsFEMLogMolarElectronEnergyDielectricBC::computeQpResidual()
{
  using std::exp;

  const ADReal c_e = exp(_log_electron_density[_qp]);
  const ADReal mean_energy = exp(_u[_qp] - _log_electron_density[_qp]);
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);

  const ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(Te);
  const ADReal particle_molar_flux_for_energy_bc = alpha * c_e;
  const ADReal energy_molar_flux = particle_molar_flux_for_energy_bc * (2.5 * Te);

  return _test[_i][_qp] * energy_molar_flux;
}
