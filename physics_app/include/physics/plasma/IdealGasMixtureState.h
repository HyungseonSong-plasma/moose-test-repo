#pragma once

#include <string>
#include <vector>

namespace Plasma
{
struct IdealGasMixtureSpecies
{
  std::string id;
  double mass_fraction;
  double molar_mass_kg_per_mol;
};

struct IdealGasMixtureValues
{
  double molar_mass_kg_per_mol;
  double density_kg_per_m3;
  double number_density_per_m3;
};

// Setup-only ideal-gas state of an explicitly frozen mixture. The canonical
// live rho_g/M_mix use AD Functors of solved Y_i and are NOT evaluated here.
class IdealGasMixtureState
{
public:
  static IdealGasMixtureValues
  evaluate(double pressure_pa, double temperature_k,
           const std::vector<IdealGasMixtureSpecies> & species);
};
} // namespace Plasma
