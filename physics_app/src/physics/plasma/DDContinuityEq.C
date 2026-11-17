#include "DDContinuityEq.h"
#include "Chemistry.h"
#include "Physics.h"

#include <cctype>
#include <cmath>
#include <map>
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
      "derivative and drift-diffusion Kernels; selected FV species own explicit "
      "time, diffusion, drift, and Chemistry-source FV Kernels.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "FEM species IDs only; initial number densities [1/m^3] belong in species JSON.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "FVM species IDs only; initial number densities [1/m^3] belong in species JSON.");
  params.addParam<VariableName>(
      "fem_potential", "Potential for selected FEM and FVM drift-diffusion transport.");
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
  validate(_fem_species, "fem_species", "FEM");
  validate(_fvm_species, "fvm_species", "FVM");

  // Selection itself activates generation. Potential is transport data, not
  // an ownership switch; never silently downgrade to binding-only mode.
  if (!isParamValid("fem_potential"))
    paramError("fem_potential",
               "Selected fem_species/fvm_species require an explicit potential "
               "for automatic FEM/FV drift-diffusion generation.");

  // FV selection is the cutover decision: no Native presence probe, no owner
  // Enum, and no partially generated species equation.
  if (!fvm.empty())
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
    drift_params.set<bool>("use_element_gradient_for_potential") = true;
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

  for (const auto & id : species)
  {
    const auto * config = mechanism.ddTransport(id);
    if (!config)
      mooseError("DDContinuityEq selected species '", id,
                 "' has no JSON transport record after constructor validation.");
    const std::string type = "DDTransportMaterial";
    auto params = getFactory().getValidParams(type);
    params.set<std::string>("species_id") = id;
    // The backend and DDTransportMaterial share lookup/constant/functor modes.
    // "functor" consumes canonical species-owned AD coefficient providers;
    // "constant" requires explicit numerical coefficients in the JSON.
    params.set<MooseEnum>("model") = config->model;
    if (id == "e")
      params.set<bool>("fluid_energy") = mechanism.fluidElectronEnergyTransport();
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
        params.set<MooseFunctorName>("pressure") = rootGasStateEnabled() ? "pressure" : config->pressure;
        params.set<MooseFunctorName>("gas_temperature") = rootGasStateEnabled() ? "temperature" : config->gas_temperature;
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
