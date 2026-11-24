#include "DDContinuityEq.h"
#include "Chemistry.h"
#include "DDEnergyEq.h"
#include "Physics.h"
#include "FEProblemBase.h"
#include "NonlinearSystemBase.h"
#include "TheWarehouse.h"
#include "Attributes.h"
#include "FVKernel.h"
#include "FVBoundaryCondition.h"

#include <cctype>
#include <cmath>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>

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
      "derivative and drift-diffusion Kernels; selected FV species own explicit "
      "time, diffusion, drift, and Chemistry-source FV Kernels.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "FEM species IDs only; initial number densities [1/m^3] belong in species JSON.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "FVM species IDs only; initial number densities [1/m^3] belong in species JSON.");
  params.addParam<VariableName>(
      "fem_potential", "Potential for selected FEM and FVM drift-diffusion transport.");
  // Numerical wall gate control belongs to this MOOSE input, not species
  // Chemistry JSON. Default 0.0 and explicit 0.0 both choose hard max(x,0);
  // positive values enable the pre-existing smooth outward migration gate.
  params.addParam<Real>(
      "migration_smoothing_width",
      0.0,
      "Wall migration gate smoothing width [V/m]. Default 0 uses hard max(x,0); "
      "positive values enable smooth gating.");
  return params;
}

DDContinuityEq::DDContinuityEq(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  // fem_species/fvm_species select species only. Initial values live in
  // Chemistry JSON and must not be duplicated as positional .i numbers.
  _fem_species = getParam<std::vector<std::string>>("fem_species");
  _fvm_species = getParam<std::vector<std::string>>("fvm_species");
  const auto & fem = _fem_species;
  const auto & fvm = _fvm_species;
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

  // Every selected FEM/FVM continuity state must be explicitly initialized
  // by species.<id>.initial_number_density in Chemistry JSON. No fallback
  // to user-declared [Variables]/[ICs] or implicit zero state is supported.
  const auto & records = chemistryData().speciesRecords();
  const auto bind_json_initial = [this, &records](
      const std::vector<std::string> & selected,
      const std::string & option,
      std::map<std::string, Real> & destinations)
  {
    for (const auto & id : selected)
    {
      const auto found = records.find(id);
      if (found == records.end() || !found->second.initial_number_density)
        paramError(option,
                   "Selected species '", id,
                   "' requires species.", id,
                   ".initial_number_density in Chemistry JSON [1/m^3]; "
                   "external [Variables]/[ICs] cannot replace it.");
      destinations.emplace(id, *found->second.initial_number_density);
      saveSolverVariableName(continuityStateName(id));
    }
  };
  bind_json_initial(fem, "fem_species", _fem_initial_number_densities);
  bind_json_initial(fvm, "fvm_species", _fvm_initial_number_densities);
  addRequiredPhysicsTask("add_variables_physics");
  addRequiredPhysicsTask("add_ics_physics");

  // Selection is driven exclusively by fem_species/fvm_species and the JSON
  // species IDs, never by the presence of a Native kernel or an ownership mode.
  // Both FE and FV continuity generation require a complete explicit JSON
  // transport record; an absent section is not a Native-coefficient fallback.
  const auto & mechanism = chemistryData();
  // Optional for every Continuity instance. Invalid explicit values remain
  // errors rather than silently disabling the outward-only migration gate.
  const Real smoothing = getParam<Real>("migration_smoothing_width");
  if (!std::isfinite(smoothing) || smoothing < 0.0)
    paramError("migration_smoothing_width",
               "Ion wall migration smoothing must be finite and nonnegative [V/m].");
  // MOOSE's existing dont_create_kernels is a whole-Physics binding-only
  // control used by historical P2 IC tests, not an ion/Native ownership mode.
  // Without that explicit control, selected species always generate Kernels.
  const bool generate_kernels = !getParam<bool>("dont_create_kernels");
  const auto validate = [this, &mechanism](const std::vector<std::string> & ids,
                                            const std::string & option,
                                            const std::string & family)
  {
    for (const auto & id : ids)
    {
      (void)mechanism.species(id);
      if (!mechanism.ddTransport(id))
        paramError(option,
                   "Missing drift-diffusion transport JSON record for ",
                   family,
                   " species '",
                   id,
                   "'. Specify transport_coef=constant, lookup, or functor in species JSON.");
    }
  };
  if (generate_kernels || mechanism.hasDDTransport())
  {
    validate(_fem_species, "fem_species", "FEM");
    validate(_fvm_species, "fvm_species", "FVM");
  }

  // Selection itself activates generation. Potential is transport data, not
  // an ownership switch; never silently downgrade to binding-only mode.
  if (generate_kernels)
  {
    if (!isParamValid("fem_potential"))
      paramError("fem_potential",
                 "Selected fem_species/fvm_species require an explicit potential "
                 "for automatic FEM/FV drift-diffusion generation.");
  }

  // FV selection is the cutover decision: no Native presence probe, no owner
  // Enum, and no partially generated species equation.
  if (!fvm.empty() && generate_kernels)
  {
    if (!chemistryEnabled())
      paramError("fvm_species",
                 "FV species kernels require [Physics]/[Plasmas]/[Transport]/[Chemistry] "
                 "to generate species source functors.");
    for (const auto & id : fvm)
      if (!mechanism.hasSpeciesSource(id))
        paramError("fvm_species",
                   "Selected FV species '", id,
                   "' requires a nonzero volume reaction source in Chemistry JSON.");
  }
}

void
DDContinuityEq::addSolverVariables()
{
  // JSON is the sole initial-state owner; reject competing external variables/ICs.
  const auto generate = [this](const std::map<std::string, Real> & densities,
                               const bool finite_volume,
                               const std::string & option) {
    for (const auto & [species, density] : densities)
    {
      const auto variable = continuityStateName(species);
      if (variableExists(variable, /*error_if_aux=*/true))
        paramError(option,
                   "Species '", species, "' has JSON initial_number_density and an "
                   "existing solver variable '", variable,
                   "'. Remove the conflicting [Variables]/[ICs] declaration; "
                   "JSON is the sole initial-state owner.");
      const std::string type = finite_volume ? "MooseVariableFVReal" : "MooseVariable";
      auto params = getFactory().getValidParams(type);
      assignBlocks(params, _blocks);
      params.set<SolverSystemName>("solver_sys") = getSolverSystem(variable);
      getProblem().addVariable(type, variable, params);
    }
  };
  generate(_fem_initial_number_densities, false, "fem_species");
  generate(_fvm_initial_number_densities, true, "fvm_species");
}

void
DDContinuityEq::addInitialConditions()
{
  const auto generate = [this](const std::map<std::string, Real> & densities,
                               const bool finite_volume) {
    const std::string type = finite_volume ? "FVConstantIC" : "ConstantIC";
    for (const auto & [species, density] : densities)
    {
      const auto variable = continuityStateName(species);
      if (!shouldCreateIC(variable, _blocks,
                          /*whether IC is a default*/ false,
                          /*error if already an IC*/ true))
        continue;
      auto params = getFactory().getValidParams(type);
      params.set<VariableName>("variable") = variable;
      // Each solver log state stores ln(c_mol/m^3), not ln(n_particles/m^3).
      // Difference of logarithms avoids n/N_A underflow at small positive n.
      params.set<Real>("value") =
          std::log(density) - std::log(PHYSICS_CONSTANTS::N_A);
      assignBlocks(params, _blocks);
      if (finite_volume)
        getProblem().addFVInitialCondition(type, name() + "_" + species + "_density_ic", params);
      else
        getProblem().addInitialCondition(type, name() + "_" + species + "_density_ic", params);
    }
  };
  generate(_fem_initial_number_densities, false);
  generate(_fvm_initial_number_densities, true);
}


void
DDContinuityEq::checkIntegrity() const
{
  const auto & fem = _fem_species;
  const auto & fvm = _fvm_species;
  const auto variables = resolvedContinuityVariables(fem, fvm);
  validateExistingSpeciesVariables(fem, fvm, variables);
  if (getParam<bool>("dont_create_kernels"))
    return;
  for (std::size_t i = 0; i < fem.size(); ++i)
  {
    requireUniqueFEKernel("FEMLogMolarTimeDerivative", variables[i]);
    requireUniqueFEKernel("FEMLogMolarDriftDiffusion", variables[i]);
    if (chemistryEnabled() && chemistryData().hasSpeciesSource(fem[i]))
      requireUniqueFEKernel("FunctorKernel", variables[i]);
  }

  if (_fvm_species.empty())
    return;

  // MOOSE stores FV objects in TheWarehouse, not the FE KernelWarehouse.
  // These queries must run after the registered add_fv_kernel action. Check
  // both FV families; matching only the generated name would miss Native
  // residual objects with a different name on the same solver variable.
  const auto nl_number = getProblem().getNonlinearSystemBase(0).number();
  std::vector<FVKernel *> elemental;
  std::vector<FVKernel *> flux;
  auto & warehouse = getProblem().theWarehouse();
  warehouse.query()
      .condition<AttribSystem>("FVElementalKernel")
      .condition<AttribSysNum>(nl_number)
      .condition<AttribThread>(0)
      .queryInto(elemental);
  warehouse.query()
      .condition<AttribSystem>("FVFluxKernel")
      .condition<AttribSysNum>(nl_number)
      .condition<AttribThread>(0)
      .queryInto(flux);
  // queryInto clears its output. Preserve BOTH disjoint FV families.
  std::vector<FVKernel *> kernels = elemental;
  kernels.insert(kernels.end(), flux.begin(), flux.end());

  std::vector<FVBoundaryCondition *> flux_bcs;
  std::vector<FVBoundaryCondition *> dirichlet_bcs;
  warehouse.query()
      .condition<AttribSystem>("FVFluxBC")
      .condition<AttribSysNum>(nl_number)
      .condition<AttribThread>(0)
      .queryInto(flux_bcs);
  warehouse.query()
      .condition<AttribSystem>("FVDirichletBC")
      .condition<AttribSysNum>(nl_number)
      .condition<AttribThread>(0)
      .queryInto(dirichlet_bcs);
  std::vector<FVBoundaryCondition *> bcs = flux_bcs;
  bcs.insert(bcs.end(), dirichlet_bcs.begin(), dirichlet_bcs.end());

  for (const auto & id : _fvm_species)
  {
    const NonlinearVariableName variable = continuityStateName(id);
    const std::map<std::string, std::string> expected = {
        {id + "_time", "FVLogMolarTimeDerivative"},
        {id + "_diffusion", "FVLogMolarDiffusion"},
        {id + "_drift", "FVLogMolarElectrostaticDrift"},
        {id + "_source", "FVCoupledForce"}};
    std::map<std::string, unsigned int> matched;

    for (const auto * kernel : kernels)
    {
      const auto & parameters = kernel->parameters();
      if (!parameters.isParamValid("variable") ||
          parameters.get<NonlinearVariableName>("variable") != variable)
        continue;
      const auto expected_type = expected.find(kernel->name());
      if (expected_type == expected.end() || kernel->type() != expected_type->second)
        mooseError("P05 FV Native/Physics duplicate or unexpected owner on '",
                   variable, "': ", kernel->name(), " [", kernel->type(), "]");
      ++matched[kernel->name()];
    }
    for (const auto & [name, type] : expected)
      if (matched[name] != 1)
        mooseError("P05 missing or duplicate FV Kernel '", name,
                   "' [", type, "] on ", variable,
                   "; observed ", matched[name], ", expected exactly one.");

    // The selected species' JSON BC catalogue, not S6-specific suffixes or
    // a fixed count of four, defines the exact expected FV BC owners.
    // Any additional Native FV BC on the same solver state is rejected.
    std::map<std::string, std::string> expected_bcs;
    for (const auto & [group, boundary] : chemistryData().boundaries())
      for (const auto & [name, bc] : boundary.bcs)
        if (bc.variable == variable &&
            (bc.type == "FVFunctorNeumannBC" ||
             bc.type == "FVLogMolarDielectricFluxBC") &&
            !expected_bcs.emplace(name, bc.type).second)
          mooseError("P05 duplicate JSON FV BC owner for ", variable, ": ", name);
    std::map<std::string, unsigned int> matched_bcs;
    for (const auto * bc : bcs)
    {
      const auto & parameters = bc->parameters();
      if (!parameters.isParamValid("variable") ||
          parameters.get<NonlinearVariableName>("variable") != variable)
        continue;
      const auto expected_type = expected_bcs.find(bc->name());
      if (expected_type == expected_bcs.end() || bc->type() != expected_type->second)
        mooseError("P05 legacy, duplicate or unexpected FV BC on '", variable,
                   "': ", bc->name(), " [", bc->type(), "]");
      ++matched_bcs[bc->name()];
    }
    // C2 ions require a nonempty boundary catalogue, while transport-only
    // fixtures may intentionally have no BCs. Never accept a partial handoff.
    if (chemistryData().hasIonWalls() && expected_bcs.empty())
      mooseError("P05 missing JSON FV wall BC declarations for selected species ", id);
    for (const auto & [name, type] : expected_bcs)
      if (matched_bcs[name] != 1)
        mooseError("P05 partial or duplicate FV BC owner '", name,
                   "' [", type, "] on ", variable,
                   "; observed ", matched_bcs[name], ", expected exactly one.");
  }
}

void
DDContinuityEq::addFEKernels()
{
  const auto & species = _fem_species;
  const auto variables = resolvedContinuityVariables(species, _fvm_species);
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

void
DDContinuityEq::addFVKernels()
{
  if (_fvm_species.empty())
    return;

  // The selected fvm_species, not a detected Native owner or separate mode,
  // determines the four generated operators per species. The full old Native
  // 11-layer deck must be independently preflighted and stripped in Scratch.
  const auto & mechanism = chemistryData();
  const auto & potential = getParam<VariableName>("fem_potential");
  for (const auto & id : _fvm_species)
  {
    const NonlinearVariableName variable = continuityStateName(id);

    const std::string time_type = "FVLogMolarTimeDerivative";
    auto time_params = getFactory().getValidParams(time_type);
    time_params.set<NonlinearVariableName>("variable") = variable;
    assignBlocks(time_params, _blocks);
    getProblem().addFVKernel(time_type, id + "_time", time_params);

    const std::string diffusion_type = "FVLogMolarDiffusion";
    auto diffusion_params = getFactory().getValidParams(diffusion_type);
    diffusion_params.set<NonlinearVariableName>("variable") = variable;
    diffusion_params.set<MooseFunctorName>("coeff") = id + "_diffusivity";
    assignBlocks(diffusion_params, _blocks);
    getProblem().addFVKernel(diffusion_type, id + "_diffusion", diffusion_params);

    const std::string drift_type = "FVLogMolarElectrostaticDrift";
    auto drift_params = getFactory().getValidParams(drift_type);
    drift_params.set<NonlinearVariableName>("variable") = variable;
    drift_params.set<MooseFunctorName>("potential") = potential;
    drift_params.set<MooseFunctorName>("mobility") = id + "_mobility";
    drift_params.set<MooseFunctorName>("carrier") = "carrier_one";
    drift_params.set<Real>("charge_number") = mechanism.species(id).charge_number;
    // The Native S6 FV drift explicitly used upwind transport.
    drift_params.set<MooseEnum>("advected_interp_method") = "upwind";
    drift_params.set<bool>("use_element_gradient_for_potential") = true;
    // Retain the Native boundary-avoid contract using the ACTUAL typed FV
    // wall declarations. Do not hard-code S6 sidesets in the generic Kernel
    // or silently apply an interior drift operator on an ion wall face.
    std::set<BoundaryName> wall_sidesets;
    for (const auto & [group, boundary] : mechanism.boundaries())
      for (const auto & [bc_name, bc] : boundary.bcs)
        if (bc.variable == variable &&
            (bc.type == "FVFunctorNeumannBC" ||
             bc.type == "FVLogMolarDielectricFluxBC"))
          wall_sidesets.insert(boundary.mesh_boundaries.begin(),
                               boundary.mesh_boundaries.end());
    // The selected species' FV BC catalogue is the sole source of boundary
    // exclusion. Its cardinality is scenario-dependent; no S6-specific count.
    if (mechanism.hasIonWalls() && wall_sidesets.empty())
      mooseError("P14 FV wall BC catalogue has no drift boundaries for selected ion ", id);
    if (!wall_sidesets.empty())
      drift_params.set<std::vector<BoundaryName>>("boundaries_to_avoid") =
          std::vector<BoundaryName>(wall_sidesets.begin(), wall_sidesets.end());
    assignBlocks(drift_params, _blocks);
    getProblem().addFVKernel(drift_type, id + "_drift", drift_params);

    // Chemistry has already combined all EI/H contributions for this species
    // into one signed molar source S_<species>_molar. FVCoupledForce evaluates
    // that Functor with a single RHS sign (negative residual).
    const std::string source_type = "FVCoupledForce";
    auto source_params = getFactory().getValidParams(source_type);
    source_params.set<NonlinearVariableName>("variable") = variable;
    source_params.set<MooseFunctorName>("v") = "S_" + id + "_molar";
    source_params.set<Real>("coef") = 1.0;
    assignBlocks(source_params, _blocks);
    getProblem().addFVKernel(source_type, id + "_source", source_params);
  }
}

void
DDContinuityEq::addFunctorMaterials()
{
  // Material ownership follows exactly the FEM and FVM species listed by
  // Continuity, not a second species list or per-species .i Material blocks.
  // PlasmasAction loads JSON and resolves table_file relative to its JSON file.
  // Transport coefficients are supplied by validated JSON for every selected
  // species; FV kernel and BC cutover are separate P05/P14 gates.
  const auto & mechanism = chemistryData();
  std::vector<std::string> species = _fem_species;
  const auto & fvm = _fvm_species;
  species.insert(species.end(), fvm.begin(), fvm.end());

  // G2 opt-in: one live electron number-density owner belongs to the selected
  // Continuity state, not to a sheath-wall flag in DDEnergyEq. A new-only
  // Poisson JSON requires these four charged states even before G3 charge
  // producer and G4 Poisson residuals are activated.
  const bool poisson_density = mechanism.poisson() != nullptr;
  if (poisson_density)
  {
    if (getParam<bool>("dont_create_kernels"))
      paramError("dont_create_kernels",
                 "New-only Poisson density requires active Continuity state ownership.");
    const std::set<std::string> fem(_fem_species.begin(), _fem_species.end());
    const std::set<std::string> fvm(_fvm_species.begin(), _fvm_species.end());
    if (!fem.count("e"))
      paramError("fem_species", "New-only Poisson requires selected FEM electron e.");
    for (const auto & id : {"O2p", "Om", "Op"})
      if (!fvm.count(id))
        paramError("fvm_species", "New-only Poisson requires selected charged FV ion ", id);

    const std::string type = "ADParsedFunctorMaterial";
    auto density = getFactory().getValidParams(type);
    density.set<std::string>("property_name") = "n_e_physical";
    density.set<std::vector<std::string>>("functor_names") = {"log_e"};
    density.set<std::vector<std::string>>("functor_symbols") = {"c"};
    density.set<std::string>("expression") = "6.02214076e23*exp(c)";
    assignBlocks(density, _blocks);
    getProblem().addFunctorMaterial(type, name() + "_electron_number_density", density);
  }

  // C2 wall laws and future Poisson charge sources consume state-dependent,
  // canonical particle number densities from the SAME selected FV ions.
  // Preserve old Native n_i/n_m/n_op_physical aliases for unrelated consumers.
  if ((mechanism.hasIonWalls() || poisson_density) &&
      !getParam<bool>("dont_create_kernels"))
    for (const auto & id : _fvm_species)
    {
      if (!mechanism.species(id).ion_wall &&
          !(poisson_density && mechanism.species(id).charge_number != 0))
        continue;
      const std::string type = "ADParsedFunctorMaterial";
      auto params = getFactory().getValidParams(type);
      params.set<std::string>("property_name") = id + "_number_density";
      params.set<std::vector<std::string>>("functor_names") = {continuityStateName(id)};
      params.set<std::vector<std::string>>("functor_symbols") = {"log_c"};
      std::ostringstream number_scale;
      number_scale << std::setprecision(17) << PHYSICS_CONSTANTS::N_A;
      params.set<std::string>("expression") = number_scale.str() + "*exp(log_c)";
      assignBlocks(params, _blocks);
      getProblem().addFunctorMaterial(type, name() + "_" + id + "_number_density", params);
    }

  for (const auto & id : species)
  {
    const auto * config = mechanism.ddTransport(id);
    if (!config)
    {
      if (getParam<bool>("dont_create_kernels"))
        continue; // Explicit MOOSE-wide binding-only P2; no DD coefficient owner.
      mooseError("DDContinuityEq selected species '", id,
                 "' has no JSON transport record after constructor validation.");
    }
    const std::string type = "DDTransportMaterial";
    auto params = getFactory().getValidParams(type);
    params.set<std::string>("species_id") = id;
    // The backend and DDTransportMaterial share lookup/constant/functor modes.
    // "functor" consumes canonical species-owned AD coefficient providers;
    // "constant" requires explicit numerical coefficients in the JSON.
    params.set<MooseEnum>("model") = config->model;
    if (id == "e")
    {
      // Electron-energy transport is an [Energy] MOOSE decision, not a JSON
      // species field. The unique energy Action requests the fluid 5/3
      // closure from this shared electron DDTransportMaterial.
      const auto energy = _awh.getActions<Plasma::DDEnergyEq>();
      if (energy.size() > 1)
        mooseError("Multiple DDEnergyEq owners cannot select a unique electron transport closure");
      const bool fluid = energy.size() == 1 &&
          energy.front()->getParam<MooseEnum>("transport_coefficient") == "fluid";
      params.set<bool>("fluid_energy") = fluid;
    }
    if (config->model == "constant")
    {
      params.set<Real>("mobility") = config->mobility;
      params.set<Real>("diffusivity") = config->diffusivity;
    }
    else if (config->model == "functor")
    {
      // species.<id>.mobility/diffusivity now bind explicit upstream AD Functors,
      // never create new physical coefficients or select numerical constants.
      params.set<MooseFunctorName>("mobility_source") = config->mobility_source;
      params.set<MooseFunctorName>("diffusivity_source") = config->diffusivity_source;
    }
    else
    {
      params.set<FileName>("table_file") = config->table_file;
      params.set<MooseEnum>("table_units") = config->table_units;
      params.set<std::string>("bounds_policy") = config->bounds_policy;
      if (config->table_units == "reduced")
      {
        if (config->root_owned_gas && !rootGasStateEnabled())
          paramError("fem_species", "Object-shaped reduced transport_coef requires root "
                                   "[Plasmas] pressure and temperature.");
        params.set<MooseFunctorName>("pressure") =
            config->root_owned_gas || rootGasStateEnabled() ? "pressure" : config->pressure;
        params.set<MooseFunctorName>("gas_temperature") =
            config->root_owned_gas || rootGasStateEnabled() ? "temperature" : config->gas_temperature;
      }
    }
    assignBlocks(params, _blocks);
    getProblem().addFunctorMaterial(type, name() + "_" + id + "_transport_coefficients", params);
  }
}

} // namespace Plasma

using Plasma::DDContinuityEq;
registerPhysicsBaseTasks("PhysicsApp", DDContinuityEq);
registerMooseAction("PhysicsApp", DDContinuityEq, "add_variables_physics");
registerMooseAction("PhysicsApp", DDContinuityEq, "add_ics_physics");
registerMooseAction("PhysicsApp", DDContinuityEq, "check_integrity");
registerMooseAction("PhysicsApp", DDContinuityEq, "add_kernel");
registerMooseAction("PhysicsApp", DDContinuityEq, "add_fv_kernel");
registerMooseAction("PhysicsApp", DDContinuityEq, "add_functor_material");
