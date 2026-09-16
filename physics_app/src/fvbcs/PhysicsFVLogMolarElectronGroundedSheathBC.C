#include "PhysicsFVLogMolarElectronGroundedSheathBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

#include "metaphysicl/raw_type.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronGroundedSheathBC);

InputParameters
PhysicsFVLogMolarElectronGroundedSheathBC::validParams()
{
  auto params = FVQpFluxBC::validParams();
  params.addClassDescription(
      "Applies the accepted grounded electron-repelling sheath collection law to "
      "c_e=exp(log_e), returning molar electron flux while log_e is solved.");
  params.addRequiredParam<MooseFunctorName>(
      "mean_electron_energy",
      "Plasma-side electron mean energy [eV]; T_e=(2/3)*mean energy.");
  params.addRequiredParam<MooseFunctorName>(
      "potential",
      "Plasma potential [V], evaluated on the plasma-side cell.");
  return params;
}

PhysicsFVLogMolarElectronGroundedSheathBC::PhysicsFVLogMolarElectronGroundedSheathBC(
    const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _potential(getFunctor<ADReal>("potential"))
{
}

ADReal
PhysicsFVLogMolarElectronGroundedSheathBC::computeQpResidual()
{
  using std::exp;

  const auto cell =
      _face_type == FaceInfo::VarFaceNeighbors::ELEM ? elemArg() : neighborArg();
  const auto state = determineState();

  const ADReal log_c_e = uOnUSub();
  const ADReal c_e_molar = exp(log_c_e);
  const ADReal mean_energy_eV = _mean_electron_energy(cell, state);
  const ADReal phi_s_V = _potential(cell, state);

  const Real raw_log_c_e = MetaPhysicL::raw_value(log_c_e);
  const Real raw_c_e_molar = MetaPhysicL::raw_value(c_e_molar);
  const Real raw_mean_energy_eV = MetaPhysicL::raw_value(mean_energy_eV);
  const Real raw_phi_s_V = MetaPhysicL::raw_value(phi_s_V);

  if (!std::isfinite(raw_log_c_e) || !std::isfinite(raw_c_e_molar) || raw_c_e_molar <= 0.0)
    mooseError("Log-molar sheath collection requires finite positive exp(log_e); log_e=",
               raw_log_c_e,
               ", c_e=",
               raw_c_e_molar,
               " mol/m^3.");
  if (raw_mean_energy_eV <= 0.0)
    mooseError("Log-molar sheath collection requires mean electron energy > 0 eV; got ",
               raw_mean_energy_eV);
  if (raw_phi_s_V < -PhysicsGroundedElectronSheath::negative_drop_tolerance_V)
    mooseError("Log-molar sheath collection is outside the grounded electron-repelling branch: phi_s = ",
               raw_phi_s_V,
               " V < 0 V. Electron-attracting/inverse sheath physics requires a separate owner.");

  const ADReal effective_drop_V = raw_phi_s_V < 0.0 ? ADReal(0.0) : phi_s_V;

  // PhysicsGroundedElectronSheath::primaryParticleFluxHat is linear in its
  // density argument. Supplying c_e [mol/m^3] therefore returns the same
  // accepted 1/4*v_th*exp(-DeltaPhi/Te) collection law in mol/(m^2 s).
  return PhysicsGroundedElectronSheath::primaryParticleFluxHat(
      c_e_molar, mean_energy_eV, effective_drop_V);
}
