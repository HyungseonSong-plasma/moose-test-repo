#include "HeavyReactionRateMaterial.h"

#include <cmath>
#include <set>
#include <stdexcept>

registerMooseObject("PhysicsApp", HeavyReactionRateMaterial);

InputParameters
HeavyReactionRateMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Computes JSON-defined heavy volume rate laws and publishes canonical R_H* Functors.");
  params.addRequiredParam<FileName>("chemistry_file", "Canonical [Plasmas]/files JSON mechanism.");
  params.addRequiredParam<MooseFunctorName>("density", "Heavy-mixture density [kg/m^3].");
  params.addRequiredParam<MooseFunctorName>("temperature", "Heavy-particle temperature [K].");
  params.addRequiredParam<std::vector<std::string>>(
      "species", "Heavy species in the JSON whose mass fractions are provided.");
  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "mass_fractions", "Mass-fraction Functors in species order.");
  params.addParam<std::vector<std::string>>(
      "active_reactions", {},
      "Optional JSON reaction IDs; if empty, select compatible heavy volume laws.");
  return params;
}

HeavyReactionRateMaterial::HeavyReactionRateMaterial(const InputParameters & parameters)
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
      paramError("species", "Duplicate heavy species ", names[i]);
    try
    {
      const auto & species = _chemistry.species(names[i]);
      if (names[i] == "e" || species.molar_mass_kg_mol <= 0.0)
        paramError("species", "Missing heavy molar_mass_kg_mol for ", names[i]);
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

    const bool valid_law = reaction.domain == "volume" &&
        (reaction.rate.model == "constant" || reaction.rate.model == "power_law");
    if (!valid_law)
    {
      if (!requested.empty())
        paramError("active_reactions", reaction.id, " is not a JSON heavy-volume rate law");
      continue;
    }

    bool compatible = true;
    for (const auto & [species, coefficient] : reaction.reactants)
      if (species == "e" || !_mass_fractions.count(species))
      {
        compatible = false;
        break;
      }
    if (!compatible)
    {
      if (!requested.empty())
        paramError("active_reactions", reaction.id, " requires an unavailable heavy reactant");
      continue;
    }
    selected.insert(reaction.id);
    _active_reactions.push_back(index);
  }
  for (const auto & id : requested)
    if (!selected.count(id))
      paramError("active_reactions", "Unknown/incompatible volume rate: ", id);

  for (const auto index : _active_reactions)
  {
    const auto & reaction = _chemistry.reactions()[index];
    addFunctorProperty<ADReal>(
        reaction.progress,
        [this, index](const auto & r, const auto & state) -> ADReal
        { return reactionProgress(_chemistry.reactions().at(index), r, state); });
  }
}

template <typename SpaceArg, typename StateArg>
ADReal
HeavyReactionRateMaterial::concentration(const std::string & species,
                                         const SpaceArg & r,
                                         const StateArg & state) const
{
  const auto it = _mass_fractions.find(species);
  if (it == _mass_fractions.end())
    mooseError("No mass fraction for reaction species ", species);
  const auto mass = _chemistry.species(species).molar_mass_kg_mol;
  return _density(r, state) * (*(it->second))(r, state) / mass;
}

template <typename SpaceArg, typename StateArg>
ADReal
HeavyReactionRateMaterial::reactionProgress(const Plasma::ReactionRecord & reaction,
                                            const SpaceArg & r,
                                            const StateArg & state) const
{
  using std::pow;
  ADReal k = reaction.rate.A_molar;
  if (reaction.rate.model == "power_law")
  {
    const ADReal T = _temperature(r, state);
    if (!std::isfinite(MetaPhysicL::raw_value(T)) || MetaPhysicL::raw_value(T) <= 0.0)
      mooseError("Heavy reaction ", reaction.id, " requires finite T_g > 0 K");
    k *= pow(reaction.rate.T_ref / T, reaction.rate.exponent);
  }
  for (const auto & [species, coefficient] : reaction.reactants)
  {
    const ADReal c = concentration(species, r, state);
    if (coefficient == 1)
      k *= c;
    else
      k *= pow(c, coefficient);
  }
  return k;
}
