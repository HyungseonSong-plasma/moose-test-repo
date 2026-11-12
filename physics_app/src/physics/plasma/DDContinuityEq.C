#include "DDContinuityEq.h"
#include "Chemistry.h"
#include "Physics.h"

#include <cerrno>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <map>
#include <set>
#include <stdexcept>

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

struct ParsedSpeciesInput
{
  std::vector<std::string> names;
  std::map<std::string, Real> initial_number_densities;
};

bool
startsNumber(const std::string & token)
{
  if (token.empty())
    return false;
  char * end = nullptr;
  (void)std::strtod(token.c_str(), &end);
  return end != token.c_str() || token[0] == '+' || token[0] == '-' || token[0] == '.';
}

// Legacy names-only form remains external-variable binding. New form alternates
// species_name and initial_number_density [1/m^3], with no arbitrary floor.
ParsedSpeciesInput
parseSpeciesInput(const std::vector<std::string> & tokens, const std::string & option)
{
  ParsedSpeciesInput result;
  if (tokens.empty())
    return result;
  const bool paired = tokens.size() > 1 && startsNumber(tokens[1]);
  if (!paired)
  {
    result.names = tokens;
    return result;
  }
  if (tokens.size() % 2 != 0)
    throw std::invalid_argument(option + ": expected species_name initial_number_density pairs");

  for (std::size_t i = 0; i < tokens.size(); i += 2)
  {
    const auto & species = tokens[i];
    const auto & density_token = tokens[i + 1];
    char * end = nullptr;
    errno = 0;
    const Real number_density = std::strtod(density_token.c_str(), &end);
    if (end == density_token.c_str() || *end != '\0' || errno == ERANGE ||
        !std::isfinite(number_density) || !(number_density > 0.0))
      throw std::invalid_argument(option + ": " + species +
                                  " requires a finite, strictly positive "
                                  "initial_number_density [1/m^3]");
    result.names.push_back(species);
    result.initial_number_densities.emplace(species, number_density);
  }
  return result;
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
      "fem_species", {}, "Species names, optionally followed by positive initial_number_density [1/m^3] for each species.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Species names, optionally followed by positive initial_number_density [1/m^3] for each species.");
  params.addParam<VariableName>(
      "fem_potential", "Potential used by existing finite-element drift-diffusion kernels.");
  return params;
}

DDContinuityEq::DDContinuityEq(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  try
  {
    const auto fem_input = parseSpeciesInput(
        getParam<std::vector<std::string>>("fem_species"), "fem_species");
    const auto fvm_input = parseSpeciesInput(
        getParam<std::vector<std::string>>("fvm_species"), "fvm_species");
    _fem_species = fem_input.names;
    _fvm_species = fvm_input.names;
    _fem_initial_number_densities = fem_input.initial_number_densities;
    _fvm_initial_number_densities = fvm_input.initial_number_densities;
  }
  catch (const std::invalid_argument & error)
  {
    paramError("fem_species", error.what());
  }
  const auto & fem = _fem_species;
  const auto & fvm = _fvm_species;
  const auto variables = resolvedContinuityVariables(fem, fvm);
  for (const auto & [id, density] : _fem_initial_number_densities)
    saveSolverVariableName(continuityStateName(id));
  for (const auto & [id, density] : _fvm_initial_number_densities)
    saveSolverVariableName(continuityStateName(id));

  if (!_fem_initial_number_densities.empty() || !_fvm_initial_number_densities.empty())
  {
    addRequiredPhysicsTask("add_variables_physics");
    addRequiredPhysicsTask("add_ics_physics");
  }
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
  // This task runs after user-authored [Variables], so an explicitly supplied
  // number density cannot silently override a Native variable or its IC.
  const auto generate = [this](const std::map<std::string, Real> & densities,
                               const bool finite_volume,
                               const std::string & option) {
    for (const auto & [species, density] : densities)
    {
      const auto variable = continuityStateName(species);
      if (variableExists(variable, /*error_if_aux=*/true))
        paramError(option,
                   "Density-paired species '", species,
                   "' already has a solver variable '", variable,
                   "'. Remove its [Variables] declaration, or use the legacy "
                   "species-name-only form with externally owned initial conditions.");
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
    const std::string type = "DDMaterial";
    auto params = getFactory().getValidParams(type);
    params.set<std::string>("species_id") = id;
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
      // DDMaterial derives the existing canonical species Functor names.
      // No source-name overrides are passed from the generated JSON.
    }
    else
    {
      params.set<FileName>("table_file") = config->table_file;
      params.set<MooseEnum>("table_units") = config->table_units;
      params.set<std::string>("bounds_policy") = config->bounds_policy;
      if (config->table_units == "reduced")
      {
        params.set<MooseFunctorName>("pressure") = config->pressure;
        params.set<MooseFunctorName>("gas_temperature") = config->gas_temperature;
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
