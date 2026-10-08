#include "ADIntegratedBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

#include <cmath>

class PhysicsFEMLogMolarElectronNoSheathSuppressionBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronNoSheathSuppressionBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const ADVariableValue & _log_energy;
};

registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronNoSheathSuppressionBC);

InputParameters
PhysicsFEMLogMolarElectronNoSheathSuppressionBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "FEM log-molar electron wall collection using only the thermal half-Maxwellian flux, "
      "with exp(-Delta phi/T_e) sheath suppression disabled.");
  params.addRequiredCoupledVar("log_energy", "Solved log-molar electron energy density.");
  return params;
}

PhysicsFEMLogMolarElectronNoSheathSuppressionBC::
PhysicsFEMLogMolarElectronNoSheathSuppressionBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _log_energy(adCoupledValue("log_energy"))
{
}

ADReal
PhysicsFEMLogMolarElectronNoSheathSuppressionBC::computeQpResidual()
{
  using std::exp;

  const ADReal c_e = exp(_u[_qp]);
  const ADReal mean_energy = exp(_log_energy[_qp] - _u[_qp]);
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);

  // Thermal collection only: deliberately omit exp(-Delta phi / T_e).
  const ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(Te);
  const ADReal molar_flux = alpha * c_e;

  return _test[_i][_qp] * molar_flux;
}
