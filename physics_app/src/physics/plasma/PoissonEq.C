#include "PoissonEq.h"
#include "Chemistry.h"

#include <cmath>

namespace Plasma
{
namespace
{
std::vector<SubdomainName>
poissonBlocks(const PoissonRecord & model)
{
  std::vector<SubdomainName> blocks;
  for (const auto & [block, value] : model.relative_permittivity)
  {
    (void)value;
    blocks.emplace_back(block);
  }
  return blocks;
}
} // namespace

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
  // G4 New-only mode obtains all geometry and charge ownership from JSON.
  // Validation of these legacy options also happens before any new objects
  // are added; legacy without the JSON key retains its old API unchanged.
  saveSolverVariableName(getParam<VariableName>("fem_potential"));
  addRequiredPhysicsTask("add_variables_physics");
  addRequiredPhysicsTask("add_ics_physics");
}

void
PoissonEq::addSolverVariables()
{
  const auto & variable = getParam<VariableName>("fem_potential");
  if (const auto * model = chemistryData().poisson())
    if (isParamSetByUser("block"))
      paramError("block", "New-only Poisson block selection belongs exclusively to JSON.");
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
  if (const auto * model = chemistryData().poisson())
    assignBlocks(params, poissonBlocks(*model));
  else
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
  if (const auto * model = chemistryData().poisson())
    assignBlocks(params, poissonBlocks(*model));
  else
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
  if (chemistryData().poisson())
  {
    if (isParamSetByUser("block") || isParamValid("charge_source_material") ||
        isParamValid("charge_source_functor") ||
        isParamSetByUser("ground_boundaries"))
      paramError("fem_potential",
                 "New-only Poisson derives block, RHS and boundaries from the unified JSON; "
                 "do not supply legacy Poisson selector parameters.");
    if (getParam<bool>("dont_create_materials") || getParam<bool>("dont_create_kernels") ||
        getParam<bool>("dont_create_bcs"))
      paramError("fem_potential",
                 "New-only Poisson requires Material, Kernel and BC ownership.");
    requireUniqueFEKernel("ADMatDiffusion", potential);
    requireUniqueFEKernel("FunctorKernel", potential);
    return;
  }
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
  if (const auto * model = chemistryData().poisson())
  {
    const auto variable = getParam<VariableName>("fem_potential");
    {
      const std::string type = "ADMatDiffusion";
      auto params = getFactory().getValidParams(type);
      params.set<NonlinearVariableName>("variable") = variable;
      params.set<MaterialPropertyName>("diffusivity") = "relative_permittivity";
      assignBlocks(params, poissonBlocks(*model));
      getProblem().addKernel(type, name() + "_diffusion", params);
    }
    {
      const std::string type = "FunctorKernel";
      auto params = getFactory().getValidParams(type);
      params.set<NonlinearVariableName>("variable") = variable;
      params.set<MooseFunctorName>("functor") = "poisson_source";
      params.set<bool>("functor_on_rhs") = true;
      assignBlocks(params, {"plasma"});
      getProblem().addKernel(type, name() + "_charge_source", params);
    }
    return;
  }

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
  if (const auto * model = chemistryData().poisson())
  {
    // One DirichletBC over 11 sidesets, matching the Native C0 owner count.
    const std::string type = "DirichletBC";
    auto ground = getFactory().getValidParams(type);
    ground.set<NonlinearVariableName>("variable") =
        getParam<VariableName>("fem_potential");
    ground.set<Real>("value") = 0.0;
    std::vector<BoundaryName> ground_sides;
    for (const auto & side : model->ground_boundaries)
      ground_sides.emplace_back(side);
    ground.set<std::vector<BoundaryName>>("boundary") = ground_sides;
    getProblem().addBoundaryCondition(type, name() + "_grounded_potential", ground);

    // Lower-D sigma_* variables are preserved. They MUST be coupled
    // nonlinear variables, never reinterpreted as Functor names.
    for (const auto & [side, sigma] : model->surface_charge)
    {
      const std::string surface_type = "PhysicsADSurfaceChargePoissonBC";
      auto params = getFactory().getValidParams(surface_type);
      params.set<NonlinearVariableName>("variable") =
          getParam<VariableName>("fem_potential");
      params.set<std::vector<BoundaryName>>("boundary") = {side};
      params.set<std::vector<VariableName>>("surface_charge") = {sigma};
      getProblem().addBoundaryCondition(
          surface_type, name() + "_surface_charge_" + side, params);
    }
    return;
  }
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

void
PoissonEq::addMaterials()
{
  const auto * model = chemistryData().poisson();
  if (!model)
    return;

  // The five native AD Material objects cover eight volume blocks.
  // Keep plasma=1 separate from vacuum/coil=1 to preserve exact ownership.
  struct MaterialGroup
  {
    const char * id;
    std::vector<SubdomainName> blocks;
  };
  const std::vector<MaterialGroup> groups = {
      {"plasma", {"plasma"}},
      {"cover", {"cover"}},
      {"wafer", {"wafer"}},
      {"focus_ring", {"focus_ring"}},
      {"vacuum", {"vacuum", "coil1", "coil2", "coil3"}}};
  for (const auto & group : groups)
  {
    const std::string type = "ADGenericConstantMaterial";
    auto params = getFactory().getValidParams(type);
    const auto epsilon = model->relative_permittivity.at(group.id);
    params.set<std::vector<std::string>>("prop_names") = {"relative_permittivity"};
    params.set<std::vector<Real>>("prop_values") = {epsilon};
    params.set<std::vector<SubdomainName>>("block") = group.blocks;
    getProblem().addMaterial(type, name() + "_eps_" + group.id, params);
  }
}

} // namespace Plasma

using Plasma::PoissonEq;
registerPhysicsBaseTasks("PhysicsApp", PoissonEq);
registerMooseAction("PhysicsApp", PoissonEq, "add_variables_physics");
registerMooseAction("PhysicsApp", PoissonEq, "add_ics_physics");
registerMooseAction("PhysicsApp", PoissonEq, "check_integrity");
registerMooseAction("PhysicsApp", PoissonEq, "add_kernel");
registerMooseAction("PhysicsApp", PoissonEq, "add_bc");
registerMooseAction("PhysicsApp", PoissonEq, "add_materials_physics");
