#include "DDEnergyEq.h"
#include "Chemistry.h"
#include "Physics.h"

#include <cmath>

namespace Plasma
{
namespace
{
// Every drift-diffusion species uses one internally resolved energy state.
// The MOOSE [Energy] block deliberately exposes no "variable" option.
VariableName
energyStateName(const std::string & species)
{
  return "log_" + species + "_energy";
}
} // namespace

InputParameters
DDEnergyEq::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Create or reuse the FEM electron log-molar energy state. With fem_potential, "
      "assemble the complete conservative electron energy equation.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "Electron species solved with finite-element variables.");
  params.addParam<VariableName>(
      "fem_potential",
      "FEM electric potential. Enables conservative energy time, drift-diffusion, "
      "electron Joule and canonical mean-energy/JSON-wall providers.");
  params.addParam<MaterialPropertyName>(
      "rf_heating_material", "Existing electron-energy heating source in the equation's units.");
  params.addParam<Real>(
      "initial_molar_energy_density_eV",
      "Required when auto-creating log_e_energy: exp(log_e_energy) [eV mol/m^3], >0.");
  return params;
}

DDEnergyEq::DDEnergyEq(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  const auto & finite_element_species = getParam<std::vector<std::string>>("fem_species");
  if (finite_element_species.size() != 1 || finite_element_species.front() != "e")
    paramError("fem_species", "Electron energy requires fem_species = 'e'.");

  validateSpeciesInputs(finite_element_species,
                        {},
                        {energyStateName(finite_element_species.front())});
  if (isParamValid("initial_molar_energy_density_eV"))
  {
    const Real initial = getParam<Real>("initial_molar_energy_density_eV");
    if (!std::isfinite(initial) || initial <= 0.0)
      paramError("initial_molar_energy_density_eV",
                 "Initial molar energy density must be finite and strictly positive.");
  }
  if (isParamValid("fem_potential"))
  {
    if (getParam<VariableName>("fem_potential").empty())
      paramError("fem_potential", "Full FEM electron energy requires a nonempty potential.");
    const auto & mechanism = chemistryData();
    if (!mechanism.ddTransport("e") || !mechanism.fluidElectronEnergyTransport())
      paramError("fem_potential",
                 "Full FEM electron energy requires JSON drift_diffusion.e coefficients "
                 "and drift_diffusion.e_energy={type:fluid}.");
  }
  saveSolverVariableName(energyStateName("e"));
  addRequiredPhysicsTask("add_variables_physics");
  addRequiredPhysicsTask("add_ics_physics");
}

void
DDEnergyEq::addSolverVariables()
{
  const auto variable = energyStateName("e");
  if (variableExists(variable, /*error_if_aux=*/true))
  {
    if (isParamValid("initial_molar_energy_density_eV"))
      paramError("initial_molar_energy_density_eV",
                 "An externally declared log_e_energy retains its own initial condition.");
    return;
  }
  if (!isParamValid("initial_molar_energy_density_eV"))
    paramError("initial_molar_energy_density_eV",
               "Auto-created log_e_energy requires an explicit positive initial molar "
               "energy density [eV mol/m^3].");

  const std::string type = "MooseVariable";
  auto params = getFactory().getValidParams(type);
  assignBlocks(params, _blocks);
  params.set<SolverSystemName>("solver_sys") = getSolverSystem(variable);
  getProblem().addVariable(type, variable, params);
  _created_energy_variable = true;
}

void
DDEnergyEq::addInitialConditions()
{
  if (!_created_energy_variable)
    return;
  const auto variable = energyStateName("e");
  if (!shouldCreateIC(variable, _blocks, /*default IC*/ false, /*duplicate error*/ true))
    return;
  const std::string type = "ConstantIC";
  auto params = getFactory().getValidParams(type);
  params.set<VariableName>("variable") = variable;
  // The solved state is log of molar energy density, not log(number density).
  params.set<Real>("value") = std::log(getParam<Real>("initial_molar_energy_density_eV"));
  assignBlocks(params, _blocks);
  getProblem().addInitialCondition(type, name() + "_initial_energy", params);
}

void
DDEnergyEq::checkIntegrity() const
{
  const auto variable = energyStateName(getParam<std::vector<std::string>>("fem_species").front());
  validateExistingSpeciesVariables(getParam<std::vector<std::string>>("fem_species"),
                                   {},
                                   {variable});
  if (isParamValid("fem_potential"))
  {
    const auto & potential = getParam<VariableName>("fem_potential");
    if (!solverVariableExists(potential) || isVariableFV(potential))
      paramError("fem_potential", "A FEM potential solver variable must exist: ", potential);
    if (!solverVariableExists("log_e") || isVariableFV("log_e"))
      paramError("fem_species", "Full electron energy requires FEM log_e from Continuity.");
    requireUniqueFEKernel("FEMLogMolarTimeDerivative", variable);
    requireUniqueFEKernel("FEMLogMolarDriftDiffusion", variable);
    requireUniqueFEKernel("FEMLogMolarElectronJouleHeating", variable);
  }
  if (isParamValid("rf_heating_material"))
    requireUniqueFEKernel("MatBodyForce", variable);
  if (chemistryEnabled() && chemistryData().hasElectronEnergySource())
    requireUniqueFEKernel("FunctorKernel", variable);
}

void
DDEnergyEq::addFEKernels()
{
  const auto variable = energyStateName(getParam<std::vector<std::string>>("fem_species").front());
  if (isParamValid("fem_potential"))
  {
    const auto & potential = getParam<VariableName>("fem_potential");
    const std::string time_type = "FEMLogMolarTimeDerivative";
    auto time = getFactory().getValidParams(time_type);
    time.set<NonlinearVariableName>("variable") = variable;
    assignBlocks(time, _blocks);
    getProblem().addKernel(time_type, name() + "_time", time);

    // Fluid energy flux uses the same charge sign as electron number flux,
    // with the 5/3 closure projected by the unique DDTransportMaterial.
    const std::string transport_type = "FEMLogMolarDriftDiffusion";
    auto transport = getFactory().getValidParams(transport_type);
    transport.set<NonlinearVariableName>("variable") = variable;
    transport.set<std::vector<VariableName>>("potential") = {potential};
    transport.set<MooseFunctorName>("mobility") = "e_energy_mobility";
    transport.set<MooseFunctorName>("diffusion") = "e_energy_diffusivity";
    transport.set<Real>("charge_number") = chemistryData().species("e").charge_number;
    assignBlocks(transport, _blocks);
    getProblem().addKernel(transport_type, name() + "_transport", transport);

    // Existing FEM kernel carries electron electric work in the original
    // eV mol/(m^3 s) log-molar convention; never insert a new Joule law.
    const std::string joule_type = "FEMLogMolarElectronJouleHeating";
    auto joule = getFactory().getValidParams(joule_type);
    joule.set<NonlinearVariableName>("variable") = variable;
    joule.set<std::vector<VariableName>>("electron_log_density") = {"log_e"};
    joule.set<std::vector<VariableName>>("potential") = {potential};
    joule.set<MooseFunctorName>("mobility") = "e_mobility";
    joule.set<MooseFunctorName>("diffusion") = "e_diffusivity";
    assignBlocks(joule, _blocks);
    getProblem().addKernel(joule_type, name() + "_joule", joule);
  }
  if (isParamValid("rf_heating_material"))
  {
    const std::string type = "MatBodyForce";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variable;
    params.set<MaterialPropertyName>("material_property") =
        getParam<MaterialPropertyName>("rf_heating_material");
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_rf_heating", params);
  }

  if (chemistryEnabled() && chemistryData().hasElectronEnergySource())
  {
    // Chemistry first collects all reaction channels from [Plasmas]/files,
    // preserving a separate progress R_k and signed electron energy change
    // delta_epsilon_k for each reaction ID (including identical equations).
    // It sums delta_epsilon_k * R_k into the single Q_e_molar_eV Functor.
    // Connect that total once on the RHS: never create per-reaction Kernels,
    // reverse its sign, or apply an implicit energy-unit conversion here.
    const std::string type = "FunctorKernel";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variable;
    params.set<MooseFunctorName>("functor") = "Q_e_molar_eV";
    params.set<bool>("functor_on_rhs") = true;
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_chemistry_energy", params);
  }

}

void
DDEnergyEq::addFunctorMaterials()
{
  // Legacy partial-input mode does not create duplicate mean-energy owners.
  if (!isParamValid("fem_potential"))
    return;

  // Canonical state conversion, once per complete electron-energy equation.
  const std::string mean_type = "ElectronEnergyMaterial";
  auto mean = getFactory().getValidParams(mean_type);
  mean.set<MooseEnum>("state_form") = "log_molar_eV";
  mean.set<MooseFunctorName>("electron_energy_density") = "log_e_energy";
  mean.set<MooseFunctorName>("electron_density") = "log_e";
  assignBlocks(mean, _blocks);
  getProblem().addFunctorMaterial(mean_type, name() + "_mean_energy", mean);

  // JSON declares which existing sheath BCs are used; the physical flux
  // calculation stays exclusively inside ESWallFluxMaterial.C.
  bool sheath_wall = false;
  for (const auto & [group, boundary] : chemistryData().boundaries())
    for (const auto & [bc_name, bc] : boundary.bcs)
    {
      (void)group;
      (void)bc_name;
      if (bc.type != "FEMElectronSheathBC" &&
          bc.type != "FEMElectronEnergySheathBC")
        continue;
      if (bc.wall_number_flux != "electron_wall_number_flux" ||
          (bc.type == "FEMElectronEnergySheathBC" && bc.mean_energy != "e_energy_eV"))
        paramError("fem_potential",
                   "Automatic JSON electron sheath BCs require canonical "
                   "electron_wall_number_flux and e_energy_eV providers.");
      sheath_wall = true;
    }
  if (!sheath_wall)
    return;

  // The FEM state log_e stores ln(c_e [mol/m^3]); sheath physics consumes
  // number density [1/m^3]. Construct a state-dependent AD Functor, not a
  // constant value or another wall-flux implementation.
  const std::string density_type = "ADParsedFunctorMaterial";
  auto density = getFactory().getValidParams(density_type);
  density.set<std::string>("property_name") = "n_e_physical";
  density.set<std::vector<std::string>>("functor_names") = {"log_e"};
  density.set<std::vector<std::string>>("functor_symbols") = {"c"};
  density.set<std::string>("expression") = "6.02214076e23*exp(c)";
  assignBlocks(density, _blocks);
  getProblem().addFunctorMaterial(density_type, name() + "_number_density", density);

  const std::string wall_type = "ESWallFluxMaterial";
  auto wall = getFactory().getValidParams(wall_type);
  wall.set<MooseFunctorName>("electron_density") = "n_e_physical";
  wall.set<MooseFunctorName>("mean_energy") = "e_energy_eV";
  wall.set<MooseFunctorName>("potential") = getParam<VariableName>("fem_potential");
  wall.set<bool>("use_element_gradient_for_potential") = true;
  assignBlocks(wall, _blocks);
  getProblem().addFunctorMaterial(wall_type, name() + "_sheath_wall_flux", wall);
}

}

using Plasma::DDEnergyEq;
registerPhysicsBaseTasks("PhysicsApp", DDEnergyEq);
registerMooseAction("PhysicsApp", DDEnergyEq, "add_variables_physics");
registerMooseAction("PhysicsApp", DDEnergyEq, "add_ics_physics");
registerMooseAction("PhysicsApp", DDEnergyEq, "check_integrity");
registerMooseAction("PhysicsApp", DDEnergyEq, "add_kernel");
registerMooseAction("PhysicsApp", DDEnergyEq, "add_functor_material");
