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
      "Applies the grounded-conductor primary-electron collection law using the "
      "plasma-side FV state with a differentiable Newton-globalization extension near phi=0.");
  params.addRequiredParam<MooseFunctorName>("mean_electron_energy", "Plasma-side electron mean energy [eV].");
  params.addRequiredParam<MooseFunctorName>("potential", "Plasma potential [V].");
  params.addParam<bool>("log_molar_state", false, "Interpret solved variable as log molar density.");
  return params;
}

PhysicsFVElectronGroundedSheathCollectionBC::PhysicsFVElectronGroundedSheathCollectionBC(const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _potential(getFunctor<ADReal>("potential")),
    _log_molar_state(getParam<bool>("log_molar_state"))
{
}

ADReal
PhysicsFVElectronGroundedSheathCollectionBC::computeQpResidual()
{
  const auto cell = _face_type == FaceInfo::VarFaceNeighbors::ELEM ? elemArg() : neighborArg();
  const auto state = determineState();
  const ADReal solved_state = uOnUSub();
  const ADReal mean_energy_eV = _mean_electron_energy(cell, state);
  const ADReal phi_s_V = _potential(cell, state);

  if (!_log_molar_state && MetaPhysicL::raw_value(solved_state) < 0.0)
    mooseError("Grounded sheath collection requires electron density >= 0.");
  if (MetaPhysicL::raw_value(mean_energy_eV) <= 0.0)
    mooseError("Grounded sheath collection requires mean electron energy > 0 eV.");

  const ADReal effective_drop_V = PhysicsGroundedElectronSheath::smoothPositiveDropV(phi_s_V);
  if (!_log_molar_state)
    return PhysicsGroundedElectronSheath::primaryParticleFluxHat(solved_state, mean_energy_eV, effective_drop_V);

  using std::exp;
  const ADReal physical_density = avogadro_per_mol * exp(solved_state);
  return PhysicsGroundedElectronSheath::primaryParticleFluxHat(physical_density, mean_energy_eV, effective_drop_V) / avogadro_per_mol;
}
