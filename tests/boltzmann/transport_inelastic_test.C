#include "PhysicsBoltzmannTransport.h"

#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>

using namespace PhysicsBoltzmann;

namespace
{
ElasticInput makeInput(bool upper = false)
{
  ElasticInput input;
  input.cells = 300;
  input.max_energy_eV = 4.0;
  input.gas_temperature_K = 3000.0;
  input.reduced_field_Td = 0.0;
  input.targets.push_back({"lower", upper ? 0.9 : 1.0, 1.37e-5,
                           {0.0,4.0},{5e-20,5e-20}});
  if (upper)
    input.targets.push_back({"upper", 0.1, 1.37e-5,
                             {0.0,4.0},{5e-20,5e-20}});
  return input;
}
ExcitationChannel channel(double s, bool upper = false)
{
  ExcitationChannel ch{"excitation", "lower", 0.4,
                       {0.0,0.4,0.41,4.0},{0.0,0.0,s,s}};
  if (upper)
  {
    ch.upper_state_target_name = "upper";
    ch.upper_to_lower_weight_ratio = 2.0;
  }
  return ch;
}
double rel(double a, double b) { return std::abs(a-b) / std::abs(b); }
void reject(const std::function<void()> & fn)
{
  try { fn(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("M7b failed to reject invalid inelastic physics input");
}
} // namespace

int main()
{
  const auto input = makeInput();
  const auto eepf = solveElasticSteadyState(input);
  const auto baseline = evaluateElasticTransportMoments(input, eepf);
  const auto zero = evaluateExcitationTransportMoments(input, eepf, {channel(0.0)});
  if (!(rel(baseline.reduced_diffusion_N_per_m_s,
            zero.reduced_diffusion_N_per_m_s) < 1e-14 &&
        rel(baseline.reduced_mobility_N_per_m_V_s,
            zero.reduced_mobility_N_per_m_V_s) < 1e-14 &&
        rel(baseline.reduced_energy_mobility_N_per_m_V_s,
            zero.reduced_energy_mobility_N_per_m_V_s) < 1e-14 &&
        rel(baseline.reduced_energy_diffusion_N_per_m_s,
            zero.reduced_energy_diffusion_N_per_m_s) < 1e-14))
    throw std::runtime_error("M7b zero amplitude does not preserve M7a transport");

  const auto inelastic = evaluateExcitationTransportMoments(
      input, eepf, {channel(3e-20)});
  if (!(inelastic.reduced_diffusion_N_per_m_s <
        baseline.reduced_diffusion_N_per_m_s &&
        inelastic.reduced_energy_diffusion_N_per_m_s <
        baseline.reduced_energy_diffusion_N_per_m_s &&
        inelastic.reduced_mobility_N_per_m_V_s <
        baseline.reduced_mobility_N_per_m_V_s))
    throw std::runtime_error("M7b inelastic momentum relaxation did not reduce transport");

  const auto mix = makeInput(true);
  const auto mixed_eepf = solveElasticSteadyState(mix);
  const auto forward = evaluateExcitationTransportMoments(
      mix, mixed_eepf, {channel(2e-20)});
  const auto reverse = evaluateExcitationTransportMoments(
      mix, mixed_eepf, {channel(2e-20, true)});
  if (!(reverse.reduced_diffusion_N_per_m_s <
        forward.reduced_diffusion_N_per_m_s &&
        reverse.reduced_energy_diffusion_N_per_m_s <
        forward.reduced_energy_diffusion_N_per_m_s))
    throw std::runtime_error("M7b superelastic momentum transfer was omitted");

  auto wrong = channel(2e-20, true);
  wrong.upper_state_target_name = "missing";
  reject([&] { (void)evaluateExcitationTransportMoments(mix, mixed_eepf, {wrong}); });
  wrong = channel(2e-20, true);
  wrong.upper_to_lower_weight_ratio = -1.0;
  reject([&] { (void)evaluateExcitationTransportMoments(mix, mixed_eepf, {wrong}); });
  wrong = channel(2e-20);
  wrong.cross_section_m2.back() = -1.0;
  reject([&] { (void)evaluateExcitationTransportMoments(input, eepf, {wrong}); });
  std::cout << "BOLTZMANN_TRANSPORT_M7B_P0_P1_PASS\n"
            << "M7B_ELASTIC_DIFFUSION=" << baseline.reduced_diffusion_N_per_m_s << '\n'
            << "M7B_EXCITATION_DIFFUSION=" << inelastic.reduced_diffusion_N_per_m_s << '\n'
            << "M7B_SUPERELASTIC_DIFFUSION=" << reverse.reduced_diffusion_N_per_m_s << '\n';
}
