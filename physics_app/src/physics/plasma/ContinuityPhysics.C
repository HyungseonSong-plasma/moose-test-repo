#include "ContinuityPhysics.h"

#include <cctype>
#include <set>

namespace Plasma
{
namespace
{

// The schema owns the names. Legacy S6 density states are bound internally
// until a separate, evidence-backed variable migration is accepted.
VariableName
continuityStateName(const std::string & species)
{
  if (species == "O2p")
    return "log_ni";
  if (species == "Om")
    return "log_nm";
  if (species == "Op")
    return "log_nop";
  return "log_n" + species;
}

std::vector<VariableName>
resolvedContinuityVariables(const std::vector<std::string> & fem,
                            const std::vector<std::string> & fvm)
{
  std::vector<VariableName> resolved;
  resolved.reserve(fem.size() + fvm.size());
  for (const auto & species : fem)
    resolved.push_back(continuityStateName(species));
  for (const auto & species : fvm)
    resolved.push_back(continuityStateName(species));
  return resolved;
}

} // namespace

InputParameters
ContinuityPhysics::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Bind plasma continuity species to deterministic internal state and kernel names. "
      "Only the supported FEM drift-diffusion slice currently creates a solver Kernel.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "Species using finite-element variables.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Species using finite-volume variables.");

  params.addParam<VariableName>(
      "fem_potential", "Potential used by existing finite-element drift-diffusion kernels.");
  params.addParam<std::vector<MooseFunctorName>>(
      "mobility", "Species-ordered mobility functors [m^2/(V s)]; FEM first, then FVM.");
  params.addParam<std::vector<MooseFunctorName>>(
      "diffusivity", "Species-ordered diffusivity functors [m^2/s]; FEM first, then FVM.");
  params.addParam<std::vector<Real>>(
      "fem_charge_numbers", "Signed charge numbers of finite-element species.");
  params.addParam<std::vector<Real>>(
      "fvm_charge_numbers", "Signed charge numbers of finite-volume species.");
  return params;
}

ContinuityPhysics::ContinuityPhysics(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  const auto & fem = getParam<std::vector<std::string>>("fem_species");
  const auto & fvm = getParam<std::vector<std::string>>("fvm_species");
  const auto variables = resolvedContinuityVariables(fem, fvm);
  validateSpeciesInputs(fem, fvm, variables);

  // A species ID becomes part of a generated object name and must be safe.
  for (const auto & species : fem)
  {
    if (species.empty() || !std::isalpha(static_cast<unsigned char>(species.front())))
      paramError("fem_species", "Invalid species ID for automatic naming: ", species);
    for (const auto ch : species)
      if (!std::isalnum(static_cast<unsigned char>(ch)) && ch != '_')
        paramError("fem_species", "Invalid species ID for automatic naming: ", species);
  }
  for (const auto & species : fvm)
  {
    if (species.empty() || !std::isalpha(static_cast<unsigned char>(species.front())))
      paramError("fvm_species", "Invalid species ID for automatic naming: ", species);
    for (const auto ch : species)
      if (!std::isalnum(static_cast<unsigned char>(ch)) && ch != '_')
        paramError("fvm_species", "Invalid species ID for automatic naming: ", species);
  }

  const bool potential = isParamValid("fem_potential");
  const bool mobility = isParamValid("mobility");
  const bool diffusivity = isParamValid("diffusivity");
  const bool fem_charges = isParamValid("fem_charge_numbers");
  const bool fvm_charges = isParamValid("fvm_charge_numbers");

  // The existing validation-only inputs remain legal. Supplying any
  // coefficients activates the supported FEM builder and requires a complete
  // species-ordered binding, even when FV species are validation-only.
  if (potential || mobility || diffusivity || fem_charges || fvm_charges)
  {
    if (!potential || !mobility || !diffusivity || !fem_charges ||
        (!fvm.empty() && !fvm_charges))
      paramError("mobility",
                 "Provide fem_potential, mobility, diffusivity and FEM/FVM charge vectors together.");
    if (fem.empty())
      paramError("fem_species", "The current generated transport Kernel requires FEM species.");

    const auto count = fem.size() + fvm.size();
    if (getParam<std::vector<MooseFunctorName>>("mobility").size() != count ||
        getParam<std::vector<MooseFunctorName>>("diffusivity").size() != count)
      paramError("mobility",
                 "Provide one mobility and one diffusivity for each FEM/FVM species.");
    if (getParam<std::vector<Real>>("fem_charge_numbers").size() != fem.size() ||
        (fvm_charges &&
         getParam<std::vector<Real>>("fvm_charge_numbers").size() != fvm.size()))
      paramError("fem_charge_numbers", "Charge vectors must match their FEM/FVM species lists.");

    // This first generated slice only recognizes pinned S6 charge identities.
    // Do not invent a scientific sign for an unregistered species.
    auto verifyCharge = [this](const std::string & key, const std::string & species, Real charge) {
      Real expected = 0;
      if (species == "e" || species == "Om")
        expected = -1;
      else if (species == "O2p" || species == "Op")
        expected = 1;
      else
        paramError(key, "No verified charged-species identity for: ", species);
      if (charge != expected)
        paramError(key, "Charge does not match verified species identity: ", species);
    };
    const auto & fe_charges = getParam<std::vector<Real>>("fem_charge_numbers");
    for (std::size_t i = 0; i < fem.size(); ++i)
      verifyCharge("fem_charge_numbers", fem[i], fe_charges[i]);
    if (fvm_charges)
    {
      const auto & fv_charges = getParam<std::vector<Real>>("fvm_charge_numbers");
      for (std::size_t i = 0; i < fvm.size(); ++i)
        verifyCharge("fvm_charge_numbers", fvm[i], fv_charges[i]);
    }
  }
}

void
ContinuityPhysics::checkIntegrity() const
{
  const auto & fem = getParam<std::vector<std::string>>("fem_species");
  const auto & fvm = getParam<std::vector<std::string>>("fvm_species");
  const auto variables = resolvedContinuityVariables(fem, fvm);
  validateExistingSpeciesVariables(fem, fvm, variables);
  if (isParamValid("fem_potential"))
    for (std::size_t i = 0; i < fem.size(); ++i)
      requireUniqueFEKernel("PhysicsFEMLogMolarDriftDiffusion", variables[i]);
}

void
ContinuityPhysics::addFEKernels()
{
  if (!isParamValid("fem_potential"))
    return;
  const auto & species = getParam<std::vector<std::string>>("fem_species");
  const auto variables = resolvedContinuityVariables(
      species, getParam<std::vector<std::string>>("fvm_species"));
  const auto & mobility = getParam<std::vector<MooseFunctorName>>("mobility");
  const auto & diffusivity = getParam<std::vector<MooseFunctorName>>("diffusivity");
  const auto & charges = getParam<std::vector<Real>>("fem_charge_numbers");
  const std::string type = "PhysicsFEMLogMolarDriftDiffusion";
  for (std::size_t i = 0; i < species.size(); ++i)
  {
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variables[i];
    params.set<std::vector<VariableName>>("potential") =
        {getParam<VariableName>("fem_potential")};
    params.set<MooseFunctorName>("mobility") = mobility[i];
    // Lower-level MOOSE Kernel interface is unchanged. Provider names such as
    // electron_diffusion are retained; only the Physics input key changed.
    params.set<MooseFunctorName>("diffusion") = diffusivity[i];
    params.set<Real>("charge_number") = charges[i];
    assignBlocks(params, _blocks);
    const std::string kernel_name = species[i] + "_transport";
    getProblem().addKernel(type, kernel_name, params);
  }
}

} // namespace Plasma

using Plasma::ContinuityPhysics;
registerPhysicsBaseTasks("PhysicsApp", ContinuityPhysics);
registerMooseAction("PhysicsApp", ContinuityPhysics, "check_integrity");
registerMooseAction("PhysicsApp", ContinuityPhysics, "add_kernel");
