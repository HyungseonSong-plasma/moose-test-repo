#include "DDContinuityEq.h"
#include "PlasmaMechanism.h"

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
DDContinuityEq::validParams()
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
  return params;
}

DDContinuityEq::DDContinuityEq(const InputParameters & parameters)
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

  // Charges are specified once in [Plasmas]/files, not by parallel per-species
  // vectors. Keep this builder disabled in pure variable-binding check mode.
  if (isParamValid("fem_potential"))
  {
    if (fem.empty())
      paramError("fem_species", "Generated FEM transport requires FEM species.");
    const auto & mechanism = chemistryData();
    for (const auto & id : fem)
      (void)mechanism.species(id);
    for (const auto & id : fvm)
      (void)mechanism.species(id);
  }
}

void
DDContinuityEq::checkIntegrity() const
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
      if (chemistryEnabled() && chemistryData().hasSpeciesSource(fem[i]))
        requireUniqueFEKernel("FunctorKernel", variables[i]);
    }
}

void
DDContinuityEq::addFEKernels()
{
  if (!isParamValid("fem_potential"))
    return;
  const auto & species = getParam<std::vector<std::string>>("fem_species");
  const auto variables = resolvedContinuityVariables(
      species, getParam<std::vector<std::string>>("fvm_species"));
  const auto & mechanism = chemistryData();
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
    params.set<Real>("charge_number") = mechanism.species(species[i]).charge_number;
    assignBlocks(params, _blocks);
    const std::string kernel_name = species[i] + "_transport";
    getProblem().addKernel(type, kernel_name, params);

    // One source owner per species; each channel has a separate progress and
    // signed coefficient inside the Chemistry-owned species source functor.
    if (chemistryEnabled() && mechanism.hasSpeciesSource(species[i]))
    {
      const std::string source_type = "FunctorKernel";
      auto source_params = getFactory().getValidParams(source_type);
      source_params.set<NonlinearVariableName>("variable") = variables[i];
      source_params.set<MooseFunctorName>("functor") = "S_" + species[i] + "_molar";
      source_params.set<bool>("functor_on_rhs") = true;
      assignBlocks(source_params, _blocks);
      getProblem().addKernel(source_type, species[i] + "_source", source_params);
    }
  }
}

} // namespace Plasma

using Plasma::DDContinuityEq;
registerPhysicsBaseTasks("PhysicsApp", DDContinuityEq);
registerMooseAction("PhysicsApp", DDContinuityEq, "check_integrity");
registerMooseAction("PhysicsApp", DDContinuityEq, "add_kernel");
