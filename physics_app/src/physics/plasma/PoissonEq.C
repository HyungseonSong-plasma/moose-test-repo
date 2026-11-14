#include "PoissonEq.h"

#include <cmath>

namespace Plasma
{

InputParameters
PoissonEq::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Create or reuse a finite-element electric potential state.");
  params.addRequiredParam<VariableName>(
      "fem_potential", "FEM potential solver variable [V], generated when missing.");

  params.addParam<Real>("initial_potential_V", 0.0,
                        "Initial numerical guess in volts for an auto-created potential.");
  params.addParam<MaterialPropertyName>(
      "charge_source_material",
      "Legacy FE MaterialProperty source rho/epsilon0 for -laplacian(phi) = rho/epsilon0.");
  params.addParam<MooseFunctorName>(
      "charge_source_functor",
      "AD Functor source rho/epsilon0 for -laplacian(phi) = rho/epsilon0, "
      "for example poisson_charge_source from PhysicsPlasmaChargeDensityMaterial. "
      "Mutually exclusive with charge_source_material.");
  params.addParam<std::vector<BoundaryName>>(
      "ground_boundaries", {}, "Zero-potential boundaries created by this Physics.");
  return params;
}

PoissonEq::PoissonEq(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  if (getParam<VariableName>("fem_potential").empty())
    paramError("fem_potential", "Specify an electric potential variable.");
  if (isParamValid("charge_source_material") && isParamValid("charge_source_functor"))
    paramError("charge_source_functor",
               "Poisson may have only one charge RHS owner: choose "
               "charge_source_functor or charge_source_material, not both.");
  if (isParamValid("charge_source_functor") &&
      getParam<MooseFunctorName>("charge_source_functor").empty())
    paramError("charge_source_functor", "A Poisson charge source Functor must not be empty.");
  if (!getParam<std::vector<BoundaryName>>("ground_boundaries").empty() &&
      !isParamValid("charge_source_material") &&
      !isParamValid("charge_source_functor"))
    paramError("charge_source_functor",
               "Provide charge_source_functor or charge_source_material "
               "to generate grounded Poisson boundaries.");
  if (!std::isfinite(getParam<Real>("initial_potential_V")))
    paramError("initial_potential_V", "Initial potential must be finite [V].");
  saveSolverVariableName(getParam<VariableName>("fem_potential"));
  addRequiredPhysicsTask("add_variables_physics");
  addRequiredPhysicsTask("add_ics_physics");
}

void
PoissonEq::addSolverVariables()
{
  const auto & variable = getParam<VariableName>("fem_potential");
  if (variableExists(variable, /*error_if_aux=*/true))
  {
    // External variable ownership is preserved, including its initial condition.
    if (isParamSetByUser("initial_potential_V"))
      paramError("initial_potential_V",
                 "An existing potential variable retains its externally defined IC.");
    return;
  }
  const std::string type = "MooseVariable";
  auto params = getFactory().getValidParams(type);
  assignBlocks(params, _blocks);
  params.set<SolverSystemName>("solver_sys") = getSolverSystem(variable);
  getProblem().addVariable(type, variable, params);
  _created_potential_variable = true;
}

void
PoissonEq::addInitialConditions()
{
  if (!_created_potential_variable)
    return;
  const auto & variable = getParam<VariableName>("fem_potential");
  if (!shouldCreateIC(variable, _blocks,
                      /*default IC*/ !isParamSetByUser("initial_potential_V"),
                      /*duplicate error*/ true))
    return;
  const std::string type = "ConstantIC";
  auto params = getFactory().getValidParams(type);
  params.set<VariableName>("variable") = variable;
  params.set<Real>("value") = getParam<Real>("initial_potential_V");
  assignBlocks(params, _blocks);
  getProblem().addInitialCondition(type, name() + "_initial_potential", params);
}

void
PoissonEq::checkIntegrity() const
{
  const auto & potential = getParam<VariableName>("fem_potential");
  if (!solverVariableExists(potential))
    paramError("fem_potential", "Electric potential variable was not found: ", potential);
  if (isVariableFV(potential))
    paramError("fem_potential",
               "Poisson fem_potential requires an FEM solver variable: ", potential);
  if (isParamValid("charge_source_material") || isParamValid("charge_source_functor"))
  {
    requireUniqueFEKernel("Diffusion", potential);
    requireUniqueFEKernel(
        isParamValid("charge_source_functor") ? "FunctorKernel" : "MatBodyForce",
        potential);
  }
}

void
PoissonEq::addFEKernels()
{
  if (!isParamValid("charge_source_material") &&
      !isParamValid("charge_source_functor"))
    return;
  const auto variable = getParam<VariableName>("fem_potential");
  {
    const std::string type = "Diffusion";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variable;
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_diffusion", params);
  }
  if (isParamValid("charge_source_functor"))
  {
    // rho_q/eps0 is an AD Functor and enters -laplacian(phi) on the RHS.
    // Use the same FunctorKernel sign convention as the chemistry source:
    // + integral(test * rho_q/eps0) is subtracted from the residual.
    const std::string type = "FunctorKernel";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variable;
    params.set<MooseFunctorName>("functor") =
        getParam<MooseFunctorName>("charge_source_functor");
    params.set<bool>("functor_on_rhs") = true;
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_charge_source", params);
  }
  else
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
PoissonEq::addFEBCs()
{
  if (!isParamValid("charge_source_material") &&
      !isParamValid("charge_source_functor"))
    return;
  for (const auto & boundary : getParam<std::vector<BoundaryName>>("ground_boundaries"))
  {
    const std::string type = "DirichletBC";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") =
        getParam<VariableName>("fem_potential");
    params.set<std::vector<BoundaryName>>("boundary") = {boundary};
    params.set<Real>("value") = 0;
    getProblem().addBoundaryCondition(type, name() + "_ground_" + boundary, params);
  }
}

}

using Plasma::PoissonEq;
registerPhysicsBaseTasks("PhysicsApp", PoissonEq);
registerMooseAction("PhysicsApp", PoissonEq, "add_variables_physics");
registerMooseAction("PhysicsApp", PoissonEq, "add_ics_physics");
registerMooseAction("PhysicsApp", PoissonEq, "check_integrity");
registerMooseAction("PhysicsApp", PoissonEq, "add_kernel");
registerMooseAction("PhysicsApp", PoissonEq, "add_bc");
