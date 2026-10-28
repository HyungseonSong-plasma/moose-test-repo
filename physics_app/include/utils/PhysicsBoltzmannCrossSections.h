#pragma once

#include "PhysicsBoltzmannElasticSolver.h"

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

// Project only the physics currently implemented by the two-term steady DC
// elastic+excitation solver. EFFECTIVE/MOMENTUM, IONIZATION, ATTACHMENT,
// ROTATION and reversible/superelastic channels fail closed; they are not
// silently dropped. Target fractions must be specified for every elastic gas.
// max_energy_eV is used only for strict interpolation-domain verification.
struct ImportedElasticExcitation
{
  std::vector<ElasticTarget> targets;
  std::vector<ExcitationChannel> channels;
};

ImportedElasticExcitation prepareElasticExcitation(
    const CollisionFile & file,
    const std::map<std::string, double> & target_fractions,
    double max_energy_eV);
}
