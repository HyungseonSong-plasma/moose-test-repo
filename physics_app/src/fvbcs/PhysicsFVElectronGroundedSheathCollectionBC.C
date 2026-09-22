#include "PhysicsFVElectronGroundedSheathCollectionBC.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVElectronGroundedSheathCollectionBC);

namespace
{
constexpr Real avogadro_per_mol = 6.02214076e23;
constexpr Real negative_drop_tolerance_V = 1.0e-10;
constexpr Real elementary_charge_C = 1.602176634e-19;
constexpr Real electron_mass_kg = 9.1093837139e-31;
constexpr Real pi = 3.141592653589793238462643383279502884;

ADReal
primaryParticleFluxHat(const ADReal & n_e_hat,
                       const ADReal & mean_energy_eV,
                       const ADReal & effective_drop_V)
{
  using std::exp;
  using std::sqrt;
  const ADReal electron_temperature_eV = (2.0 / 3.0) * mean_energy_eV;
  const ADReal mean_speed_m_s =
      sqrt(8.0 * elementary_charge_C * electron_temperature_eV /
           (pi * electron_mass_kg));
  return 0.25 * n_e_hat * mean_speed_m_s *
         exp(-effective_drop_V / electron_temperature_eV);
}
}

InputParameters
PhysicsFVElectronGroundedSheathCollectionBC::validParams()
{
  auto params = FVQpFluxBC::validParams();
  params.addClassDescription(
      "Legacy compatibility owner for the accepted grounded-conductor primary-electron "
      "collection law. New input decks should prefer ADParsedFunctorMaterial plus "
      "FVFunctorNeumannBC so the closure stays in standard MOOSE input syntax.");
  params.addRequiredParam<MooseFunctorName>(
      "mean_electron_energy",
      "Plasma-side electron mean energy [eV]. The sheath temperature is (2/3) mean energy.");
  params.addRequiredParam<MooseFunctorName>(
      "potential",
      "Plasma potential [V]. This object evaluates the plasma-side element value.");
  params.addParam<bool>(
      "log_molar_state", false,
      "If true, interpret the solved variable as log(c_e/[1 mol/m^3]) and return molar particle flux.");
  return params;
}

PhysicsFVElectronGroundedSheathCollectionBC::
    PhysicsFVElectronGroundedSheathCollectionBC(const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _potential(getFunctor<ADReal>("potential")),
    _log_molar_state(getParam<bool>("log_molar_state"))
{
}

ADReal
PhysicsFVElectronGroundedSheathCollectionBC::computeQpResidual()
{
  const auto cell =
      _face_type == FaceInfo::VarFaceNeighbors::ELEM ? elemArg() : neighborArg();
  const auto state = determineState();

  const ADReal solved_state = uOnUSub();
  const ADReal mean_energy_eV = _mean_electron_energy(cell, state);
  const ADReal phi_s_V = _potential(cell, state);

  const Real raw_mean_energy_eV = MetaPhysicL::raw_value(mean_energy_eV);
  const Real raw_phi_s_V = MetaPhysicL::raw_value(phi_s_V);
  if (!_log_molar_state && MetaPhysicL::raw_value(solved_state) < 0.0)
    mooseError("Grounded sheath collection requires normalized electron density >= 0.");
  if (raw_mean_energy_eV <= 0.0)
    mooseError("Grounded sheath collection requires mean electron energy > 0 eV; got ",
               raw_mean_energy_eV);
  if (raw_phi_s_V < -negative_drop_tolerance_V)
    mooseError("Grounded sheath collection is outside its accepted electron-repelling branch: phi_s = ",
               raw_phi_s_V);

  const ADReal effective_drop_V = raw_phi_s_V < 0.0 ? ADReal(0.0) : phi_s_V;
  if (!_log_molar_state)
    return primaryParticleFluxHat(solved_state, mean_energy_eV, effective_drop_V);

  using std::exp;
  const ADReal physical_density = avogadro_per_mol * exp(solved_state);
  return primaryParticleFluxHat(physical_density, mean_energy_eV, effective_drop_V) /
         avogadro_per_mol;
}
