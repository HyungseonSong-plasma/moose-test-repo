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
  params.addParam<MooseFunctorName>("mobility", "Electron mobility for optional wall subgrid closure [m^2/(V s)].");
  params.addParam<MooseFunctorName>("diffusion", "Electron diffusion for optional wall subgrid closure [m^2/s].");
  params.addParam<bool>("log_molar_state", false, "Interpret solved variable as log molar density.");
  params.addParam<bool>(
      "apply_sheath_suppression",
      true,
      "Multiply the thermal wall flux by exp(-Delta phi/T_e). Set false only for "
      "diagnostic comparison without the sheath suppression factor.");
  params.addParam<bool>(
      "use_wall_subgrid_closure",
      false,
      "Replace direct cell-state sheath collection by an analytic 1D constant-coefficient "
      "drift-diffusion closure between the FV cell centroid and wall face.");
  params.addParam<Real>("charge_number", -1.0, "Signed charge number used by the wall subgrid drift velocity.");
  return params;
}

PhysicsFVElectronGroundedSheathCollectionBC::PhysicsFVElectronGroundedSheathCollectionBC(const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(isParamValid("mobility") ? &getFunctor<ADReal>("mobility") : nullptr),
    _diffusion(isParamValid("diffusion") ? &getFunctor<ADReal>("diffusion") : nullptr),
    _log_molar_state(getParam<bool>("log_molar_state")),
    _apply_sheath_suppression(getParam<bool>("apply_sheath_suppression")),
    _use_wall_subgrid_closure(getParam<bool>("use_wall_subgrid_closure")),
    _charge_number(getParam<Real>("charge_number"))
{
  if (_use_wall_subgrid_closure)
  {
    if (!_mobility)
      paramError("mobility", "mobility is required when use_wall_subgrid_closure=true.");
    if (!_diffusion)
      paramError("diffusion", "diffusion is required when use_wall_subgrid_closure=true.");
    if (_charge_number == 0.0)
      paramError("charge_number", "wall subgrid closure requires nonzero charge_number.");
  }
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
  const ADReal electron_temperature_eV =
      PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy_eV);

  const auto collection_speed = [&]() -> ADReal
  {
    ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(electron_temperature_eV);
    if (_apply_sheath_suppression)
      alpha *= PhysicsGroundedElectronSheath::suppression(effective_drop_V, electron_temperature_eV);
    return alpha;
  };

  using std::exp;
  const ADReal density_state = _log_molar_state ? exp(solved_state) : solved_state;

  if (_use_wall_subgrid_closure)
  {
    const ADReal mu = (*_mobility)(cell, state);
    const ADReal D = (*_diffusion)(cell, state);
    if (MetaPhysicL::raw_value(D) <= 0.0)
      mooseError("Wall subgrid closure requires diffusion > 0.");

    const ADRealVectorValue electric_field = -_potential.gradient(cell, state);
    const ADReal v_out = _charge_number * mu * (electric_field * _normal);

    const Point & center = _face_type == FaceInfo::VarFaceNeighbors::ELEM
                               ? _face_info->elemCentroid()
                               : _face_info->neighborCentroid();
    const Real wall_distance =
        std::abs((_face_info->faceCentroid() - center) * _normal);
    if (wall_distance <= 0.0)
      mooseError("Wall subgrid closure requires positive centroid-to-wall normal distance.");

    const ADReal alpha = collection_speed();
    ADReal gamma;
    if (std::abs(MetaPhysicL::raw_value(v_out)) < 1.0e-12)
      gamma = alpha * density_state / (1.0 + alpha * wall_distance / D);
    else
    {
      const ADReal Pe = v_out * wall_distance / D;
      const ADReal exp_Pe = exp(Pe);
      gamma = alpha * density_state * exp_Pe /
              (1.0 + (alpha / v_out) * (exp_Pe - 1.0));
    }

    return gamma;
  }

  const ADReal gamma_direct = collection_speed() * density_state;
  return gamma_direct;
}
