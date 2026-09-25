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
      "Builds a model-agnostic Gummel coupling between the electron subsystem in the current "
      "application and a Poisson sub-application. Electron equations are supplied independently.");

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
      "Disable restore between fixed-point iterations so the Poisson solve retains its current "
      "iterate.");
  params.addRangeCheckedParam<Real>(
      "relaxation_factor",
      1.0,
      "relaxation_factor>0 & relaxation_factor<2",
      "Relaxation factor applied to the Poisson MultiApp transformed variables.");
  params.addParam<std::vector<std::string>>(
      "poisson_transformed_variables",
      {},
      "Poisson sub-application variables transformed by the MOOSE fixed-point algorithm.");

  params.addParam<std::vector<VariableName>>(
      "electron_state_variables",
      {},
      "Electron state advanced by the current application. This declaration is descriptive: "
      "the Action does not assume drift-diffusion, momentum, or energy equations.");

  params.addRequiredParam<std::vector<VariableName>>(
      "electron_to_poisson_source_variables",
      "Variables in the electron subsystem copied to the Poisson sub-application.");
  params.addRequiredParam<std::vector<AuxVariableName>>(
      "electron_to_poisson_variables",
      "Target variables in the Poisson sub-application corresponding one-to-one with "
      "electron_to_poisson_source_variables.");
  params.addRequiredParam<std::vector<VariableName>>(
      "poisson_to_electron_source_variables",
      "Variables in the Poisson sub-application copied back to the electron subsystem.");
  params.addRequiredParam<std::vector<AuxVariableName>>(
      "poisson_to_electron_variables",
      "Target variables in the electron subsystem corresponding one-to-one with "
      "poisson_to_electron_source_variables.");

  params.addParam<bool>(
      "manage_convergence",
      true,
      "Create and select a DeltaPhiMultiAppConvergence object for this Gummel iteration.");
  params.addParam<PostprocessorName>(
      "delta_phi_postprocessor",
      "Postprocessor containing the maximum potential change for the current fixed-point iterate.");
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

  if (e_src.empty())
    paramError("electron_to_poisson_source_variables",
               "At least one electron-to-Poisson variable mapping is required.");
  if (p_src.empty())
    paramError("poisson_to_electron_source_variables",
               "At least one Poisson-to-electron variable mapping is required.");
  if (e_src.size() != e_dst.size())
    paramError("electron_to_poisson_variables",
               "The electron-to-Poisson source and target lists must have the same length.");
  if (p_src.size() != p_dst.size())
    paramError("poisson_to_electron_variables",
               "The Poisson-to-electron source and target lists must have the same length.");
}

void
GummelIterationAction::act()
{
  const auto & multiapp_name = getParam<MultiAppName>("poisson_multiapp");
  const std::string object_prefix = std::string(multiapp_name) + "_gummel";

  if (_current_task == "add_multi_app")
  {
    const auto & multiapp_type = getParam<std::string>("poisson_multiapp_type");
    auto params = _factory.getValidParams(multiapp_type);
    params.set<std::vector<FileName>>("input_files") = {getParam<FileName>("poisson_input_file")};
    params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_END;
    params.set<Real>("relaxation_factor") = getParam<Real>("relaxation_factor");
    params.set<std::vector<std::string>>("transformed_variables") =
        getParam<std::vector<std::string>>("poisson_transformed_variables");
    params.set<bool>("no_restore") = getParam<bool>("no_restore");

    _problem->addMultiApp(multiapp_type, multiapp_name, params);
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

    for (std::size_t i = 0; i < e_src.size(); ++i)
    {
      auto params = _factory.getValidParams("MultiAppCopyTransfer");
      params.set<MultiAppName>("to_multi_app") = multiapp_name;
      params.set<std::vector<VariableName>>("source_variable") = {e_src[i]};
      params.set<std::vector<AuxVariableName>>("variable") = {e_dst[i]};

      _problem->addTransfer("MultiAppCopyTransfer",
                            object_prefix + "_to_poisson_" + std::to_string(i),
                            params);
    }

    for (std::size_t i = 0; i < p_src.size(); ++i)
    {
      auto params = _factory.getValidParams("MultiAppCopyTransfer");
      params.set<MultiAppName>("from_multi_app") = multiapp_name;
      params.set<std::vector<VariableName>>("source_variable") = {p_src[i]};
      params.set<std::vector<AuxVariableName>>("variable") = {p_dst[i]};

      _problem->addTransfer("MultiAppCopyTransfer",
                            object_prefix + "_from_poisson_" + std::to_string(i),
                            params);
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
    _problem->setMultiAppFixedPointConvergenceName(convergence_name);
  }
}
