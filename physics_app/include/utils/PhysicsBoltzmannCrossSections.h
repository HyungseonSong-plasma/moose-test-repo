#pragma once

#include "PhysicsBoltzmannElasticSolver.h"
#include "PhysicsBoltzmannGrowth.h"

#include <cstddef>
#include <istream>
#include <map>
#include <string>
#include <vector>

// Independent C++ reader for the text collision format documented by BOLSIG+.
// No LXCat raw datasets are embedded or redistributed by this module.
namespace PhysicsBoltzmann
{
enum class CollisionKind
{
  Elastic, Effective, Excitation, Ionization, Attachment, Rotation
};

struct CollisionRecord
{
  CollisionKind kind = CollisionKind::Elastic;
  std::string target;                // pre-arrow target species
  std::string product;               // optional post-arrow state label
  bool reversible = false;           // <-> requires superelastic physics
  double parameter = 0.0;            // elastic m_e/M or excitation threshold [eV]
  double upper_to_lower_weight_ratio = 1.0; // g_upper/g_lower on reversible excitation
  std::vector<double> energy_eV;
  std::vector<double> cross_section_m2;
  std::vector<std::string> comments; // original per-process citations/notes
  std::size_t source_line = 0;
};

struct CollisionFile
{
  std::vector<std::string> header;  // preserved preamble / citation metadata
  std::vector<CollisionRecord> records; // including unsupported model processes
};

// Strict structural parser: no implicit unit conversions, process filtering,
// extrapolation, or unrecorded physical fallback. The file owner must separately
// verify raw-byte SHA-256, contributor rights and provenance.
CollisionFile parseBolsigCrossSections(std::istream & input);

// Explicit opt-in 07/2024 collision-table boundary preprocessing for a
// user-local source whose READCOLLISIONS instruction used Extrapolate=1.
// This preserves every process and its original source_line/identity;
// high-energy continuation uses 1.5x knot growth and log(E)/E at those
// new knots, with linear interpolation between knots (not analytic
// evaluation between them). Any ill-defined continuation fails closed.
// Ionization/excitation thresholds are enforced without deleting the
// corresponding source process when it lies beyond the solver Emax.
CollisionFile normalizeBolsig2024CollisionFile(
    const CollisionFile & source, double max_energy_eV,
    bool extrapolate_high_energy);

// Project steady DC elastic+excitation physics. A source EFFECTIVE/MOMENTUM
// record contains *total* elastic + inelastic momentum scattering. For this
// excitation-only subset, derive the elastic residual on the union of source
// energy knots before the solver adds excitation momentum once; reject a
// negative residual or duplicate ELASTIC/EFFECTIVE target. This is not valid
// for files containing IONIZATION, ATTACHMENT or ROTATION, which fail closed.
// Reversible/superelastic channels still require explicit opt-in and states.
// An EFFECTIVE momentum record for the excited upper state is rejected
// because its included inverse scattering is not separately reconstructed.
// All active target fractions and full cross-section energy coverage are
// mandatory; no source extrapolation or invented physical data is permitted.
struct ImportedElasticExcitation
{
  std::vector<ElasticTarget> targets;
  std::vector<ExcitationChannel> channels;
};

ImportedElasticExcitation prepareElasticExcitation(
    const CollisionFile & file,
    const std::map<std::string, double> & target_fractions,
    double max_energy_eV,
    bool enable_reversible = false,
    const std::vector<CollisionRecord> & additional_scattering = {});

// Explicit whole-set import for M6 particle-changing physics. This function
// must not discard IONIZATION or ATTACHMENT to satisfy the M5-only projector.
// In M6b3 all channels contribute to sigma_m exactly once: an EFFECTIVE
// record supplies total field scattering while its elastic recoil residual
// subtracts excitation + ionization + attachment; an ELASTIC record gets
// those channels added to an independent field-scattering table.
// The source must explicitly include every physical process used.
struct ImportedGrowthPhysics
{
  std::vector<ElasticTarget> targets;
  std::vector<ExcitationChannel> excitation_channels;
  std::vector<IonizationChannel> ionization_channels;
  std::vector<AttachmentChannel> attachment_channels;
};

ImportedGrowthPhysics prepareGrowthPhysics(
    const CollisionFile & file,
    const std::map<std::string, double> & target_fractions,
    double max_energy_eV,
    bool enable_reversible = false);
}
