#include "PhysicsFVElectronGroundedSheathEnergyBC.h"
#include "PhysicsGroundedElectronSheathFlux.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVElectronGroundedSheathEnergyBC);

InputParameters
PhysicsFVElectronGroundedSheathEnergyBC::validParams()
{
  auto params = FVQpFluxBC::validParams();
  params.addClassDescription(
      "Applies grounded-conductor sheath-edge electron energy loss with (5/2) T_e + Delta phi. "
      "Optional wall-subgrid mode uses the same unresolved 1D particle drift-diffusion closure "
      "as the primary-electron collection BC before multiplying by the sheath energy per electron.");
  params.addRequiredParam<MooseFunctorName>("electron_density", "Plasma-side electron density.");
  params.addRequiredParam<MooseFunctorName>("mean_electron_energy", "Plasma-side electron mean energy [eV].");
  params.addRequiredParam<MooseFunctorName>("potential", "Plasma potential [V].");
  params.addParam<MooseFunctorName>("mobility", "Electron particle mobility for optional wall subgrid closure [m^2/(V s)].");
  params.addParam<MooseFunctorName>("diffusion", "Electron particle diffusion for optional wall subgrid closure [m^2/s].");
  params.addParam<Real>("energy_reference_eV", 1.0, "Legacy normalization energy [eV].");
  params.addParam<bool>("molar_energy_state", false, "Return conservative molar-energy flux.");
  params.addParam<bool>("physical_eV_state", false, "Return physical eV/(m^2 s) flux.");
  params.addParam<bool>(
      "apply_sheath_suppression",
      true,
      "Multiply the thermal primary-electron wall flux by exp(-Delta phi/T_e). Set false "
      "only for diagnostic comparison without the sheath suppression factor.");
  params.addParam<bool>(
      "use_wall_subgrid_closure",
      false,
      "Use the same analytic 1D constant-coefficient particle drift-diffusion closure as the "
      "electron particle wall BC, then multiply that flux by the sheath energy per electron.");
  params.addParam<Real>("charge_number", -1.0, "Signed electron charge number used by the wall subgrid drift velocity.");
  return params;
}

PhysicsFVElectronGroundedSheathEnergyBC::PhysicsFVElectronGroundedSheathEnergyBC(
    const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(isParamValid("mobility") ? &getFunctor<ADReal>("mobility") : nullptr),
    _diffusion(isParamValid("diffusion") ? &getFunctor<ADReal>("diffusion") : nullptr),
    _energy_reference_eV(getParam<Real>("energy_reference_eV")),
    _molar_energy_state(getParam<bool>("molar_energy_state")),
    _physical_eV_state(getParam<bool>("physical_eV_state")),
    _apply_sheath_suppression(getParam<bool>("apply_sheath_suppression")),
    _use_wall_subgrid_closure(getParam<bool>("use_wall_subgrid_closure")),
    _charge_number(getParam<Real>("charge_number"))
{
  if (_molar_energy_state && _physical_eV_state)
    paramError("physical_eV_state", "molar_energy_state and physical_eV_state are mutually exclusive.");
  if (!_molar_energy_state && !_physical_eV_state && !parameters.isParamSetByUser("energy_reference_eV"))
    paramError("energy_reference_eV", "Legacy normalized-energy mode requires energy_reference_eV.");
  if (!_molar_energy_state && !_physical_eV_state && _energy_reference_eV <= 0.0)
    paramError("energy_reference_eV", "Electron-energy normalization scale must be positive.");

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

  const auto collection_speed = [&]() -> ADReal
  {
    ADReal alpha = 0.25 * PhysicsGroundedElectronSheath::meanSpeedMPerS(electron_temperature_eV);
    if (_apply_sheath_suppression)
      alpha *= PhysicsGroundedElectronSheath::suppression(effective_drop_V, electron_temperature_eV);
    return alpha;
  };

  ADReal primary_particle_flux;
  if (_use_wall_subgrid_closure)
  {
    using std::exp;
    const ADReal mu = (*_mobility)(cell, state);
    const ADReal D = (*_diffusion)(cell, state);
    if (MetaPhysicL::raw_value(D) <= 0.0)
      mooseError("Energy wall subgrid closure requires diffusion > 0.");

    const ADRealVectorValue electric_field = -_potential.gradient(cell, state);
    const ADReal v_out = _charge_number * mu * (electric_field * _normal);

    const Point & center = _face_type == FaceInfo::VarFaceNeighbors::ELEM
                               ? _face_info->elemCentroid()
                               : _face_info->neighborCentroid();
    const Real wall_distance = std::abs(MetaPhysicL::raw_value(
        (_face_info->faceCentroid() - center) * _normal));
    if (wall_distance <= 0.0)
      mooseError("Energy wall subgrid closure requires positive centroid-to-wall normal distance.");

    const ADReal alpha = collection_speed();
    if (std::abs(MetaPhysicL::raw_value(v_out)) < 1.0e-12)
      primary_particle_flux = alpha * electron_density / (1.0 + alpha * wall_distance / D);
    else
    {
      const ADReal Pe = v_out * wall_distance / D;
      const ADReal exp_Pe = exp(Pe);
      primary_particle_flux = alpha * electron_density * exp_Pe /
                              (1.0 + (alpha / v_out) * (exp_Pe - 1.0));
    }
  }
  else
  {
    primary_particle_flux =
        _apply_sheath_suppression
            ? PhysicsGroundedElectronSheath::primaryParticleFluxHat(
                  electron_density, mean_energy_eV, effective_drop_V)
            : collection_speed() * electron_density;
  }

  const ADReal energy_per_collected_electron_eV =
      2.5 * electron_temperature_eV + effective_drop_V;

  if (_molar_energy_state || _physical_eV_state)
    return primary_particle_flux * energy_per_collected_electron_eV;

  return primary_particle_flux * energy_per_collected_electron_eV / _energy_reference_eV;
}
