#include "GummelIterationAction.h"

#include "FEProblemBase.h"
#include "Factory.h"

#include <cstddef>
#include <string>

registerMooseAction("PhysicsApp", GummelIterationAction, "add_multi_app");
registerMooseAction("PhysicsApp", GummelIterationAction, "add_transfer");
registerMooseAction("PhysicsApp", GummelIterationAction, "add_convergence");

InputParameters
GummelIterationAction::validParams()
{
  InputParameters params = Action::validParams();
  params.addClassDescription(
      "Builds a model-agnostic Gummel coupling. In two-sub-application mode sibling electron "
      "and Poisson MultiApps exchange n_e and phi directly. Optional parent mappings allow a "
      "dedicated driver to hold a frozen heavy-state snapshot and collect converged fast state. "
      "Legacy current-application electron coupling remains supported.");

  params.addParam<FileName>(
      "electron_input_file",
      "Optional input file for an electron sub-application. When supplied, the Action creates "
      "sibling electron and Poisson MultiApps and transfers directly between them.");
  params.addParam<MultiAppName>(
      "electron_multiapp", "electron", "Name of the electron MultiApp in two-sub-application mode.");
  params.addParam<std::string>(
      "electron_multiapp_type",
      "TransientMultiApp",
      "MOOSE MultiApp type used for the electron solve.");
  params.addRequiredParam<FileName>(
      "poisson_input_file", "Input file for the Poisson sub-application.");
  params.addRequiredParam<MultiAppName>(
      "poisson_multiapp", "Name of the Poisson MultiApp created by this Action.");
  params.addParam<std::string>(
      "poisson_multiapp_type",
      "TransientMultiApp",
      "MOOSE MultiApp type used for the Poisson solve.");
  params.addParam<bool>(
      "no_restore",
      true,
      "Disable restore between fixed-point iterations so sub-applications retain their current "
      "iterates.");
  params.addRangeCheckedParam<Real>(
      "relaxation_factor",
      1.0,
      "relaxation_factor>0 & relaxation_factor<2",
      "Relaxation factor applied to the Poisson MultiApp transformed variables.");
  params.addParam<std::vector<std::string>>(
      "poisson_transformed_variables",
      {},
      "Poisson sub-application variables transformed by the MOOSE fixed-point algorithm.");

  params.addParam<VariableName>(
      "electron_density_variable",
      "n_e",
      "Electron-sub-application solved density variable copied to Poisson.");
  params.addParam<AuxVariableName>(
      "poisson_electron_density_variable",
      "n_e",
      "Poisson-sub-application auxiliary density receiving the electron solution.");
  params.addParam<VariableName>(
      "poisson_potential_variable",
      "phi",
      "Poisson-sub-application solved potential copied to the electron application.");
  params.addParam<AuxVariableName>(
      "electron_potential_variable",
      "phi",
      "Electron-sub-application auxiliary potential receiving the Poisson solution.");

  params.addParam<MooseEnum>(
      "potential_transfer_mode",
      MooseEnum("direct_sibling through_parent", "direct_sibling"),
      "Potential coupling path. direct_sibling copies Poisson potential directly to the electron "
      "sub-application. through_parent copies Poisson potential to a parent/driver auxiliary "
      "variable and then from that driver variable to electron, so parent-level fixed-point "
      "acceleration can transform the potential before the next electron solve.");
  params.addParam<AuxVariableName>(
      "parent_potential_variable",
      "phi_from_poisson",
      "Parent/driver auxiliary potential used when potential_transfer_mode=through_parent.");

  params.addParam<std::vector<VariableName>>(
      "electron_state_variables",
      {},
      "Descriptive list of electron state variables. The Action does not construct their equations.");

  params.addParam<std::vector<VariableName>>(
      "electron_to_poisson_source_variables",
      {},
      "Additional variables copied from the electron subsystem to Poisson.");
  params.addParam<std::vector<AuxVariableName>>(
      "electron_to_poisson_variables",
      {},
      "Additional Poisson auxiliary targets corresponding one-to-one with "
      "electron_to_poisson_source_variables.");
  params.addParam<std::vector<VariableName>>(
      "poisson_to_electron_source_variables",
      {},
      "Additional variables copied from Poisson back to the electron subsystem.");
  params.addParam<std::vector<AuxVariableName>>(
      "poisson_to_electron_variables",
      {},
      "Additional electron auxiliary targets corresponding one-to-one with "
      "poisson_to_electron_source_variables.");

  params.addParam<std::vector<VariableName>>(
      "parent_to_electron_source_variables",
      {},
      "Parent-application variables copied to the electron sub-application before its solve.");
  params.addParam<std::vector<AuxVariableName>>(
      "parent_to_electron_variables",
      {},
      "Electron auxiliary targets corresponding one-to-one with "
      "parent_to_electron_source_variables.");
  params.addParam<std::vector<VariableName>>(
      "electron_to_parent_source_variables",
      {},
      "Electron-sub-application variables copied back to parent auxiliary variables after its solve.");
  params.addParam<std::vector<AuxVariableName>>(
      "electron_to_parent_variables",
      {},
      "Parent auxiliary targets corresponding one-to-one with "
      "electron_to_parent_source_variables.");
  params.addParam<std::vector<VariableName>>(
      "parent_to_poisson_source_variables",
      {},
      "Parent-application variables copied to the Poisson sub-application before its solve.");
  params.addParam<std::vector<AuxVariableName>>(
      "parent_to_poisson_variables",
      {},
      "Poisson auxiliary targets corresponding one-to-one with "
      "parent_to_poisson_source_variables.");
  params.addParam<std::vector<VariableName>>(
      "poisson_to_parent_source_variables",
      {},
      "Poisson-sub-application variables copied back to parent auxiliary variables after its solve.");
  params.addParam<std::vector<AuxVariableName>>(
      "poisson_to_parent_variables",
      {},
      "Parent auxiliary targets corresponding one-to-one with "
      "poisson_to_parent_source_variables.");

  params.addParam<bool>(
      "manage_convergence",
      true,
      "Create a DeltaPhiMultiAppConvergence object for this Gummel iteration. The parent "
      "Executioner must select it with multiapp_fixed_point_convergence.");
  params.addParam<PostprocessorName>(
      "delta_phi_postprocessor",
      "Parent-application postprocessor containing the maximum potential change for the current "
      "fixed-point iterate.");
  params.addRangeCheckedParam<Real>(
      "delta_phi_abs_tol",
      1.0e-6,
      "delta_phi_abs_tol>0",
      "Absolute potential-change convergence tolerance [V].");
  params.addParam<ConvergenceName>(
      "convergence_name",
      "gummel_delta_phi",
      "Name of the convergence object created when manage_convergence=true.");

  return params;
}

GummelIterationAction::GummelIterationAction(const InputParameters & parameters)
  : Action(parameters)
{
  checkVariableMaps();

  if (getParam<bool>("manage_convergence") && !isParamValid("delta_phi_postprocessor"))
    paramError("delta_phi_postprocessor",
               "This parameter is required when manage_convergence=true.");
}

bool
GummelIterationAction::usesElectronSubApp() const
{
  return isParamValid("electron_input_file");
}

void
GummelIterationAction::checkVariableMaps() const
{
  const auto & e_src =
      getParam<std::vector<VariableName>>("electron_to_poisson_source_variables");
  const auto & e_dst =
      getParam<std::vector<AuxVariableName>>("electron_to_poisson_variables");
  const auto & p_src =
      getParam<std::vector<VariableName>>("poisson_to_electron_source_variables");
  const auto & p_dst =
      getParam<std::vector<AuxVariableName>>("poisson_to_electron_variables");
  const auto & parent_e_src =
      getParam<std::vector<VariableName>>("parent_to_electron_source_variables");
  const auto & parent_e_dst =
      getParam<std::vector<AuxVariableName>>("parent_to_electron_variables");
  const auto & e_parent_src =
      getParam<std::vector<VariableName>>("electron_to_parent_source_variables");
  const auto & e_parent_dst =
      getParam<std::vector<AuxVariableName>>("electron_to_parent_variables");
  const auto & parent_p_src =
      getParam<std::vector<VariableName>>("parent_to_poisson_source_variables");
  const auto & parent_p_dst =
      getParam<std::vector<AuxVariableName>>("parent_to_poisson_variables");
  const auto & p_parent_src =
      getParam<std::vector<VariableName>>("poisson_to_parent_source_variables");
  const auto & p_parent_dst =
      getParam<std::vector<AuxVariableName>>("poisson_to_parent_variables");

  if (e_src.size() != e_dst.size())
    paramError("electron_to_poisson_variables",
               "The electron-to-Poisson source and target lists must have the same length.");
  if (p_src.size() != p_dst.size())
    paramError("poisson_to_electron_variables",
               "The Poisson-to-electron source and target lists must have the same length.");
  if (parent_e_src.size() != parent_e_dst.size())
    paramError("parent_to_electron_variables",
               "The parent-to-electron source and target lists must have the same length.");
  if (e_parent_src.size() != e_parent_dst.size())
    paramError("electron_to_parent_variables",
               "The electron-to-parent source and target lists must have the same length.");
  if (parent_p_src.size() != parent_p_dst.size())
    paramError("parent_to_poisson_variables",
               "The parent-to-Poisson source and target lists must have the same length.");
  if (p_parent_src.size() != p_parent_dst.size())
    paramError("poisson_to_parent_variables",
               "The Poisson-to-parent source and target lists must have the same length.");

  if (usesElectronSubApp())
  {
    if (getParam<MultiAppName>("electron_multiapp") == getParam<MultiAppName>("poisson_multiapp"))
      paramError("electron_multiapp",
                 "electron_multiapp and poisson_multiapp must have different names.");

    // Pinned MOOSE executes sibling BETWEEN_MULTIAPP transfers before the MultiApps on a
    // given execution flag.  The Action therefore staggers the sibling solves across
    // TIMESTEP_BEGIN/TIMESTEP_END instead of relying on newer execution-order-group behavior.
  }
  else
  {
    if (e_src.empty())
      paramError("electron_to_poisson_source_variables",
                 "Legacy current-application electron mode requires at least one "
                 "electron-to-Poisson mapping.");
    if (p_src.empty())
      paramError("poisson_to_electron_source_variables",
                 "Legacy current-application electron mode requires at least one "
                 "Poisson-to-electron mapping.");
    if (!parent_e_src.empty() || !e_parent_src.empty() || !parent_p_src.empty() ||
        !p_parent_src.empty())
      paramError("electron_input_file",
                 "Parent-state mappings are only valid in two-sub-application sibling mode.");
  }
}

void
GummelIterationAction::act()
{
  const auto & poisson_name = getParam<MultiAppName>("poisson_multiapp");
  const std::string object_prefix = std::string(poisson_name) + "_gummel";

  if (_current_task == "add_multi_app")
  {
    if (usesElectronSubApp())
    {
      const auto & electron_name = getParam<MultiAppName>("electron_multiapp");
      const auto & electron_type = getParam<std::string>("electron_multiapp_type");
      auto electron_params = _factory.getValidParams(electron_type);
      electron_params.set<std::vector<FileName>>("input_files") =
          {getParam<FileName>("electron_input_file")};
      electron_params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_BEGIN;
      electron_params.set<bool>("no_restore") = getParam<bool>("no_restore");

      _problem->addMultiApp(electron_type, electron_name, electron_params);
    }

    const auto & poisson_type = getParam<std::string>("poisson_multiapp_type");
    auto poisson_params = _factory.getValidParams(poisson_type);
    poisson_params.set<std::vector<FileName>>("input_files") =
        {getParam<FileName>("poisson_input_file")};
    poisson_params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_END;
    poisson_params.set<Real>("relaxation_factor") = getParam<Real>("relaxation_factor");
    poisson_params.set<std::vector<std::string>>("transformed_variables") =
        getParam<std::vector<std::string>>("poisson_transformed_variables");
    poisson_params.set<bool>("no_restore") = getParam<bool>("no_restore");

    _problem->addMultiApp(poisson_type, poisson_name, poisson_params);
  }
  else if (_current_task == "add_transfer")
  {
    const auto & e_src =
        getParam<std::vector<VariableName>>("electron_to_poisson_source_variables");
    const auto & e_dst =
        getParam<std::vector<AuxVariableName>>("electron_to_poisson_variables");
    const auto & p_src =
        getParam<std::vector<VariableName>>("poisson_to_electron_source_variables");
    const auto & p_dst =
        getParam<std::vector<AuxVariableName>>("poisson_to_electron_variables");
    const auto & parent_e_src =
        getParam<std::vector<VariableName>>("parent_to_electron_source_variables");
    const auto & parent_e_dst =
        getParam<std::vector<AuxVariableName>>("parent_to_electron_variables");
    const auto & e_parent_src =
        getParam<std::vector<VariableName>>("electron_to_parent_source_variables");
    const auto & e_parent_dst =
        getParam<std::vector<AuxVariableName>>("electron_to_parent_variables");
    const auto & parent_p_src =
        getParam<std::vector<VariableName>>("parent_to_poisson_source_variables");
    const auto & parent_p_dst =
        getParam<std::vector<AuxVariableName>>("parent_to_poisson_variables");
    const auto & p_parent_src =
        getParam<std::vector<VariableName>>("poisson_to_parent_source_variables");
    const auto & p_parent_dst =
        getParam<std::vector<AuxVariableName>>("poisson_to_parent_variables");

    if (usesElectronSubApp())
    {
      const auto & electron_name = getParam<MultiAppName>("electron_multiapp");
      const bool potential_through_parent =
          getParam<MooseEnum>("potential_transfer_mode") == "through_parent";

      if (potential_through_parent)
      {
        const auto & parent_potential =
            getParam<AuxVariableName>("parent_potential_variable");

        auto to_electron = _factory.getValidParams("MultiAppCopyTransfer");
        to_electron.set<MultiAppName>("to_multi_app") = electron_name;
        to_electron.set<std::vector<VariableName>>("source_variable") =
            {VariableName(parent_potential)};
        to_electron.set<std::vector<AuxVariableName>>("variable") =
            {getParam<AuxVariableName>("electron_potential_variable")};
        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_shared_phi_parent_to_electron",
                              to_electron);

        auto from_poisson = _factory.getValidParams("MultiAppCopyTransfer");
        from_poisson.set<MultiAppName>("from_multi_app") = poisson_name;
        from_poisson.set<std::vector<VariableName>>("source_variable") =
            {getParam<VariableName>("poisson_potential_variable")};
        from_poisson.set<std::vector<AuxVariableName>>("variable") =
            {parent_potential};
        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_shared_phi_poisson_to_parent",
                              from_poisson);
      }

      for (std::size_t i = 0; i < parent_e_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("to_multi_app") = electron_name;
        params.set<std::vector<VariableName>>("source_variable") = {parent_e_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {parent_e_dst[i]};
        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_parent_to_electron_" + std::to_string(i),
                              params);
      }

      for (std::size_t i = 0; i < e_parent_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = electron_name;
        params.set<std::vector<VariableName>>("source_variable") = {e_parent_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {e_parent_dst[i]};
        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_electron_to_parent_" + std::to_string(i),
                              params);
      }

      for (std::size_t i = 0; i < parent_p_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("to_multi_app") = poisson_name;
        params.set<std::vector<VariableName>>("source_variable") = {parent_p_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {parent_p_dst[i]};
        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_parent_to_poisson_" + std::to_string(i),
                              params);
      }

      for (std::size_t i = 0; i < p_parent_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = poisson_name;
        params.set<std::vector<VariableName>>("source_variable") = {p_parent_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {p_parent_dst[i]};
        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_poisson_to_parent_" + std::to_string(i),
                              params);
      }

      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = electron_name;
        params.set<MultiAppName>("to_multi_app") = poisson_name;
        params.set<std::vector<VariableName>>("source_variable") =
            {getParam<VariableName>("electron_density_variable")};
        params.set<std::vector<AuxVariableName>>("variable") =
            {getParam<AuxVariableName>("poisson_electron_density_variable")};

        _problem->addTransfer(
            "MultiAppCopyTransfer", object_prefix + "_shared_n_e", params);
      }

      for (std::size_t i = 0; i < e_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = electron_name;
        params.set<MultiAppName>("to_multi_app") = poisson_name;
        params.set<std::vector<VariableName>>("source_variable") = {e_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {e_dst[i]};

        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_electron_to_poisson_" + std::to_string(i),
                              params);
      }

      if (!potential_through_parent)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = poisson_name;
        params.set<MultiAppName>("to_multi_app") = electron_name;
        params.set<std::vector<VariableName>>("source_variable") =
            {getParam<VariableName>("poisson_potential_variable")};
        params.set<std::vector<AuxVariableName>>("variable") =
            {getParam<AuxVariableName>("electron_potential_variable")};

        _problem->addTransfer(
            "MultiAppCopyTransfer", object_prefix + "_shared_phi", params);
      }

      for (std::size_t i = 0; i < p_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = poisson_name;
        params.set<MultiAppName>("to_multi_app") = electron_name;
        params.set<std::vector<VariableName>>("source_variable") = {p_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {p_dst[i]};

        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_poisson_to_electron_" + std::to_string(i),
                              params);
      }
    }
    else
    {
      for (std::size_t i = 0; i < e_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("to_multi_app") = poisson_name;
        params.set<std::vector<VariableName>>("source_variable") = {e_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {e_dst[i]};

        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_to_poisson_" + std::to_string(i),
                              params);
      }

      for (std::size_t i = 0; i < p_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = poisson_name;
        params.set<std::vector<VariableName>>("source_variable") = {p_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {p_dst[i]};

        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_from_poisson_" + std::to_string(i),
                              params);
      }
    }
  }
  else if (_current_task == "add_convergence" && getParam<bool>("manage_convergence"))
  {
    const auto & convergence_name = getParam<ConvergenceName>("convergence_name");
    auto params = _factory.getValidParams("DeltaPhiMultiAppConvergence");
    params.set<PostprocessorName>("delta_phi_pp") =
        getParam<PostprocessorName>("delta_phi_postprocessor");
    params.set<Real>("delta_phi_abs_tol") = getParam<Real>("delta_phi_abs_tol");

    _problem->addConvergence("DeltaPhiMultiAppConvergence", convergence_name, params);
  }
}
