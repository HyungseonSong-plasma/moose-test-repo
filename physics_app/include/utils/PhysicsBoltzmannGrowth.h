#pragma once

#include "PhysicsBoltzmannElasticSolver.h"

#include <cstddef>
#include <string>
#include <vector>

namespace PhysicsBoltzmann
{
// M6a particle-changing channels. All cross sections are input data with
// explicitly controlled units; no new process is silently treated as EXCITATION.
struct IonizationChannel
{
  std::string name;
  std::string target_name;
  double threshold_eV = 0.0;
  std::vector<double> energy_eV;
  std::vector<double> cross_section_m2;
};

struct AttachmentChannel
{
  std::string name;
  std::string target_name;
  std::vector<double> energy_eV;
  std::vector<double> cross_section_m2;
};

struct KineticOperatorEntry
{
  std::size_t destination = 0;
  std::size_t donor = 0;
  double coefficient_m3_per_s = 0.0;
};

// Discrete operator Q acts on the cell-wise EEPF f0:
//  M d(n_e f0)/d(Nt) = Q (n_e f0),
//  M_i = integral_cell sqrt(energy_eV) denergy_eV.
// Each ionization event consumes 1 incident electron and produces 2 electrons,
// each at (epsilon - threshold)/2. Each attachment event removes one electron.
// Q uses the same cross-section quadrature as rate evaluation.
// IMPORTANT: this is the collision contribution, not yet a self-consistent
// spatial/temporal growth eigenvalue solver.
struct GrowthOperator
{
  std::size_t energy_cells = 0;
  std::vector<KineticOperatorEntry> entries;
  std::vector<double> electron_number_mass; // diagonal M_i
  std::vector<double> ionization_event_columns; // sum of ionization rates per donor
  std::vector<double> attachment_event_columns; // sum of attachment rates per donor
  double maximum_number_balance_relative_error = 0.0;
};

struct GrowthDiagnostics
{
  std::vector<double> ionization_rates_m3_per_s; // per target molecule
  std::vector<double> attachment_rates_m3_per_s; // per target molecule
  double reduced_temporal_growth_m3_per_s = 0.0; // (1/N)(1/n_e) dn_e/dt
  double reduced_ionization_energy_loss_eV_m3_per_s = 0.0; // includes mixture fractions
  double operator_number_balance_relative_error = 0.0;
};

GrowthOperator assembleGrowthCollisions(
    const ElasticInput & input,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments,
    // Empty preserves the validated piecewise-constant FV collision operator.
    // Nonempty freezes a positivity-limited, mass-conservative subcell shape.
    const std::vector<double> & reference_eepf = {});

// Evaluate against an EXPLICIT supplied, normalized and piecewise-constant
// EEPF (e.g. M5); no claim of growth-corrected EEPF or BOLSIG+ parity.
GrowthDiagnostics evaluateGrowthOnFrozenEepf(
    const ElasticInput & input,
    const ElasticResult & distribution,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments,
    // Empty preserves the validated piecewise-constant FV collision operator.
    // Nonempty freezes a positivity-limited, mass-conservative subcell shape.
    const std::vector<double> & reference_eepf = {});
}
