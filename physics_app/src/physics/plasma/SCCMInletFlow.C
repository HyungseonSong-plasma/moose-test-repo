#include "SCCMInletFlow.h"

#include <cmath>
#include <set>
#include <stdexcept>

namespace Plasma
{
namespace
{
constexpr double GAS_CONSTANT = 8.31446261815324; // J/(mol K)

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
  std::set<std::string> ids;
  double inlet_sum = 0.0;
  double inverse_molar_mass = 0.0;
  for (const auto & item : species)
  {
    if (item.id.empty() || !ids.emplace(item.id).second)
      throw std::invalid_argument("inlet species IDs must be nonempty and unique");
    requirePositiveFinite(item.molar_mass_kg_per_mol, "species molar mass");
    if (!std::isfinite(item.inlet_mass_fraction) ||
        item.inlet_mass_fraction < 0.0 || item.inlet_mass_fraction > 1.0)
      throw std::invalid_argument("inlet species mass fraction must be in [0,1]");
    inlet_sum += item.inlet_mass_fraction;
    inverse_molar_mass += item.inlet_mass_fraction / item.molar_mass_kg_per_mol;
  }
  if (!std::isfinite(inlet_sum) || std::abs(inlet_sum - 1.0) > 1.0e-8)
    throw std::invalid_argument("inlet heavy mass fractions must sum to 1");
  requirePositiveFinite(inverse_molar_mass, "inverse inlet mixture molar mass");

  const double mean_molar_mass = 1.0 / inverse_molar_mass;
  const double q_std_m3_per_s = settings.sccm * 1.0e-6 / 60.0;
  const double inlet_mdot = q_std_m3_per_s * mean_molar_mass /
                            settings.standard_molar_volume_m3_per_mol;
  const double inlet_rho = settings.inlet_pressure_pa * mean_molar_mass /
                           (GAS_CONSTANT * settings.inlet_temperature_k);
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
