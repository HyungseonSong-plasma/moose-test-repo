#include "PlasmaSpeciesContinuityPhysics.h"

#include <set>
#include <string>
#include <vector>

registerPhysicsBaseTasks("PhysicsApp", PlasmaSpeciesContinuityPhysics);
registerMooseAction("PhysicsApp", PlasmaSpeciesContinuityPhysics, "check_integrity");

InputParameters
PlasmaSpeciesContinuityPhysics::validParams()
{
  InputParameters params = PhysicsBase::validParams();
  params.addClassDescription(
      "Validates FEM/FV species-to-existing-solver-variable bindings for the Issue #402 "
      "opt-in plasma input pilot. No equation or variable is generated.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "Species whose existing continuity variables use FEM.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Species whose existing continuity variables use FV.");
  params.addRequiredParam<std::vector<VariableName>>(
      "variables", "Existing solved variables in fem_species order followed by fvm_species order.");
  params.addParam<MooseEnum>(
      "owner_mode",
      MooseEnum("external generate", "external"),
      "Only external bindings are implemented in the G1 pilot; generate is rejected explicitly.");
  return params;
}

PlasmaSpeciesContinuityPhysics::PlasmaSpeciesContinuityPhysics(
    const InputParameters & parameters)
  : PhysicsBase(parameters)
{
  const auto & fem = getParam<std::vector<std::string>>("fem_species");
  const auto & fvm = getParam<std::vector<std::string>>("fvm_species");
  const auto & vars = getParam<std::vector<VariableName>>("variables");

  if (getParam<MooseEnum>("owner_mode") != "external")
    paramError("owner_mode",
               "P402_OWNER: G1 external-binding pilot cannot generate or replace equations.");

  if (fem.empty() && fvm.empty())
    paramError("fem_species", "P402_SPECIES: set fem_species and/or fvm_species.");

  if (vars.size() != fem.size() + fvm.size())
    paramError("variables", "P402_SPECIES: expected exactly one variable per FEM/FV species.");

  std::set<std::string> unique_species;
  for (const auto & sp : fem)
    if (sp.empty() || !unique_species.insert(sp).second)
      paramError("fem_species", "P402_SPECIES: duplicate or empty FEM species: ", sp);
  for (const auto & sp : fvm)
    if (sp.empty() || !unique_species.insert(sp).second)
      paramError("fvm_species", "P402_SPECIES: duplicated across FEM/FV or empty species: ", sp);

  std::set<VariableName> unique_variables;
  for (const auto & var : vars)
    if (var.empty() || !unique_variables.insert(var).second)
      paramError("variables", "P402_OWNER: duplicate or empty continuity variable: ", var);
}

void
PlasmaSpeciesContinuityPhysics::checkIntegrity() const
{
  const auto & fem = getParam<std::vector<std::string>>("fem_species");
  const auto & fvm = getParam<std::vector<std::string>>("fvm_species");
  const auto & vars = getParam<std::vector<VariableName>>("variables");

  for (std::size_t i = 0; i < vars.size(); ++i)
  {
    const auto & var = vars[i];
    if (!solverVariableExists(var))
      paramError("variables",
                 "P402_OWNER: expected an externally owned solver variable '",
                 var,
                 "'; it was not found. The G1 pilot never creates it.");
    const bool selected_fv = i >= fem.size();
    if (isVariableFV(var) != selected_fv)
      paramError("variables",
                 "P402_SPECIES: species '",
                 selected_fv ? fvm[i - fem.size()] : fem[i],
                 "' was mapped to the wrong FEM/FV variable family: ",
                 var);
  }
}
