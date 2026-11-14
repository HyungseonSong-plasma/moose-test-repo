#include "IdealGasMixtureState.h"

#include <cmath>
#include <set>
#include <stdexcept>

namespace Plasma
{
namespace
{
constexpr double GAS_CONSTANT = 8.31446261815324;
constexpr double BOLTZMANN_CONSTANT = 1.380649e-23;

void
positive(const double value, const char * label)
{
  if (!(std::isfinite(value) && value > 0.0))
    throw std::invalid_argument(std::string(label) + " must be finite and strictly positive");
}
} // namespace

IdealGasMixtureValues
IdealGasMixtureState::evaluate(
    const double pressure_pa,
    const double temperature_k,
    const std::vector<IdealGasMixtureSpecies> & species)
{
  positive(pressure_pa, "gas pressure");
  positive(temperature_k, "gas temperature");
  if (species.empty())
    throw std::invalid_argument("ideal-gas mixture requires at least one species");

  std::set<std::string> ids;
  double sum = 0.0;
  double inverse_molar_mass = 0.0;
  for (const auto & item : species)
  {
    if (item.id.empty() || !ids.insert(item.id).second)
      throw std::invalid_argument("mixture species IDs must be nonempty and unique");
    positive(item.molar_mass_kg_per_mol, "species molar mass");
    if (!std::isfinite(item.mass_fraction) || item.mass_fraction < 0.0 ||
        item.mass_fraction > 1.0)
      throw std::invalid_argument("mixture mass fraction must be finite and in [0,1]");
    sum += item.mass_fraction;
    inverse_molar_mass += item.mass_fraction / item.molar_mass_kg_per_mol;
  }
  if (!std::isfinite(sum) || std::abs(sum - 1.0) > 1e-8)
    throw std::invalid_argument("mixture mass fractions must sum to 1");
  positive(inverse_molar_mass, "inverse mean molar mass");
  const double molar_mass = 1.0 / inverse_molar_mass;
  const double density = pressure_pa * molar_mass / (GAS_CONSTANT * temperature_k);
  const double number_density = pressure_pa / (BOLTZMANN_CONSTANT * temperature_k);
  positive(molar_mass, "mixture molar mass");
  positive(density, "mixture density");
  positive(number_density, "mixture number density");
  return {molar_mass, density, number_density};
}
} // namespace Plasma
