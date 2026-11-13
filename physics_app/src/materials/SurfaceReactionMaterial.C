#include "SurfaceReactionMaterial.h"

#include <algorithm>
#include <cmath>
#include <set>
#include <stdexcept>

registerMooseObject("PhysicsApp", SurfaceReactionMaterial);

InputParameters
SurfaceReactionMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Evaluates JSON-defined neutral thermal-sticking and signed outward mass fluxes.");
  params.addRequiredParam<FileName>("chemistry_file", "Canonical [Plasmas]/files JSON mechanism.");
  params.addRequiredParam<MooseFunctorName>("density", "Heavy-mixture density [kg/m^3].");
  params.addRequiredParam<MooseFunctorName>("temperature", "Heavy-particle temperature [K].");
  params.addRequiredParam<std::vector<std::string>>(
      "species", "Heavy species with mass-fraction Functors.");
  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "mass_fractions", "Mass fractions in species order.");
  params.addParam<std::vector<std::string>>(
      "active_reactions", {}, "Optional neutral surface reaction IDs.");
  return params;
}

SurfaceReactionMaterial::SurfaceReactionMaterial(const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _density(getFunctor<ADReal>("density")),
    _temperature(getFunctor<ADReal>("temperature")),
    _chemistry(std::vector<std::string>{getParam<FileName>("chemistry_file")})
{
  const auto names = getParam<std::vector<std::string>>("species");
  const auto fractions = getParam<std::vector<MooseFunctorName>>("mass_fractions");
  if (names.size() != fractions.size())
    paramError("mass_fractions", "species and mass_fractions sizes differ");

  for (std::size_t i = 0; i < names.size(); ++i)
  {
    if (!_mass_fractions.emplace(names[i], nullptr).second)
      paramError("species", "Duplicate surface species ", names[i]);
    try
    {
      if (names[i] == "e" || _chemistry.species(names[i]).molar_mass_kg_mol <= 0.0)
        paramError("species", "Missing molar_mass_kg_mol for ", names[i]);
    }
    catch (const std::runtime_error & error)
    {
      paramError("species", error.what());
    }
    _mass_fractions[names[i]] = &getFunctorByName<ADReal>(fractions[i]);
  }

  const auto requested = getParam<std::vector<std::string>>("active_reactions");
  std::set<std::string> selected;
  for (std::size_t index = 0; index < _chemistry.reactions().size(); ++index)
  {
    const auto & reaction = _chemistry.reactions()[index];
    const bool requested_here = requested.empty() ||
        std::find(requested.begin(), requested.end(), reaction.id) != requested.end();
    if (!requested_here)
      continue;
    if (reaction.domain != "surface" || reaction.rate.model != "thermal_sticking" ||
        reaction.reactants.size() != 1)
    {
      if (!requested.empty())
        paramError("active_reactions", reaction.id, " is not a neutral sticking reaction");
      continue;
    }
    const auto & species = reaction.reactants.begin()->first;
    if (species == "e" || _chemistry.species(species).charge_number != 0 ||
        !_mass_fractions.count(species))
    {
      if (!requested.empty())
        paramError("active_reactions", "Sticking requires an available neutral: ", species);
      continue;
    }
    selected.insert(reaction.id);
    _active_reactions.push_back(index);
  }
  for (const auto & id : requested)
    if (!selected.count(id))
      paramError("active_reactions", "Unknown/incompatible surface reaction ", id);

  for (const auto index : _active_reactions)
  {
    const auto & reaction = _chemistry.reactions()[index];
    addFunctorProperty<ADReal>(
        reaction.progress,
        [this, index](const auto & r, const auto & state) -> ADReal
        { return reactionProgress(_chemistry.reactions().at(index), r, state); });
  }

  // All named heavy species have deterministic outward surface flux outputs.
  // A species with no active surface reaction has exactly zero net flux.
  for (const auto & [species, record] : _mass_fractions)
    addFunctorProperty<ADReal>(
        "surface_mass_flux_" + species,
        [this, species](const auto & r, const auto & state) -> ADReal
        { return outwardMassFlux(species, r, state); });

  addFunctorProperty<ADReal>(
      "surface_mass_flux_sum",
      [this](const auto & r, const auto & state) -> ADReal
      {
        ADReal sum = 0.0;
        for (const auto & [species, record] : _mass_fractions)
          sum += outwardMassFlux(species, r, state);
        return sum;
      });
}

template <typename SpaceArg, typename StateArg>
ADReal
SurfaceReactionMaterial::concentration(const std::string & species,
                                       const SpaceArg & r,
                                       const StateArg & state) const
{
  const auto it = _mass_fractions.find(species);
  if (it == _mass_fractions.end())
    mooseError("Missing surface mass fraction for ", species);
  return _density(r, state) * (*(it->second))(r, state) /
         _chemistry.species(species).molar_mass_kg_mol;
}

template <typename SpaceArg, typename StateArg>
ADReal
SurfaceReactionMaterial::reactionProgress(const Plasma::ReactionRecord & reaction,
                                          const SpaceArg & r,
                                          const StateArg & state) const
{
  using std::sqrt;
  const auto & [species, coefficient] = *reaction.reactants.begin();
  const ADReal T = _temperature(r, state);
  if (!std::isfinite(MetaPhysicL::raw_value(T)) || MetaPhysicL::raw_value(T) <= 0.0)
    mooseError("Surface reaction ", reaction.id, " requires finite T > 0 K");
  const auto molar_mass = _chemistry.species(species).molar_mass_kg_mol;
  const ADReal speed = sqrt(8.0 * PHYSICS_CONSTANTS::R * T /
                            (PHYSICS_CONSTANTS::pi * molar_mass));
  return reaction.rate.sticking * 0.25 * concentration(species, r, state) *
         speed / coefficient;
}

template <typename SpaceArg, typename StateArg>
ADReal
SurfaceReactionMaterial::outwardMassFlux(const std::string & species,
                                         const SpaceArg & r,
                                         const StateArg & state) const
{
  ADReal flux = 0.0;
  const auto molar_mass = _chemistry.species(species).molar_mass_kg_mol;
  for (const auto index : _active_reactions)
  {
    const auto & reaction = _chemistry.reactions()[index];
    const auto nu = reaction.net(species);
    if (nu != 0)
      flux -= molar_mass * nu * reactionProgress(reaction, r, state);
  }
  return flux;
}
