#pragma once

#include <cstddef>
#include <string>
#include <vector>

// Standalone (MOOSE-independent) zero-dimensional, steady, two-term electron
// Boltzmann energy-space solver. M1 covers *elastic* electron-neutral collisions
// and a uniform DC reduced field only. Not a complete BOLSIG+ replacement.
namespace PhysicsBoltzmann
{
struct ElasticTarget
{
  std::string name;
  double mole_fraction = 0.0;  // number fraction, dimensionless
  double electron_mass_ratio = 0.0; // m_e/M_target, dimensionless
  std::vector<double> energy_eV;     // tabulated collision energy, eV
  std::vector<double> momentum_transfer_m2; // elastic momentum transfer cross section, m^2
};

struct ElasticInput
{
  double reduced_field_Td = 0.0; // E/N, 1 Td = 1e-21 V m^2
  double gas_temperature_K = 300.0;
  double max_energy_eV = 10.0;
  std::size_t cells = 400;
  std::vector<ElasticTarget> targets;
};

struct ElasticResult
{
  std::vector<double> energy_eV; // energy cell centers
  std::vector<double> eepf_eV_minus_3_halves; // f0: integral(sqrt(e)*f0 de)=1
  double mean_energy_eV = 0.0;
  double normalization = 0.0;
  double maximum_normalized_flux_residual = 0.0;
};

// Solves d/denergy [W f0 - D df0/denergy] = 0 with zero flux at both
// energy-space boundaries. Interior zero-flux exponential fitting yields the
// conservative discrete nullspace; one normalization then fixes its scale.
// No ionization, excitation, attachment, superelastic, electron-electron,
// electron-density growth, or RF/harmonic collision model is included.
ElasticResult solveElasticSteadyState(const ElasticInput & input);

struct ExcitationChannel
{
  std::string name;
  std::string target_name;     // identifier for an existing ElasticTarget
  double threshold_eV = 0.0;  // energy lost per excitation event
  std::vector<double> energy_eV;
  std::vector<double> cross_section_m2;
  // Optional inverse superelastic channel. Both lower and upper target
  // populations must have explicitly defined ELASTIC collision records
  // and number fractions in ElasticInput.targets.
  std::string upper_state_target_name;
  double upper_to_lower_weight_ratio = 1.0; // g_upper/g_lower (>0)
};

enum class ExcitationLinearMethod
{
  Auto,             // dense reference for <=512 cells, sparse above
  DenseReference,   // O(N^3), <=512 only: independent parity oracle
  SparseBiCGSTAB    // sparse O(N) storage with tridiagonal preconditioner
};

struct ExcitationResult
{
  ElasticResult distribution;
  std::vector<double> rate_coefficients_m3_per_s; // per channel / target molecule
  std::vector<double> energy_loss_coefficients_eV_m3_per_s; // forward u * k
  // Per-excited-target superelastic rate and net *mixture-weighted* loss;
  // reverse rate is zero for unidirectional excitation channels.
  std::vector<double> superelastic_rate_coefficients_m3_per_s;
  std::vector<double> net_energy_loss_coefficients_eV_m3_per_s;
  double maximum_normalized_equation_residual = 0.0;
  double maximum_collision_number_balance_error = 0.0;
  std::size_t assembled_nonzero_entries = 0;
  std::size_t linear_iterations = 0;
  ExcitationLinearMethod linear_method_used = ExcitationLinearMethod::DenseReference;
};

// DEVELOPMENT: steady excitation-only collision operator + elastic SG flux.
// Dense reference <=512 cells or sparse preconditioned BiCGSTAB up to 16384
// cells. Not coupled to production Physics.
ExcitationResult solveExcitationSteadyState(
    const ElasticInput & input,
    const std::vector<ExcitationChannel> & channels,
    ExcitationLinearMethod method = ExcitationLinearMethod::Auto);
}
