#include "PhysicsFVElectronGroundedSheathEnergyBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

registerMooseObject("PhysicsApp", PhysicsFVElectronGroundedSheathEnergyBC);

InputParameters
PhysicsFVElectronGroundedSheathEnergyBC::validParams()
{
  auto params = FVQpFluxBC::validParams();

  params.addClassDescription(
      "Applies the W4.5 grounded-conductor sheath-edge primary-electron energy loss "
      "using the same collected primary population as PhysicsFVElectronGroundedSheathCollectionBC. "
      "T2 can return the conservative molar-energy flux directly.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_density",
      "Plasma-side electron density. Legacy mode expects n_e/n_ref; molar-energy mode expects c_e [mol/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "mean_electron_energy",
      "Plasma-side electron mean energy [eV]. The sheath temperature is (2/3) mean energy.");
  params.addRequiredParam<MooseFunctorName>(
      "potential",
      "Plasma potential [V]. The plasma-side element value is used, not the grounded face value.");
  params.addParam<Real>(
      "energy_reference_eV",
      1.0,
      "Positive legacy normalization energy epsilon_ref [eV]. Must be explicitly supplied in legacy mode and is ignored in molar-energy mode.");
  params.addParam<bool>(
      "molar_energy_state",
      false,
      "If true, electron_density is c_e [mol/m^3] and the residual is returned in eV mol/(m^2 s) without an arbitrary normalization scale.");

  return params;
}

PhysicsFVElectronGroundedSheathEnergyBC::PhysicsFVElectronGroundedSheathEnergyBC(
    const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _potential(getFunctor<ADReal>("potential")),
    _energy_reference_eV(getParam<Real>("energy_reference_eV")),
    _molar_energy_state(getParam<bool>("molar_energy_state"))
{
  if (!_molar_energy_state && !parameters.isParamSetByUser("energy_reference_eV"))
    paramError("energy_reference_eV",
               "Legacy normalized-energy mode requires an explicit energy_reference_eV.");
  if (!_molar_energy_state && _energy_reference_eV <= 0.0)
    paramError("energy_reference_eV", "Electron-energy normalization scale must be positive.");
}

ADReal
PhysicsFVElectronGroundedSheathEnergyBC::computeQpResidual()
{
  const auto cell =
      _face_type == FaceInfo::VarFaceNeighbors::ELEM ? elemArg() : neighborArg();
  const auto state = determineState();

  const ADReal electron_density = _electron_density(cell, state);
  const ADReal mean_energy_eV = _mean_electron_energy(cell, state);
  const ADReal phi_s_V = _potential(cell, state);

  const Real raw_electron_density = MetaPhysicL::raw_value(electron_density);
  const Real raw_mean_energy_eV = MetaPhysicL::raw_value(mean_energy_eV);
  const Real raw_phi_s_V = MetaPhysicL::raw_value(phi_s_V);

  if (raw_electron_density < 0.0)
    mooseError("Grounded sheath energy collection requires electron density >= 0; got ",
               raw_electron_density);
  if (raw_mean_energy_eV <= 0.0)
    mooseError("Grounded sheath energy collection requires mean electron energy > 0 eV; got ",
               raw_mean_energy_eV);
  if (raw_phi_s_V < -PhysicsGroundedElectronSheath::negative_drop_tolerance_V)
    mooseError("Grounded sheath energy collection is outside its W4.5 validity branch: phi_s = ",
               raw_phi_s_V,
               " V < 0 V. Electron-attracting/inverse sheath physics requires a separate owner.");

  const ADReal effective_drop_V = raw_phi_s_V < 0.0 ? ADReal(0.0) : phi_s_V;

  if (_molar_energy_state)
  {
    const ADReal electron_temperature_eV =
        PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy_eV);
    const ADReal primary_particle_flux_molar =
        PhysicsGroundedElectronSheath::primaryParticleFluxHat(
            electron_density, mean_energy_eV, effective_drop_V);
    return primary_particle_flux_molar *
           (2.0 * electron_temperature_eV + effective_drop_V);
  }

  // Positive FVQpFluxBC residual is outward loss from the solved bulk energy.
  return PhysicsGroundedElectronSheath::primaryEnergyFluxHat(
      electron_density, mean_energy_eV, effective_drop_V, _energy_reference_eV);
}