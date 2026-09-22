#include "PhysicsFVElectronGroundedSheathEnergyBC.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVElectronGroundedSheathEnergyBC);

namespace
{
constexpr Real negative_drop_tolerance_V = 1.0e-10;
constexpr Real elementary_charge_C = 1.602176634e-19;
constexpr Real electron_mass_kg = 9.1093837139e-31;
constexpr Real pi = 3.141592653589793238462643383279502884;

ADReal
electronTemperatureEV(const ADReal & mean_energy_eV)
{
  return (2.0 / 3.0) * mean_energy_eV;
}

ADReal
primaryParticleFluxHat(const ADReal & n_e_hat,
                       const ADReal & mean_energy_eV,
                       const ADReal & effective_drop_V)
{
  using std::exp;
  using std::sqrt;
  const ADReal electron_temperature_eV = electronTemperatureEV(mean_energy_eV);
  const ADReal mean_speed_m_s =
      sqrt(8.0 * elementary_charge_C * electron_temperature_eV /
           (pi * electron_mass_kg));
  return 0.25 * n_e_hat * mean_speed_m_s *
         exp(-effective_drop_V / electron_temperature_eV);
}
}

InputParameters
PhysicsFVElectronGroundedSheathEnergyBC::validParams()
{
  auto params = FVQpFluxBC::validParams();

  params.addClassDescription(
      "Legacy compatibility owner for the accepted grounded-conductor sheath-edge "
      "primary-electron energy loss. New input decks should prefer standard MOOSE "
      "functor materials and FVFunctorNeumannBC.");

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
  if (raw_phi_s_V < -negative_drop_tolerance_V)
    mooseError("Grounded sheath energy collection is outside its W4.5 validity branch: phi_s = ",
               raw_phi_s_V,
               " V < 0 V. Electron-attracting/inverse sheath physics requires a separate owner.");

  const ADReal effective_drop_V = raw_phi_s_V < 0.0 ? ADReal(0.0) : phi_s_V;
  const ADReal electron_temperature_eV = electronTemperatureEV(mean_energy_eV);
  const ADReal primary_particle_flux =
      primaryParticleFluxHat(electron_density, mean_energy_eV, effective_drop_V);
  const ADReal energy_per_collected_electron_eV =
      2.0 * electron_temperature_eV + effective_drop_V;

  if (_molar_energy_state)
    return primary_particle_flux * energy_per_collected_electron_eV;

  return primary_particle_flux * energy_per_collected_electron_eV / _energy_reference_eV;
}
