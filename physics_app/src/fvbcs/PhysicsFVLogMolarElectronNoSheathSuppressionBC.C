#include "FVQpFluxBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

#include <cmath>

class PhysicsFVLogMolarElectronNoSheathSuppressionBC : public FVQpFluxBC
{
public:
  static InputParameters validParams();
  PhysicsFVLogMolarElectronNoSheathSuppressionBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _mean_electron_energy;
};

class PhysicsFVLogMolarElectronEnergyNoSheathSuppressionBC : public FVQpFluxBC
{
public:
  static InputParameters validParams();
  PhysicsFVLogMolarElectronEnergyNoSheathSuppressionBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _mean_electron_energy;
};

registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronNoSheathSuppressionBC);
registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronEnergyNoSheathSuppressionBC);

InputParameters
PhysicsFVLogMolarElectronNoSheathSuppressionBC::validParams()
{
  auto params = FVQpFluxBC::validParams();
  params.addClassDescription(
      "FV log-molar electron wall collection using the thermal half-Maxwellian flux only; "
      "no sheath suppression factor is applied.");
  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Electron molar concentration c_e [mol/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "mean_electron_energy", "Mean electron energy [eV].");
  return params;
}

PhysicsFVLogMolarElectronNoSheathSuppressionBC::
PhysicsFVLogMolarElectronNoSheathSuppressionBC(const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy"))
{
}

ADReal
PhysicsFVLogMolarElectronNoSheathSuppressionBC::computeQpResidual()
{
  const auto cell =
      _face_type == FaceInfo::VarFaceNeighbors::ELEM ? elemArg() : neighborArg();
  const auto state = determineState();
  const ADReal c_e = _electron_density(cell, state);
  const ADReal mean_energy = _mean_electron_energy(cell, state);
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);
  const ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(Te);
  return alpha * c_e;
}

InputParameters
PhysicsFVLogMolarElectronEnergyNoSheathSuppressionBC::validParams()
{
  auto params = FVQpFluxBC::validParams();
  params.addClassDescription(
      "FV log-molar electron-energy wall loss matching the FEM thermal-only closure: "
      "Gamma_eps=(1/4 c_e vbar_e)(5/2 T_e), with no sheath suppression or Delta-phi term.");
  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Electron molar concentration c_e [mol/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "mean_electron_energy", "Mean electron energy [eV].");
  return params;
}

PhysicsFVLogMolarElectronEnergyNoSheathSuppressionBC::
PhysicsFVLogMolarElectronEnergyNoSheathSuppressionBC(const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy"))
{
}

ADReal
PhysicsFVLogMolarElectronEnergyNoSheathSuppressionBC::computeQpResidual()
{
  const auto cell =
      _face_type == FaceInfo::VarFaceNeighbors::ELEM ? elemArg() : neighborArg();
  const auto state = determineState();
  const ADReal c_e = _electron_density(cell, state);
  const ADReal mean_energy = _mean_electron_energy(cell, state);
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);
  const ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(Te);
  return alpha * c_e * (2.5 * Te);
}
