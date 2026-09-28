#include "DeltaPhiMultiAppConvergence.h"

#include "FEProblemBase.h"
#include "FixedPointSolve.h"
#include "MultiApp.h"

#include <cmath>
#include <limits>

registerMooseObject("PhysicsApp", DeltaPhiMultiAppConvergence);

InputParameters
DeltaPhiMultiAppConvergence::validParams()
{
  auto params = DefaultMultiAppFixedPointConvergence::validParams();
  params.addClassDescription(
      "Default MultiApp fixed-point convergence augmented with an AND condition on "
      "a maximum potential-iterate change postprocessor. The delta-phi postprocessor "
      "may live in the current application or in a named sibling MultiApp.");

  params.addParam<PostprocessorName>(
      "delta_phi_pp",
      "Current-application postprocessor containing max absolute potential change "
      "between the current and entering fixed-point iterates.");

  params.addParam<MultiAppName>(
      "delta_phi_multiapp",
      "Optional MultiApp that owns the delta-phi postprocessor.");
  params.addParam<PostprocessorName>(
      "delta_phi_subapp_pp",
      "Postprocessor in delta_phi_multiapp containing max absolute potential change.");

  params.addRequiredRangeCheckedParam<Real>(
      "delta_phi_abs_tol", "delta_phi_abs_tol>0", "Absolute potential-iterate tolerance [V].");
  return params;
}

DeltaPhiMultiAppConvergence::DeltaPhiMultiAppConvergence(
    const InputParameters & parameters)
  : DefaultMultiAppFixedPointConvergence(parameters),
    _delta_phi(isParamValid("delta_phi_pp") ? &getPostprocessorValue("delta_phi_pp") : nullptr),
    _delta_phi_multiapp(
        isParamValid("delta_phi_multiapp")
            ? _fe_problem.getMultiApp(getParam<MultiAppName>("delta_phi_multiapp"))
            : nullptr),
    _delta_phi_subapp_pp(
        isParamValid("delta_phi_subapp_pp")
            ? std::string(getParam<PostprocessorName>("delta_phi_subapp_pp"))
            : std::string()),
    _delta_phi_abs_tol(getParam<Real>("delta_phi_abs_tol"))
{
  const bool local_mode = _delta_phi != nullptr;
  const bool subapp_name = isParamValid("delta_phi_multiapp");
  const bool subapp_pp = isParamValid("delta_phi_subapp_pp");

  if (subapp_name != subapp_pp)
    mooseError(
        "DeltaPhiMultiAppConvergence requires both delta_phi_multiapp and "
        "delta_phi_subapp_pp when reading the convergence metric from a sub-application.");

  if (local_mode == subapp_name)
    mooseError(
        "DeltaPhiMultiAppConvergence requires exactly one delta-phi source: either "
        "delta_phi_pp in the current application, or delta_phi_multiapp plus "
        "delta_phi_subapp_pp.");
}

Real
DeltaPhiMultiAppConvergence::deltaPhi() const
{
  if (_delta_phi)
    return *_delta_phi;

  if (!_delta_phi_multiapp)
    mooseError("DeltaPhiMultiAppConvergence has no delta-phi source.");

  if (_delta_phi_multiapp->numGlobalApps() != 1)
    mooseError(
        "DeltaPhiMultiAppConvergence sibling mode currently requires exactly one "
        "delta-phi sub-application. Got ",
        _delta_phi_multiapp->numGlobalApps(),
        ".");

  Real value = -std::numeric_limits<Real>::max();
  if (_delta_phi_multiapp->hasLocalApp(0))
    value = _delta_phi_multiapp->appProblemBase(0).getPostprocessorValueByName(
        _delta_phi_subapp_pp);

  _communicator.max(value);

  if (value == -std::numeric_limits<Real>::max())
    mooseError(
        "DeltaPhiMultiAppConvergence could not read postprocessor '",
        _delta_phi_subapp_pp,
        "' from MultiApp '",
        _delta_phi_multiapp->name(),
        "'.");

  return value;
}

Convergence::MooseConvergenceStatus
DeltaPhiMultiAppConvergence::checkConvergence(unsigned int n_iter)
{
  const auto standard = DefaultMultiAppFixedPointConvergence::checkConvergence(n_iter);

  if (standard != MooseConvergenceStatus::CONVERGED)
    return standard;

  const Real delta_phi = deltaPhi();

  if (!std::isfinite(delta_phi))
    mooseError("Non-finite delta-phi convergence metric: ", delta_phi);

  if (delta_phi <= _delta_phi_abs_tol)
    return MooseConvergenceStatus::CONVERGED;

  // The default residual criterion is satisfied but the coupling variable is not.
  // Continue the fixed-point loop and mark the reason as not-yet-assessed so the
  // final printed status is not misleading.
  _fp_solve.setFixedPointStatus(
      FixedPointSolve::MooseFixedPointConvergenceReason::CONVERGED_NONLINEAR);
  return MooseConvergenceStatus::ITERATING;
}
