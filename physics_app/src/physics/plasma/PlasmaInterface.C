#include "PlasmaInterface.h"

#include <set>

InputParameters
PlasmaInterface::validParams()
{
  InputParameters params = PhysicsBase::validParams();
  params.addParam<MooseEnum>(
      "owner_mode",
      MooseEnum("external generate", "external"),
      "Use existing solver variables only. Creating equations is not supported.");
  return params;
}

PlasmaInterface::PlasmaInterface(const InputParameters & parameters)
  : PhysicsBase(parameters)
{
  if (getParam<MooseEnum>("owner_mode") != "external")
    paramError("owner_mode",
               "Cannot create equations: this check only uses existing solver variables.");
}

void
PlasmaInterface::validateSpeciesInputs(
    const std::vector<std::string> & finite_element_species,
    const std::vector<std::string> & finite_volume_species,
    const std::vector<VariableName> & variables) const
{
  if (finite_element_species.empty() && finite_volume_species.empty())
    paramError("fem_species", "List at least one species in fem_species or fvm_species.");

  if (variables.size() != finite_element_species.size() + finite_volume_species.size())
    paramError("variables", "Provide one solver variable for each listed species.");

  std::set<std::string> unique_species;
  for (const auto & species : finite_element_species)
    if (species.empty() || !unique_species.insert(species).second)
      paramError("fem_species", "Repeated or empty species in fem_species: ", species);

  for (const auto & species : finite_volume_species)
    if (species.empty() || !unique_species.insert(species).second)
      paramError("fvm_species",
                 "Repeated or empty species in fvm_species, or species listed in both groups: ",
                 species);

  std::set<VariableName> unique_variables;
  for (const auto & variable : variables)
    if (variable.empty() || !unique_variables.insert(variable).second)
      paramError("variables", "Repeated or empty solver variable: ", variable);
}

void
PlasmaInterface::validateExistingSpeciesVariables(
    const std::vector<std::string> & finite_element_species,
    const std::vector<std::string> & finite_volume_species,
    const std::vector<VariableName> & variables) const
{
  for (std::size_t index = 0; index < variables.size(); ++index)
  {
    const auto & variable = variables[index];
    if (!solverVariableExists(variable))
      paramError("variables",
                 "The solver variable '",
                 variable,
                 "' was not found. Define it before using this check.");

    const bool is_finite_volume = index >= finite_element_species.size();
    if (isVariableFV(variable) != is_finite_volume)
      paramError("variables",
                 "Species '",
                 is_finite_volume ? finite_volume_species[index - finite_element_species.size()]
                                  : finite_element_species[index],
                 "' uses a solver variable of the wrong type: ",
                 variable);
  }
}
