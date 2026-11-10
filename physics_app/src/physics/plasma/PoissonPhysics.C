#include "PoissonPhysics.h"

namespace Plasma
{

InputParameters
PoissonPhysics::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Checks existing poisson inputs without creating or modifying solver equations.");
  params.addRequiredParam<VariableName>(
      "potential_variable", "Existing solver variable for the electric potential.");

  params.addParam<MaterialPropertyName>(
      "charge_source_material", "Source rho/epsilon0 for -laplacian(phi) = rho/epsilon0.");
  params.addParam<std::vector<BoundaryName>>(
      "ground_boundaries", {}, "Zero-potential boundaries created by this Physics.");
  return params;
}

PoissonPhysics::PoissonPhysics(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  if (getParam<VariableName>("potential_variable").empty())
    paramError("potential_variable", "Specify an electric potential variable.");
  if (!getParam<std::vector<BoundaryName>>("ground_boundaries").empty() &&
      !isParamValid("charge_source_material"))
    paramError("charge_source_material", "Provide charge source to create potential boundaries.");
}

void
PoissonPhysics::checkIntegrity() const
{
  const auto & potential = getParam<VariableName>("potential_variable");
  if (!solverVariableExists(potential))
    paramError("potential_variable", "Electric potential variable was not found: ", potential);
  if (isParamValid("charge_source_material"))
  {
    requireUniqueFEKernel("Diffusion", potential);
    requireUniqueFEKernel("MatBodyForce", potential);
  }
}

void
PoissonPhysics::addFEKernels()
{
  if (!isParamValid("charge_source_material"))
    return;
  const auto variable = getParam<VariableName>("potential_variable");
  {
    const std::string type = "Diffusion";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variable;
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_diffusion", params);
  }
  {
    const std::string type = "MatBodyForce";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variable;
    params.set<MaterialPropertyName>("material_property") =
        getParam<MaterialPropertyName>("charge_source_material");
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_charge_source", params);
  }
}

void
PoissonPhysics::addFEBCs()
{
  if (!isParamValid("charge_source_material"))
    return;
  for (const auto & boundary : getParam<std::vector<BoundaryName>>("ground_boundaries"))
  {
    const std::string type = "DirichletBC";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") =
        getParam<VariableName>("potential_variable");
    params.set<std::vector<BoundaryName>>("boundary") = {boundary};
    params.set<Real>("value") = 0;
    getProblem().addBoundaryCondition(type, name() + "_ground_" + boundary, params);
  }
}

}

using Plasma::PoissonPhysics;
registerPhysicsBaseTasks("PhysicsApp", PoissonPhysics);
registerMooseAction("PhysicsApp", PoissonPhysics, "check_integrity");
registerMooseAction("PhysicsApp", PoissonPhysics, "add_kernel");
registerMooseAction("PhysicsApp", PoissonPhysics, "add_bc");
