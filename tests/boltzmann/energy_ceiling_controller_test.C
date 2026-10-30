// First-party manufactured numerical fixtures only. No LXCat or BOLSIG+
// output is bundled. This tests the actual C++ elastic re-solve and the
// generic P0-1 convergence controller; it is NOT physical parity.
#include "PhysicsBoltzmannEnergyCeiling.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace PhysicsBoltzmann;

namespace
{
void require(bool ok, const std::string & reason)
{
  if (!ok) throw std::runtime_error(reason);
}

void rejects(const std::function<void()> & fn)
{
  try { fn(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("expected invalid energy-ceiling input rejection");
}

// Synthetic exactly normalized piecewise-constant exp(-E/T) EEPF.
// Rate is an invented threshold-weighted moment; not a physical cross section.
EnergyCeilingSample manufactured(double emax, double temperature = 1.0,
                                 bool monitor_rate = true)
{
  const std::size_t n = static_cast<std::size_t>(std::ceil(emax * 50.0));
  EnergyCeilingSample sample;
  auto & d = sample.distribution;
  d.energy_cell_edges_eV.resize(n + 1);
  d.energy_eV.resize(n);
  d.eepf_eV_minus_3_halves.resize(n);
  double mass = 0.0, moment = 0.0, rate = 0.0;
  for (std::size_t i = 0; i <= n; ++i)
    d.energy_cell_edges_eV[i] = emax * static_cast<double>(i) / n;
  for (std::size_t i = 0; i < n; ++i)
  {
    const double l = d.energy_cell_edges_eV[i], r = d.energy_cell_edges_eV[i + 1];
    const double e = 0.5 * (l + r);
    const double f = std::exp(-e / temperature);
    const double m = (2.0 / 3.0) * (std::pow(r, 1.5) - std::pow(l, 1.5));
    const double w = (2.0 / 5.0) * (std::pow(r, 2.5) - std::pow(l, 2.5));
    d.energy_eV[i] = e;
    d.eepf_eV_minus_3_halves[i] = f;
    mass += f * m;
    moment += f * w;
    rate += f * m * e * std::max(0.0, e - 1.5);
  }
  for (auto & v : d.eepf_eV_minus_3_halves)
    v /= mass;
  d.normalization = 1.0;
  d.mean_energy_eV = moment / mass;
  if (monitor_rate)
    sample.rates_m3_per_s = {rate / mass * 1e-15};
  return sample;
}
} // namespace

int main()
{
  EnergyCeilingControls c;
  c.maximum_energy_eV = 96.0;
  c.expansion_factor = 2.0;
  c.max_expansions = 6;
  c.required_stable_expansions = 2;
  c.tail_mass_limit = 1e-7;
  c.tail_energy_limit = 1e-6;
  c.moment_relative_limit = 1e-3;
  c.rate_relative_limit = 1e-3;

  const auto selected = selectEnergyCeiling(3.0, c, [](double e) {
    return manufactured(e);
  });
  require(selected.converged && selected.history.size() >= 4 &&
          selected.history.back().rates_monitored &&
          selected.history.back().stable &&
          selected.history.back().tail_number_fraction <= c.tail_mass_limit &&
          selected.history.back().tail_energy_fraction <= c.tail_energy_limit,
          "manufactured tail/rate/mean controller did not converge");
  require(selected.history.front().energy_ceiling_eV == 3.0 &&
          selected.history.back().energy_ceiling_eV > 3.0,
          "controller reused the initial energy ceiling");
  require(selected.status == "CONVERGED_MONITORED_RATES_SCIENCE_HOLD",
          "controller mislabeled manufactured rate convergence");

  // A very small final-cell ionization window (15.8–15.8367 eV) must NOT
  // be declared resolved merely because the total EEPF tail is negligible.
  EnergyCeilingControls near_threshold = c;
  near_threshold.maximum_energy_eV = 18.0;
  near_threshold.expansion_factor = 1.1;
  near_threshold.max_expansions = 3;
  near_threshold.required_stable_expansions = 1;
  near_threshold.required_thresholds_eV = {15.8};
  const auto threshold = selectEnergyCeiling(15.8367, near_threshold,
      [](double e) { return manufactured(e, 0.8); });
  require(threshold.converged && threshold.history.size() >= 2 &&
          !threshold.history.front().threshold_resolved &&
          threshold.history.back().threshold_resolved,
          "15.8 eV near-ceiling threshold guard was bypassed");

  EnergyCeilingControls limited = c;
  limited.maximum_energy_eV = 4.0;
  limited.tail_mass_limit = 1e-12;
  limited.tail_energy_limit = 1e-12;
  const auto held = selectEnergyCeiling(3.0, limited,
      [](double e) { return manufactured(e); });
  require(!held.converged && held.status == "HOLD_MAX_ENERGY_LIMIT" &&
          held.history.size() == 2,
          "unresolved high-energy tail was silently accepted");

  rejects([&] {
    (void)selectEnergyCeiling(3.0, c, [](double e) {
      auto s = manufactured(e);
      s.distribution.eepf_eV_minus_3_halves[0] *= 2.0;
      return s;
    });
  });
  rejects([&] {
    (void)selectEnergyCeiling(3.0, c, [](double e) {
      auto s = manufactured(e);
      s.distribution.eepf_eV_minus_3_halves[0] = -1.0;
      return s;
    });
  });
  rejects([&] {
    (void)selectEnergyCeiling(3.0, c, [](double e) {
      return manufactured(e, 1.0, e > 3.0);
    });
  });
  rejects([&] {
    EnergyCeilingControls invalid = c;
    invalid.expansion_factor = 1.0;
    (void)selectEnergyCeiling(3.0, invalid,
        [](double e) { return manufactured(e); });
  });

  // The real, independently compiled C++ SG elastic solver is re-run at
  // increasing Emax with fixed nominal cell width. Invented constant sigma.
  ElasticInput elastic;
  elastic.reduced_field_Td = 0.2;
  elastic.gas_temperature_K = 300.0;
  elastic.max_energy_eV = 4.0;
  elastic.cells = 120;
  elastic.targets = {
      {"synthetic-neutral", 1.0, 1.37e-5, {0.0, 32.0}, {5e-20, 5e-20}}};
  EnergyCeilingControls elastic_controls = c;
  elastic_controls.maximum_energy_eV = 32.0;
  elastic_controls.max_expansions = 3;
  elastic_controls.tail_mass_limit = 1e-5;
  elastic_controls.tail_energy_limit = 1e-4;
  elastic_controls.moment_relative_limit = 2e-3;
  const auto real_solver = solveElasticWithAutomaticCeiling(elastic, elastic_controls);
  require(real_solver.converged &&
          real_solver.history.back().cells > elastic.cells &&
          real_solver.status ==
              "CONVERGED_MOMENTS_ONLY_RATES_NOT_MONITORED_SCIENCE_HOLD",
          "real C++ elastic re-solve failed convergence or mislabeled rate monitor");
  rejects([&] {
    ElasticInput bad = elastic;
    bad.energy_cell_edges_eV.resize(bad.cells + 1, 0.0);
    (void)solveElasticWithAutomaticCeiling(bad, elastic_controls);
  });
  rejects([&] {
    EnergyCeilingControls out_of_domain = elastic_controls;
    out_of_domain.maximum_energy_eV = 64.0;
    (void)solveElasticWithAutomaticCeiling(elastic, out_of_domain);
  });

  std::cout << "P0-1 synthetic monitored rate converged at "
            << selected.history.back().energy_ceiling_eV
            << " eV; threshold guard cleared at "
            << threshold.history.back().energy_ceiling_eV
            << " eV; real elastic solver converged at "
            << real_solver.history.back().energy_ceiling_eV
            << " eV (" << real_solver.history.back().cells
            << " cells); insufficient tail remains HOLD\n";
  return 0;
}
