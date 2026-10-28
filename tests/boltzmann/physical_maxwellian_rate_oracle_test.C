#include "PhysicsBoltzmannGrowth.h"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace PhysicsBoltzmann;

namespace
{
constexpr double qe = 1.602176634e-19;
constexpr double me = 9.1093837139e-31;
constexpr double kb = 1.380649e-23;
constexpr double pi = 3.14159265358979323846264338327950288;
constexpr double gamma = 592969.320;
const double theta = kb * 3000.0 / qe;

// Independently normalized continuous Maxwellian EEPF at finite Emax:
//   f0(epsilon) = C * exp(-epsilon/theta)
//   C^-1 = theta^(3/2) * [sqrt(pi)/2 erf(sqrt(E/theta))
//                         - sqrt(E/theta) exp(-E/theta)]
double continuousNormalization(double emax)
{
  const double z = std::sqrt(emax / theta);
  return std::pow(theta, 1.5) *
         (0.5 * std::sqrt(pi) * std::erf(z) - z * std::exp(-z*z));
}

// Independent exact constant-cross-section Maxwellian rate integral:
//   k = sqrt(2 e/m_e) sigma C integral_threshold^Emax
//       epsilon exp(-epsilon/theta) d epsilon
double exactConstantCrossSectionRate(double sigma, double threshold, double emax)
{
  const double integral = theta *
      ((threshold + theta) * std::exp(-threshold/theta) -
       (emax + theta) * std::exp(-emax/theta));
  return std::sqrt(2.0 * qe / me) * sigma * integral /
         continuousNormalization(emax);
}

ElasticInput fourGasFixture(std::size_t cells)
{
  ElasticInput input;
  input.cells = cells;
  input.max_energy_eV = 4.0;
  input.gas_temperature_K = 3000.0;
  input.reduced_field_Td = 0.0;
  // Official example 4 composition, but entirely MANUFACTURED process
  // cross sections and gas temperature. This is NOT a real gas oracle.
  for (const auto & entry : std::vector<std::pair<const char*, double>>{
      {"Ar", 0.70}, {"He", 0.20}, {"N2", 0.08}, {"O2", 0.02}})
  {
    input.targets.push_back({entry.first, entry.second, 1.37e-5,
                             {0.0, 4.0}, {5e-20, 5e-20}});
  }
  return input;
}

ElasticResult manufacturedMaxwellian(const ElasticInput & input)
{
  ElasticResult f;
  const double h = input.max_energy_eV / input.cells;
  double mass = 0.0;
  for (std::size_t i = 0; i < input.cells; ++i)
  {
    const double lo = i*h, hi = (i+1)*h;
    const double center = (i+0.5)*h;
    const double value = std::exp(-center/theta);
    mass += value * (2.0/3.0) *
            (std::pow(hi,1.5)-std::pow(lo,1.5));
    f.energy_eV.push_back(center);
    f.eepf_eV_minus_3_halves.push_back(value);
  }
  f.mean_energy_eV = 0.0;
  for (std::size_t i = 0; i < input.cells; ++i)
  {
    const double lo = i*h, hi = (i+1)*h;
    auto & value = f.eepf_eV_minus_3_halves[i];
    value /= mass;
    f.mean_energy_eV += value * (2.0/5.0) *
                        (std::pow(hi,2.5)-std::pow(lo,2.5));
  }
  f.normalization = 1.0;
  return f;
}

double relative(double computed, double expected)
{
  return std::abs(computed - expected) / expected;
}
} // namespace

int main()
{
  const IonizationChannel ion{
      "synthetic_Ar_ionization", "Ar", 0.35, {0.0, 4.0}, {2e-20, 2e-20}};
  const AttachmentChannel attachment{
      "synthetic_O2_attachment", "O2", {0.0, 4.0}, {0.4e-20, 0.4e-20}};

  const double reference_ion =
      exactConstantCrossSectionRate(2e-20, 0.35, 4.0);
  const double reference_att =
      exactConstantCrossSectionRate(0.4e-20, 0.0, 4.0);
  const double reference_growth = 0.70*reference_ion - 0.02*reference_att;
  const double reference_energy_loss = 0.70*0.35*reference_ion;
  double previous_ion_error = 1.0, previous_attachment_error = 1.0;
  double finest_ion_error = 1.0, finest_attachment_error = 1.0;

  for (const std::size_t cells : {50u, 100u, 200u, 400u})
  {
    const auto input = fourGasFixture(cells);
    const auto manufactured = manufacturedMaxwellian(input);
    const auto result = evaluateGrowthOnFrozenEepf(
        input, manufactured, {ion}, {attachment});
    const double rate_ion = result.ionization_rates_m3_per_s.at(0);
    const double rate_att = result.attachment_rates_m3_per_s.at(0);
    const double ion_error = relative(rate_ion, reference_ion);
    const double attachment_error = relative(rate_att, reference_att);
    if (!(ion_error < 0.01 && attachment_error < 0.01 &&
          ion_error < previous_ion_error &&
          attachment_error < previous_attachment_error))
      throw std::runtime_error(
          "Boltzmann SCIENCE: Maxwellian analytic rate/grid convergence failed");
    if (relative(result.reduced_temporal_growth_m3_per_s,
                 reference_growth) > 0.01 ||
        relative(result.reduced_ionization_energy_loss_eV_m3_per_s,
                 reference_energy_loss) > 0.01 ||
        result.operator_number_balance_relative_error > 1e-10)
      throw std::runtime_error(
          "Boltzmann SCIENCE: independent four-gas growth/energy-number budget failed");
    previous_ion_error = ion_error;
    previous_attachment_error = attachment_error;
    finest_ion_error = ion_error;
    finest_attachment_error = attachment_error;
  }
  if (!(finest_ion_error < 1e-4 && finest_attachment_error < 1e-4))
    throw std::runtime_error(
        "Boltzmann SCIENCE: analytic Maxwellian rate convergence too weak");
  std::cout << "BOLTZMANN_SCIENCE_ANALYTIC_RATE_PASS\n"
            << "MODE=MANUFACTURED_MAXWELLIAN_NOT_BOLSIG_ORACLE\n"
            << "AR_ION_RATE_REFERENCE_M3_PER_S=" << reference_ion << '\n'
            << "O2_ATTACHMENT_REFERENCE_M3_PER_S=" << reference_att << '\n'
            << "FOUR_GAS_REDUCED_GROWTH_M3_PER_S=" << reference_growth << '\n'
            << "FOUR_GAS_REDUCED_ENERGY_LOSS_EV_M3_PER_S=" << reference_energy_loss << '\n'
            << "ION_RELATIVE_ERROR_400=" << finest_ion_error << '\n'
            << "ATT_RELATIVE_ERROR_400=" << finest_attachment_error << '\n';
}
