#include "SCCMInletFlow.h"
#include "IdealGasMixtureState.h"

#include <cmath>
#include <stdexcept>

namespace Plasma
{
namespace
{

void
requirePositiveFinite(const double value, const char * name)
{
  if (!(std::isfinite(value) && value > 0.0))
    throw std::invalid_argument(std::string(name) + " must be finite and strictly positive");
}
} // namespace

std::map<std::string, double>
SCCMInletFlow::calculate(const SCCMFeedSettings & settings,
                         const std::vector<SCCMFeedSpecies> & species)
{
  requirePositiveFinite(settings.sccm, "sccm");
  requirePositiveFinite(settings.inlet_area_m2, "inlet_area");
  requirePositiveFinite(settings.standard_molar_volume_m3_per_mol, "standard_molar_volume");
  requirePositiveFinite(settings.inlet_pressure_pa, "pressure");
  requirePositiveFinite(settings.inlet_temperature_k, "temperature");
  if (species.empty())
    throw std::invalid_argument("inlet feed requires at least one heavy species");

  // Identical standard-volume convention and species-flux splitting as
  // historical Issue #19 / #21 .i implementations. The independent
  // Chemistry JSON supplies inlet Y_i and molar masses.
  std::vector<IdealGasMixtureSpecies> inlet_components;
  inlet_components.reserve(species.size());
  for (const auto & item : species)
    inlet_components.push_back(
        {item.id, item.inlet_mass_fraction, item.molar_mass_kg_per_mol});
  const auto state = IdealGasMixtureState::evaluate(
      settings.inlet_pressure_pa, settings.inlet_temperature_k, inlet_components);
  const double mean_molar_mass = state.molar_mass_kg_per_mol;
  const double q_std_m3_per_s = settings.sccm * 1.0e-6 / 60.0;
  const double inlet_mdot = q_std_m3_per_s * mean_molar_mass /
                            settings.standard_molar_volume_m3_per_mol;
  const double inlet_rho = state.density_kg_per_m3;
  const double inlet_flux = inlet_mdot / settings.inlet_area_m2;
  const double inlet_speed = inlet_flux / inlet_rho;
  requirePositiveFinite(mean_molar_mass, "inlet mixture molar mass");
  requirePositiveFinite(inlet_mdot, "inlet mass flow");
  requirePositiveFinite(inlet_rho, "inlet density");
  requirePositiveFinite(inlet_flux, "inlet mass flux");
  requirePositiveFinite(inlet_speed, "inlet speed magnitude");

  std::map<std::string, double> outputs = {
      {"plasma_inlet_mdot", inlet_mdot},
      {"plasma_inlet_area", settings.inlet_area_m2},
      {"plasma_inlet_rho", inlet_rho},
      {"plasma_inlet_mass_flux", inlet_flux},
      {"plasma_inlet_speed", inlet_speed}};
  for (const auto & item : species)
  {
    const double mdot_i = inlet_mdot * item.inlet_mass_fraction;
    if (!std::isfinite(mdot_i) || mdot_i < 0.0)
      throw std::invalid_argument("species inlet mass flow is invalid");
    outputs.emplace("plasma_inlet_Y_" + item.id, item.inlet_mass_fraction);
    outputs.emplace("plasma_inlet_mdot_" + item.id, mdot_i);
  }
  return outputs;
}
} // namespace Plasma
