#include "PhysicsFVElectronGroundedSheathCollectionBC.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVElectronGroundedSheathCollectionBC);

InputParameters
PhysicsFVElectronGroundedSheathCollectionBC::validParams()
{
  auto params = FVQpFluxBC::validParams();

  params.addClassDescription(
      "Applies the W3 grounded-conductor sheath-unresolved primary-electron collection "
      "law using the plasma-side FV state. Secondary emission is owned separately.");

  params.addRequiredParam<MooseFunctorName>(
      "mean_electron_energy",
      "Plasma-side electron mean energy [eV]. The sheath temperature is (2/3) mean energy.");
  params.addRequiredParam<MooseFunctorName>(
      "potential",
      "Plasma potential [V]. This object evaluates the plasma-side element value, not the "
      "grounded Dirichlet face value.");

  return params;
}

PhysicsFVElectronGroundedSheathCollectionBC::
    PhysicsFVElectronGroundedSheathCollectionBC(const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _potential(getFunctor<ADReal>("potential"))
{
}

ADReal
PhysicsFVElectronGroundedSheathCollectionBC::computeQpResidual()
{
  using std::exp;
  using std::sqrt;

  // W3 interprets the first plasma FV cell as the sheath edge.  A FaceArg
  // would evaluate a Dirichlet boundary value for potential and collapse the
  // grounded sheath drop to zero, so all sheath state is sampled on the
  // variable-owning plasma cell instead.
  const auto cell =
      _face_type == FaceInfo::VarFaceNeighbors::ELEM ? elemArg() : neighborArg();
  const auto state = determineState();

  const ADReal n_e_hat = uOnUSub();
  const ADReal mean_energy_eV = _mean_electron_energy(cell, state);
  const ADReal phi_s_V = _potential(cell, state);

  const Real raw_n_e_hat = MetaPhysicL::raw_value(n_e_hat);
  const Real raw_mean_energy_eV = MetaPhysicL::raw_value(mean_energy_eV);
  const Real raw_phi_s_V = MetaPhysicL::raw_value(phi_s_V);

  if (raw_n_e_hat < 0.0)
    mooseError("Grounded sheath collection requires normalized electron density >= 0; got ",
               raw_n_e_hat);
  if (raw_mean_energy_eV <= 0.0)
    mooseError("Grounded sheath collection requires mean electron energy > 0 eV; got ",
               raw_mean_energy_eV);

  // The accepted W3 scope is the classical electron-repelling sheath.  Allow
  // only roundoff-sized negative trial values; a materially attracting/inverse
  // sheath is a different model branch and must not be silently extended here.
  constexpr Real negative_drop_tolerance_V = 1.0e-10;
  if (raw_phi_s_V < -negative_drop_tolerance_V)
    mooseError("Grounded sheath collection is outside its W3 validity branch: phi_s = ",
               raw_phi_s_V,
               " V < 0 V. Electron-attracting/inverse sheath physics requires a separate owner.");

  const ADReal effective_drop_V = raw_phi_s_V < 0.0 ? ADReal(0.0) : phi_s_V;
  const ADReal electron_temperature_eV = (2.0 / 3.0) * mean_energy_eV;

  constexpr Real elementary_charge_C = 1.602176634e-19;
  constexpr Real electron_mass_kg = 9.1093837139e-31;
  constexpr Real pi = 3.141592653589793238462643383279502884;

  const ADReal mean_speed_m_s =
      sqrt(8.0 * elementary_charge_C * electron_temperature_eV / (pi * electron_mass_kg));
  const ADReal suppression = exp(-effective_drop_V / electron_temperature_eV);

  // n_e is normalized by n_ref, so Gamma_e,out / n_ref has units of m/s.
  // FVQpFluxBC positive residual is outward loss.
  return 0.25 * n_e_hat * mean_speed_m_s * suppression;
}
