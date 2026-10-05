#include "PhysicsFVElectronGroundedSheathEnergyBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

registerMooseObject("PhysicsApp", PhysicsFVElectronGroundedSheathEnergyBC);

InputParameters
PhysicsFVElectronGroundedSheathEnergyBC::validParams()
{
  auto params = FVQpFluxBC::validParams();
  params.addClassDescription(
      "Applies grounded-conductor sheath-edge electron energy loss with (5/2) T_e + Delta phi "
      "and a differentiable Newton-globalization extension near phi=0.");
  params.addRequiredParam<MooseFunctorName>("electron_density", "Plasma-side electron density.");
  params.addRequiredParam<MooseFunctorName>("mean_electron_energy", "Plasma-side electron mean energy [eV].");
  params.addRequiredParam<MooseFunctorName>("potential", "Plasma potential [V].");
  params.addParam<Real>("energy_reference_eV", 1.0, "Legacy normalization energy [eV].");
  params.addParam<bool>("molar_energy_state", false, "Return conservative molar-energy flux.");
  params.addParam<bool>("physical_eV_state", false, "Return physical eV/(m^2 s) flux.");
  params.addParam<bool>(
      "apply_sheath_suppression",
      true,
      "Multiply the thermal primary-electron wall flux by exp(-Delta phi/T_e). Set false "
      "only for diagnostic comparison without the sheath suppression factor.");
  return params;
}

PhysicsFVElectronGroundedSheathEnergyBC::PhysicsFVElectronGroundedSheathEnergyBC(const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _potential(getFunctor<ADReal>("potential")),
    _energy_reference_eV(getParam<Real>("energy_reference_eV")),
    _molar_energy_state(getParam<bool>("molar_energy_state")),
    _physical_eV_state(getParam<bool>("physical_eV_state")),
    _apply_sheath_suppression(getParam<bool>("apply_sheath_suppression"))
{
  if (_molar_energy_state && _physical_eV_state)
    paramError("physical_eV_state", "molar_energy_state and physical_eV_state are mutually exclusive.");
  if (!_molar_energy_state && !_physical_eV_state && !parameters.isParamSetByUser("energy_reference_eV"))
    paramError("energy_reference_eV", "Legacy normalized-energy mode requires energy_reference_eV.");
  if (!_molar_energy_state && !_physical_eV_state && _energy_reference_eV <= 0.0)
    paramError("energy_reference_eV", "Electron-energy normalization scale must be positive.");
}

ADReal
PhysicsFVElectronGroundedSheathEnergyBC::computeQpResidual()
{
  const auto cell = _face_type == FaceInfo::VarFaceNeighbors::ELEM ? elemArg() : neighborArg();
  const auto state = determineState();
  const ADReal electron_density = _electron_density(cell, state);
  const ADReal mean_energy_eV = _mean_electron_energy(cell, state);
  const ADReal phi_s_V = _potential(cell, state);

  if (MetaPhysicL::raw_value(electron_density) < 0.0)
    mooseError("Grounded sheath energy collection requires electron density >= 0.");
  if (MetaPhysicL::raw_value(mean_energy_eV) <= 0.0)
    mooseError("Grounded sheath energy collection requires mean electron energy > 0 eV.");

  const ADReal effective_drop_V = PhysicsGroundedElectronSheath::smoothPositiveDropV(phi_s_V);
  const ADReal electron_temperature_eV = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy_eV);
  const ADReal primary_particle_flux =
      _apply_sheath_suppression
          ? PhysicsGroundedElectronSheath::primaryParticleFluxHat(
                electron_density, mean_energy_eV, effective_drop_V)
          : 0.25 * electron_density *
                PhysicsGroundedElectronSheath::meanSpeedMPerS(electron_temperature_eV);

  if (_molar_energy_state || _physical_eV_state)
    return primary_particle_flux * (2.5 * electron_temperature_eV + effective_drop_V);

  if (!_apply_sheath_suppression)
    return primary_particle_flux *
           (2.5 * electron_temperature_eV + effective_drop_V) / _energy_reference_eV;

  return PhysicsGroundedElectronSheath::primaryEnergyFluxHat(
      electron_density, mean_energy_eV, effective_drop_V, _energy_reference_eV);
}
