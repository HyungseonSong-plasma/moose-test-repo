#include "ContinuityPhysics.h"

namespace Plasma
{

InputParameters
ContinuityPhysics::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Checks each plasma species against an existing solver variable of the correct type. "
      "Does not create variables or equations.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "Species using finite-element variables.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Species using finite-volume variables.");
  params.addRequiredParam<std::vector<VariableName>>(
      "variables", "Existing solver variables in fem_species order followed by fvm_species order.");

  params.addParam<VariableName>(
      "fem_potential", "Potential used by existing finite-element drift-diffusion kernels.");
  params.addParam<std::vector<MooseFunctorName>>(
      "fem_mobility", "Mobilities for finite-element species [m^2/(V s)].");
  params.addParam<std::vector<MooseFunctorName>>(
      "fem_diffusion", "Diffusion coefficients for finite-element species [m^2/s].");
  params.addParam<std::vector<Real>>(
      "fem_charge_numbers", "Signed charge number of each finite-element species.");
  return params;
}

ContinuityPhysics::ContinuityPhysics(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  validateSpeciesInputs(getParam<std::vector<std::string>>("fem_species"),
                        getParam<std::vector<std::string>>("fvm_species"),
                        getParam<std::vector<VariableName>>("variables"));
  const bool potential = isParamValid("fem_potential");
  const bool mobility = isParamValid("fem_mobility");
  const bool diffusion = isParamValid("fem_diffusion");
  const bool charges = isParamValid("fem_charge_numbers");
  if (potential || mobility || diffusion || charges)
  {
    if (!potential || !mobility || !diffusion || !charges)
      paramError("fem_potential", "Provide potential, mobility, diffusion and charge numbers together.");
    const auto count = getParam<std::vector<std::string>>("fem_species").size();
    if (!count ||
        getParam<std::vector<MooseFunctorName>>("fem_mobility").size() != count ||
        getParam<std::vector<MooseFunctorName>>("fem_diffusion").size() != count ||
        getParam<std::vector<Real>>("fem_charge_numbers").size() != count)
      paramError("fem_mobility", "One mobility, diffusion and charge number is required per FEM species.");
    for (const auto charge : getParam<std::vector<Real>>("fem_charge_numbers"))
      if (charge == 0)
        paramError("fem_charge_numbers", "A drift species must have nonzero charge.");
  }
}

void
ContinuityPhysics::checkIntegrity() const
{
  validateExistingSpeciesVariables(getParam<std::vector<std::string>>("fem_species"),
                                   getParam<std::vector<std::string>>("fvm_species"),
                                   getParam<std::vector<VariableName>>("variables"));
}

void
ContinuityPhysics::addFEKernels()
{
  if (!isParamValid("fem_potential"))
    return;
  const auto & species = getParam<std::vector<std::string>>("fem_species");
  const auto & variables = getParam<std::vector<VariableName>>("variables");
  const auto & mobility = getParam<std::vector<MooseFunctorName>>("fem_mobility");
  const auto & diffusion = getParam<std::vector<MooseFunctorName>>("fem_diffusion");
  const auto & charges = getParam<std::vector<Real>>("fem_charge_numbers");
  const std::string type = "PhysicsFEMLogMolarDriftDiffusion";
  for (std::size_t i = 0; i < species.size(); ++i)
  {
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variables[i];
    params.set<std::vector<VariableName>>("potential") =
        {getParam<VariableName>("fem_potential")};
    params.set<MooseFunctorName>("mobility") = mobility[i];
    params.set<MooseFunctorName>("diffusion") = diffusion[i];
    params.set<Real>("charge_number") = charges[i];
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_" + species[i] + "_drift_diffusion", params);
  }
}

}

// MOOSE registers this action by its short name.
using Plasma::ContinuityPhysics;
registerPhysicsBaseTasks("PhysicsApp", ContinuityPhysics);
registerMooseAction("PhysicsApp", ContinuityPhysics, "check_integrity");
registerMooseAction("PhysicsApp", ContinuityPhysics, "add_kernel");
