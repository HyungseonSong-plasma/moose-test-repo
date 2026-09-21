#include "PhysicsFVElectronGroundedSheathCollectionBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVElectronGroundedSheathCollectionBC);

namespace
{
constexpr Real avogadro_per_mol = 6.02214076e23;
}

InputParameters
PhysicsFVElectronGroundedSheathCollectionBC::validParams()
{
  auto params = FVQpFluxBC::validParams();
  params.addClassDescription(
      "Applies the accepted grounded-conductor primary-electron collection law using the "
      "plasma-side FV state. T1 can reconstruct molar flux from a log-molar state.");
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
    mooseError("Grounded sheath collection requires mean electron energy > 0 eV; got ", raw_mean_energy_eV);
  if (raw_phi_s_V < -PhysicsGroundedElectronSheath::negative_drop_tolerance_V)
    mooseError("Grounded sheath collection is outside its accepted electron-repelling branch: phi_s = ", raw_phi_s_V);

  const ADReal effective_drop_V = raw_phi_s_V < 0.0 ? ADReal(0.0) : phi_s_V;
  if (!_log_molar_state)
    return PhysicsGroundedElectronSheath::primaryParticleFluxHat(
        solved_state, mean_energy_eV, effective_drop_V);

  using std::exp;
  const ADReal physical_density = avogadro_per_mol * exp(solved_state);
  return PhysicsGroundedElectronSheath::primaryParticleFluxHat(
             physical_density, mean_energy_eV, effective_drop_V) /
         avogadro_per_mol;
}
