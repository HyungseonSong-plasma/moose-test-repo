#include "PhysicsFVElectronReactionEnergySource.h"

registerMooseObject("PhysicsApp", PhysicsFVElectronReactionEnergySource);

InputParameters
PhysicsFVElectronReactionEnergySource::validParams()
{
  auto params = FVElementalKernel::validParams();

  params.addClassDescription(
      "Projects an existing canonical molar reaction progress into the normalized "
      "electron-energy equation. This object performs no kinetic-rate evaluation.");

  params.addRequiredParam<MooseFunctorName>(
      "reaction_progress", "Canonical molar reaction progress [mol/(m^3 s)].");
  params.addRequiredRangeCheckedParam<Real>(
      "energy_loss_eV", "energy_loss_eV > 0", "Positive electron energy loss per event [eV].");
  params.addRequiredRangeCheckedParam<Real>(
      "n_ref", "n_ref > 0", "Electron-density normalization n_ref [1/m^3].");
  params.addRequiredRangeCheckedParam<Real>(
      "energy_reference_eV",
      "energy_reference_eV > 0",
      "Positive electron-energy normalization epsilon_ref [eV].");

  return params;
}

PhysicsFVElectronReactionEnergySource::PhysicsFVElectronReactionEnergySource(
    const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _reaction_progress(getFunctor<ADReal>("reaction_progress")),
    _energy_loss_eV(getParam<Real>("energy_loss_eV")),
    _n_ref(getParam<Real>("n_ref")),
    _energy_reference_eV(getParam<Real>("energy_reference_eV"))
{
}

ADReal
PhysicsFVElectronReactionEnergySource::computeQpResidual()
{
  constexpr Real N_A = 6.02214076e23;

  const ADReal R = _reaction_progress(makeElemArg(_current_elem), determineState());
  if (R.value() < 0.0)
    mooseError("PhysicsFVElectronReactionEnergySource requires reaction_progress >= 0.");

  const ADReal physical_energy_source = -_energy_loss_eV * N_A * R;
  const ADReal normalized_rhs =
      physical_energy_source / (_n_ref * _energy_reference_eV);

  return -normalized_rhs;
}
