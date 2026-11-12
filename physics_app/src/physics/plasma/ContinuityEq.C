#include "ContinuityEq.h"

#include <cctype>
#include <set>

namespace Plasma
{
namespace
{

// Bind each species to the same canonical state naming rule.
VariableName
continuityStateName(const std::string & species)
{
  // All new solver states use one deterministic species-based naming rule.
  return "log_" + species;
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
ContinuityEq::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Bind plasma continuity species to deterministic internal state and kernel names. "
      "Supported FEM continuity generation creates the conservative log-molar time " 
      "derivative and drift-diffusion Kernels; FV transport stays Native.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "Species using finite-element variables.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Species using finite-volume variables.");
  params.addParam<VariableName>(
      "fem_potential", "Potential used by existing finite-element drift-diffusion kernels.");
  params.addParam<std::vector<Real>>(
      "fem_charge_numbers", "Signed charge numbers of finite-element species.");
  params.addParam<std::vector<Real>>(
      "fvm_charge_numbers", "Signed charge numbers of finite-volume species.");
  return params;
}

ContinuityEq::ContinuityEq(const InputParameters & parameters)
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
  const bool fem_charges = isParamValid("fem_charge_numbers");
  const bool fvm_charges = isParamValid("fvm_charge_numbers");

  // The current generated FEM transport slice is activated only when a
  // potential/charge binding is provided. Its transport Functor names are
  // always derived from the species identifier, never user-supplied.
  if (potential || fem_charges || fvm_charges)
  {
    if (!potential || !fem_charges || (!fvm.empty() && !fvm_charges))
      paramError("fem_potential",
                 "Provide fem_potential and FEM/FVM charge vectors together.");
    if (fem.empty())
      paramError("fem_species", "The current generated transport Kernel requires FEM species.");

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
ContinuityEq::checkIntegrity() const
{
  const auto & fem = getParam<std::vector<std::string>>("fem_species");
  const auto & fvm = getParam<std::vector<std::string>>("fvm_species");
  const auto variables = resolvedContinuityVariables(fem, fvm);
  validateExistingSpeciesVariables(fem, fvm, variables);
  if (isParamValid("fem_potential"))
    for (std::size_t i = 0; i < fem.size(); ++i)
    {
      requireUniqueFEKernel("FEMLogMolarTimeDerivative", variables[i]);
      requireUniqueFEKernel("FEMLogMolarDriftDiffusion", variables[i]);
    }
}

void
ContinuityEq::addFEKernels()
{
  if (!isParamValid("fem_potential"))
    return;
  const auto & species = getParam<std::vector<std::string>>("fem_species");
  const auto variables = resolvedContinuityVariables(
      species, getParam<std::vector<std::string>>("fvm_species"));
  const auto & charges = getParam<std::vector<Real>>("fem_charge_numbers");
  const std::string type = "FEMLogMolarDriftDiffusion";
  const std::string time_type = "FEMLogMolarTimeDerivative";
  for (std::size_t i = 0; i < species.size(); ++i)
  {
    // Retain the exact Native log-molar backward-Euler operator, state and region;
    // no new time convention, rate coefficient or user option is introduced.
    auto time_params = getFactory().getValidParams(time_type);
    time_params.set<NonlinearVariableName>("variable") = variables[i];
    assignBlocks(time_params, _blocks);
    getProblem().addKernel(time_type, species[i] + "_time", time_params);

    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variables[i];
    params.set<std::vector<VariableName>>("potential") =
        {getParam<VariableName>("fem_potential")};
    // Canonical provider names are species_id + "_mobility" and
    // species_id + "_diffusivity". Never infer fallback coefficients.
    params.set<MooseFunctorName>("mobility") = species[i] + "_mobility";
    // The lower-level Kernel parameter is still called "diffusion".
    params.set<MooseFunctorName>("diffusion") = species[i] + "_diffusivity";
    params.set<Real>("charge_number") = charges[i];
    assignBlocks(params, _blocks);
    const std::string kernel_name = species[i] + "_transport";
    getProblem().addKernel(type, kernel_name, params);
  }
}

} // namespace Plasma

using Plasma::ContinuityEq;
registerPhysicsBaseTasks("PhysicsApp", ContinuityEq);
registerMooseAction("PhysicsApp", ContinuityEq, "check_integrity");
registerMooseAction("PhysicsApp", ContinuityEq, "add_kernel");
