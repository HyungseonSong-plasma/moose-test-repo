#include "PlasmaInterface.h"
#include "ActionWarehouse.h"
#include "Chemistry.h"
#include "ChemistryAction.h"

#include "KernelBase.h"
#include "NonlinearSystemBase.h"

#include <set>

// Reuse standard PhysicsBase parameters for every plasma Physics class.
InputParameters
PlasmaInterface::validParams()
{
  InputParameters params = PhysicsBase::validParams();
  return params;
}

// Pass the derived Physics inputs to the shared MOOSE PhysicsBase.
PlasmaInterface::PlasmaInterface(const InputParameters & parameters)
  : PhysicsBase(parameters)
{
}


const Plasma::ChemistryData &
PlasmaInterface::chemistryData() const
{
  const auto actions = _awh.getActions<ChemistryAction>();
  if (actions.size() != 1)
    mooseError("Exactly one [Physics]/[Plasmas] mechanism owner is required");
  return actions.front()->data();
}

bool
PlasmaInterface::chemistryEnabled() const
{
  return !_awh.getActions<Plasma::Chemistry>().empty();
}

// Validate species identities and resolved variable ordering before building kernels.
void
PlasmaInterface::validateSpeciesInputs(
    const std::vector<std::string> & finite_element_species,
    const std::vector<std::string> & finite_volume_species,
    const std::vector<VariableName> & variables) const
{
  // At least one FEM or FV species must be declared.
  if (finite_element_species.empty() && finite_volume_species.empty())
    paramError("fem_species", "List at least one species in fem_species or fvm_species.");

  // Each species requires exactly one resolved state variable.
  if (variables.size() != finite_element_species.size() + finite_volume_species.size())
    paramError("fem_species", "Provide one internally resolved solver variable for each listed species.");

  // Use a shared set to detect duplicates within and across FEM/FV groups.
  std::set<std::string> unique_species;
  // FEM names must be nonempty and unique.
  for (const auto & species : finite_element_species)
    if (species.empty() || !unique_species.insert(species).second)
      paramError("fem_species", "Repeated or empty species in fem_species: ", species);

  // FV names must also be distinct from all FEM names.
  for (const auto & species : finite_volume_species)
    if (species.empty() || !unique_species.insert(species).second)
      paramError("fvm_species",
                 "Repeated or empty species in fvm_species, or species listed in both groups: ",
                 species);

  // Two species must not bind to the same resolved solver variable.
  std::set<VariableName> unique_variables;
  for (const auto & variable : variables)
    if (variable.empty() || !unique_variables.insert(variable).second)
      paramError("fem_species", "Repeated or empty resolved solver variable: ", variable);
}

// Check that resolved variables exist and have the declared FEM/FV family.
void
PlasmaInterface::validateExistingSpeciesVariables(
    const std::vector<std::string> & finite_element_species,
    const std::vector<std::string> & finite_volume_species,
    const std::vector<VariableName> & variables) const
{
  // Variable order is FEM species first, followed by FV species.
  for (std::size_t index = 0; index < variables.size(); ++index)
  {
    const auto & variable = variables[index];
    // Fail if a Physics input references a variable not created by the model.
    if (!solverVariableExists(variable))
      paramError(index >= finite_element_species.size() ? "fvm_species" : "fem_species",
                 "The solver variable '",
                 variable,
                 "' was not found. Define it before using this check.");

    // The index determines which discretization and species name to inspect.
    const bool is_finite_volume = index >= finite_element_species.size();
    // Reject a variable declared in the wrong MOOSE discretization family.
    if (isVariableFV(variable) != is_finite_volume)
      paramError(is_finite_volume ? "fvm_species" : "fem_species",
                 "Species '",
                 is_finite_volume ? finite_volume_species[index - finite_element_species.size()]
                                  : finite_element_species[index],
                 "' uses a solver variable of the wrong type: ",
                 variable);
  }
}

// Prevent two owners from adding the same FEM kernel type to one variable.
void
PlasmaInterface::requireUniqueFEKernel(const std::string & type,
                                      const VariableName & variable) const
{
  // Read the existing kernels from the primary nonlinear system.
  const auto & kernels = getProblem().getNonlinearSystemBase(0).getKernelWarehouse().getObjects();
  // Count kernels matching both the operator type and target variable.
  std::size_t matches = 0;
  for (const auto & kernel : kernels)
  {
    // Inspect registered object parameters instead of relying on names.
    const auto & parameters = kernel->parameters();
    if (kernel->type() == type && parameters.isParamValid("variable") &&
        parameters.get<NonlinearVariableName>("variable") == variable)
      ++matches;
  }

  // This deliberately rejects even different-source kernels of the same
  // type on one variable. A deliberate multi-source model must use explicit
  // native Kernels until individual ownership is represented.
  if (matches != 1)
    mooseError("The generated ", type, " operator for solver variable '", variable,
               "' must have exactly one owner; found ", matches,
               ". Remove the duplicate native Kernel or overlapping Physics input.");
}
