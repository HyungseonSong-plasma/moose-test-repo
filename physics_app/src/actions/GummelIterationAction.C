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
      "Builds a model-agnostic Gummel coupling. In two-sub-application mode the parent "
      "application owns orchestration only, while sibling electron and Poisson MultiApps exchange "
      "n_e and phi directly. Legacy current-application electron coupling remains supported.");

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
      "coordinator_to_electron_source_variables",
      {},
      "Current coordinator variables copied into the electron sibling before its solve.");
  params.addParam<std::vector<AuxVariableName>>(
      "coordinator_to_electron_variables",
      {},
      "Electron auxiliary targets corresponding one-to-one with "
      "coordinator_to_electron_source_variables.");
  params.addParam<std::vector<VariableName>>(
      "coordinator_to_poisson_source_variables",
      {},
      "Current coordinator variables copied into the Poisson sibling before its solve.");
  params.addParam<std::vector<AuxVariableName>>(
      "coordinator_to_poisson_variables",
      {},
      "Poisson auxiliary targets corresponding one-to-one with "
      "coordinator_to_poisson_source_variables.");
  params.addParam<std::vector<VariableName>>(
      "electron_to_coordinator_source_variables",
      {},
      "Electron sibling variables copied back to the coordinator after fixed-point convergence.");
  params.addParam<std::vector<AuxVariableName>>(
      "electron_to_coordinator_variables",
      {},
      "Coordinator auxiliary targets corresponding one-to-one with "
      "electron_to_coordinator_source_variables.");
  params.addParam<std::vector<VariableName>>(
      "poisson_to_coordinator_source_variables",
      {},
      "Poisson sibling variables copied back to the coordinator after fixed-point convergence.");
  params.addParam<std::vector<AuxVariableName>>(
      "poisson_to_coordinator_variables",
      {},
      "Coordinator auxiliary targets corresponding one-to-one with "
      "poisson_to_coordinator_source_variables.");

  params.addParam<bool>(
      "manage_convergence",
      true,
      "Create a DeltaPhiMultiAppConvergence object for this Gummel iteration. The parent "
      "Executioner must select it with multiapp_fixed_point_convergence.");
  params.addParam<PostprocessorName>(
      "delta_phi_postprocessor",
      "Maximum potential-change postprocessor. In legacy mode it lives in the current "
      "application; in sibling mode it lives in the Poisson sub-application.");
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

  const auto & c2e_src =
      getParam<std::vector<VariableName>>("coordinator_to_electron_source_variables");
  const auto & c2e_dst =
      getParam<std::vector<AuxVariableName>>("coordinator_to_electron_variables");
  const auto & c2p_src =
      getParam<std::vector<VariableName>>("coordinator_to_poisson_source_variables");
  const auto & c2p_dst =
      getParam<std::vector<AuxVariableName>>("coordinator_to_poisson_variables");
  const auto & e2c_src =
      getParam<std::vector<VariableName>>("electron_to_coordinator_source_variables");
  const auto & e2c_dst =
      getParam<std::vector<AuxVariableName>>("electron_to_coordinator_variables");
  const auto & p2c_src =
      getParam<std::vector<VariableName>>("poisson_to_coordinator_source_variables");
  const auto & p2c_dst =
      getParam<std::vector<AuxVariableName>>("poisson_to_coordinator_variables");

  if (e_src.size() != e_dst.size())
    paramError("electron_to_poisson_variables",
               "The electron-to-Poisson source and target lists must have the same length.");
  if (p_src.size() != p_dst.size())
    paramError("poisson_to_electron_variables",
               "The Poisson-to-electron source and target lists must have the same length.");

  if (c2e_src.size() != c2e_dst.size())
    paramError("coordinator_to_electron_variables",
               "The coordinator-to-electron source and target lists must have the same length.");
  if (c2p_src.size() != c2p_dst.size())
    paramError("coordinator_to_poisson_variables",
               "The coordinator-to-Poisson source and target lists must have the same length.");
  if (e2c_src.size() != e2c_dst.size())
    paramError("electron_to_coordinator_variables",
               "The electron-to-coordinator source and target lists must have the same length.");
  if (p2c_src.size() != p2c_dst.size())
    paramError("poisson_to_coordinator_variables",
               "The Poisson-to-coordinator source and target lists must have the same length.");

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

    const auto & c2e_src =
        getParam<std::vector<VariableName>>("coordinator_to_electron_source_variables");
    const auto & c2e_dst =
        getParam<std::vector<AuxVariableName>>("coordinator_to_electron_variables");
    const auto & c2p_src =
        getParam<std::vector<VariableName>>("coordinator_to_poisson_source_variables");
    const auto & c2p_dst =
        getParam<std::vector<AuxVariableName>>("coordinator_to_poisson_variables");
    const auto & e2c_src =
        getParam<std::vector<VariableName>>("electron_to_coordinator_source_variables");
    const auto & e2c_dst =
        getParam<std::vector<AuxVariableName>>("electron_to_coordinator_variables");
    const auto & p2c_src =
        getParam<std::vector<VariableName>>("poisson_to_coordinator_source_variables");
    const auto & p2c_dst =
        getParam<std::vector<AuxVariableName>>("poisson_to_coordinator_variables");

    if (usesElectronSubApp())
    {
      const auto & electron_name = getParam<MultiAppName>("electron_multiapp");

      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = electron_name;
        params.set<MultiAppName>("to_multi_app") = poisson_name;
        params.set<std::vector<VariableName>>("source_variable") =
            {getParam<VariableName>("electron_density_variable")};
        params.set<std::vector<AuxVariableName>>("variable") =
            {getParam<AuxVariableName>("poisson_electron_density_variable")};
        params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_END;

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
        params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_END;

        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_electron_to_poisson_" + std::to_string(i),
                              params);
      }

      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = poisson_name;
        params.set<MultiAppName>("to_multi_app") = electron_name;
        params.set<std::vector<VariableName>>("source_variable") =
            {getParam<VariableName>("poisson_potential_variable")};
        params.set<std::vector<AuxVariableName>>("variable") =
            {getParam<AuxVariableName>("electron_potential_variable")};
        params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_BEGIN;

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
        params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_BEGIN;

        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_poisson_to_electron_" + std::to_string(i),
                              params);
      }

      for (std::size_t i = 0; i < c2e_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("to_multi_app") = electron_name;
        params.set<std::vector<VariableName>>("source_variable") = {c2e_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {c2e_dst[i]};
        params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_BEGIN;

        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_coordinator_to_electron_" + std::to_string(i),
                              params);
      }

      for (std::size_t i = 0; i < c2p_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("to_multi_app") = poisson_name;
        params.set<std::vector<VariableName>>("source_variable") = {c2p_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {c2p_dst[i]};
        params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_END;

        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_coordinator_to_poisson_" + std::to_string(i),
                              params);
      }

      for (std::size_t i = 0; i < e2c_src.size(); ++i)
      {
        auto params = _factory.getValidParams("MultiAppCopyTransfer");
        params.set<MultiAppName>("from_multi_app") = electron_name;
        params.set<std::vector<VariableName>>("source_variable") = {e2c_src[i]};
        params.set<std::vector<AuxVariableName>>("variable") = {e2c_dst[i]};
        params.set<ExecFlagEnum>("execute_on") = EXEC_MULTIAPP_FIXED_POINT_END;

        _problem->addTransfer("MultiAppCopyTransfer",
                              object_prefix + "_electron_to_coordinator_" + std::to_string(i),
                              params);
      }

      for (std::size_t i = 0; i < p2c_src.size(); ++i)
      {
        auto begin_params = _factory.getValidParams("MultiAppCopyTransfer");
        begin_params.set<MultiAppName>("from_multi_app") = poisson_name;
        begin_params.set<std::vector<VariableName>>("source_variable") = {p2c_src[i]};
        begin_params.set<std::vector<AuxVariableName>>("variable") = {p2c_dst[i]};
        begin_params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_BEGIN;

        _problem->addTransfer(
            "MultiAppCopyTransfer",
            object_prefix + "_poisson_to_coordinator_begin_" + std::to_string(i),
            begin_params);

        auto final_params = _factory.getValidParams("MultiAppCopyTransfer");
        final_params.set<MultiAppName>("from_multi_app") = poisson_name;
        final_params.set<std::vector<VariableName>>("source_variable") = {p2c_src[i]};
        final_params.set<std::vector<AuxVariableName>>("variable") = {p2c_dst[i]};
        final_params.set<ExecFlagEnum>("execute_on") = EXEC_MULTIAPP_FIXED_POINT_END;

        _problem->addTransfer(
            "MultiAppCopyTransfer",
            object_prefix + "_poisson_to_coordinator_final_" + std::to_string(i),
            final_params);
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
    if (usesElectronSubApp())
    {
      params.set<MultiAppName>("delta_phi_multiapp") = poisson_name;
      params.set<PostprocessorName>("delta_phi_subapp_pp") =
          getParam<PostprocessorName>("delta_phi_postprocessor");
    }
    else
      params.set<PostprocessorName>("delta_phi_pp") =
          getParam<PostprocessorName>("delta_phi_postprocessor");

    params.set<Real>("delta_phi_abs_tol") = getParam<Real>("delta_phi_abs_tol");

    _problem->addConvergence("DeltaPhiMultiAppConvergence", convergence_name, params);
  }
}
