#pragma once

#include "MooseObject.h"
#include "MooseUtils.h"

#include <string>
#include <vector>

/**
 * Resolve per-reaction number-density weights: prefer species_density_fractions,
 * fall back to legacy mole_fractions (same physical meaning in Boltzmann kernels).
 */
inline std::vector<Real>
resolveSpeciesDensityFractions(const MooseObject & me)
{
  const auto & pars = me.parameters();
  const bool have_new = pars.isParamValid("species_density_fractions");
  const bool have_old = pars.isParamValid("mole_fractions");

  if (have_new && have_old)
    me.mooseError(me.type(),
                  " '",
                  me.name(),
                  "': set only one of species_density_fractions or mole_fractions.");

  if (have_new)
    return pars.get<std::vector<Real>>("species_density_fractions");
  if (have_old)
    return pars.get<std::vector<Real>>("mole_fractions");

  me.mooseError(me.type(),
                " '",
                me.name(),
                "': specify species_density_fractions or mole_fractions with one entry per reaction in "
                "reaction_lists.");
}

/** Optional space-separated species labels; count must match reaction_lists when set. */
inline void
checkOptionalSpeciesLabels(const MooseObject & me, const std::vector<std::string> & reaction_names)
{
  const auto & pars = me.parameters();
  if (!pars.isParamValid("species"))
    return;

  std::vector<std::string> species;
  MooseUtils::tokenize(pars.get<std::string>("species"), species, 1, " ");
  if (species.size() != reaction_names.size())
    me.paramError("species",
                  "Number of entries (",
                  species.size(),
                  ") must match the number of reaction IDs in reaction_lists (",
                  reaction_names.size(),
                  ").");
}

inline void
checkDensityFractionsVsReactions(const MooseObject & me,
                                 const std::vector<std::string> & reaction_names,
                                 const std::vector<Real> & density_fractions)
{
  if (density_fractions.size() != reaction_names.size())
    me.paramError(me.parameters().isParamValid("species_density_fractions") ? "species_density_fractions"
                                                                            : "mole_fractions",
                  "Length (",
                  density_fractions.size(),
                  ") must match reaction_lists count (",
                  reaction_names.size(),
                  ").");
}

inline void
checkElasticMassInverseVsReactions(const MooseObject & me,
                                   const std::vector<std::string> & reaction_names,
                                   const std::vector<Real> & mass_inv)
{
  if (mass_inv.size() != reaction_names.size())
    me.paramError("elastic_mass_inverse",
                  "Length (",
                  mass_inv.size(),
                  ") must match reaction_lists count (",
                  reaction_names.size(),
                  ").");
}
