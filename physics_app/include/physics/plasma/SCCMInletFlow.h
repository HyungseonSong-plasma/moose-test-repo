#pragma once

#include <map>
#include <string>
#include <vector>

namespace Plasma
{
// Immutable settings for a steady, standard-volume feed. Physical inlet area
// is supplied explicitly; this model does not infer boundary geometry.
struct SCCMFeedSettings
{
  double sccm;
  double inlet_area_m2;
  double standard_molar_volume_m3_per_mol;
  double inlet_pressure_pa;
  double inlet_temperature_k;
};

struct SCCMFeedSpecies
{
  std::string id;
  double inlet_mass_fraction;
  double molar_mass_kg_per_mol;
};

// Pure C++ mapping: does not depend on MOOSE, a solver state, or Functors.
// For a fixed feed, call once during input setup, then publish resulting
// numbers through existing ConstantPostprocessors and WCNS boundary owners.
class SCCMInletFlow
{
public:
  static std::map<std::string, double>
  calculate(const SCCMFeedSettings & settings, const std::vector<SCCMFeedSpecies> & species);
};
} // namespace Plasma
