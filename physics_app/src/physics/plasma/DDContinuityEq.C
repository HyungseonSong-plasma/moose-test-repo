#include "DDContinuityEq.h"
#include "Chemistry.h"
#include "Physics.h"

#include <algorithm>
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
      "derivative and drift-diffusion Kernels; non-electron FV transport stays Native.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "FEM species IDs only; initial number densities [1/m^3] belong in species JSON.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Non-electron FVM species IDs only; initial number densities [1/m^3] belong in species JSON.");
  params.addParam<VariableName>(
      "fem_potential", "Potential used by existing finite-element drift-diffusion kernels.");
  return params;
}

DDContinuityEq::DDContinuityEq(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  // fem_species/fvm_species select species only. Initial values live in
  // Chemistry JSON and must not be duplicated as positional .i numbers.
  _fem_species = getParam<std::vector<std::string>>("fem_species");
  _fvm_species = getParam<std::vector<std::string>>("fvm_species");
  // Electron continuity is FEM-only. Preserve FVM variables, ICs and
  // transport coefficients for ions and other non-electron species.
  if (std::find(_fvm_species.begin(), _fvm_species.end(), "e") != _fvm_species.end())
    paramError("fvm_species",
               "Electron continuity is FEM-only; select e through fem_species.");
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

  // JSON automatically owns all selected DD species when any DD record exists.
  // A fully absent section preserves historical Native coefficients.
  // No front-end transport switch or implicit partial JSON fallback.
  if (chemistryData().hasDDTransport())
  {
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
                     "'. Specify model=constant, lookup, or functor.");
      }
    };
    validate(_fem_species, "fem_species", "FEM");
    validate(_fvm_species, "fvm_species", "FVM");
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
DDContinuityEq::addFunctorMaterials()
{
  // Material ownership follows exactly the FEM and FVM species listed by
  // Continuity, not a second species list or per-species .i Material blocks.
  // PlasmasAction loads JSON and resolves table_file relative to its JSON file.
  // Native FV equations remain external; generated coefficient Functors are
  // available to those FV operators without creating a duplicate equation.
  const auto & mechanism = chemistryData();
  std::vector<std::string> species = _fem_species;
  const auto & fvm = _fvm_species;
  species.insert(species.end(), fvm.begin(), fvm.end());

  for (const auto & id : species)
  {
    const auto * config = mechanism.ddTransport(id);
    if (!config)
      continue; // Existing Native coefficient owners remain during S6 parity migration.
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
registerMooseAction("PhysicsApp", DDContinuityEq, "add_functor_material");
