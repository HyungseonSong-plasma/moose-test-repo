#include "DeltaPhiMultiAppConvergence.h"

#include "FixedPointSolve.h"
#include "FEProblemBase.h"
#include "MultiApp.h"
#include "MultiAppTransfer.h"

#include <cmath>
#include <limits>

registerMooseObject("PhysicsApp", DeltaPhiMultiAppConvergence);

InputParameters
DeltaPhiMultiAppConvergence::validParams()
{
  auto params = DefaultMultiAppFixedPointConvergence::validParams();
  params.addClassDescription(
      "Default MultiApp fixed-point convergence augmented with an AND condition on "
      "a maximum potential-iterate change postprocessor.");
  params.addRequiredParam<PostprocessorName>(
      "delta_phi_pp",
      "Postprocessor containing max absolute potential change between the current and entering "
      "fixed-point iterates.");
  params.addRequiredRangeCheckedParam<Real>(
      "delta_phi_abs_tol", "delta_phi_abs_tol>0", "Absolute potential-iterate tolerance [V].");
  params.addParam<MultiAppName>(
      "residual_multiapp",
      "Optional child MultiApp whose FEProblem residual replaces the parent residual for the "
      "standard fixed-point convergence check. This is used by solve=false Gummel drivers.");
  return params;
}

DeltaPhiMultiAppConvergence::DeltaPhiMultiAppConvergence(
    const InputParameters & parameters)
  : DefaultMultiAppFixedPointConvergence(parameters),
    _delta_phi(getPostprocessorValue("delta_phi_pp")),
    _delta_phi_abs_tol(getParam<Real>("delta_phi_abs_tol")),
    _use_residual_multiapp(isParamValid("residual_multiapp")),
    _residual_multiapp_name(_use_residual_multiapp ? getParam<MultiAppName>("residual_multiapp")
                                                   : MultiAppName()),
    _child_residual_previous(std::numeric_limits<Real>::max())
{
}

Real
DeltaPhiMultiAppConvergence::residualMultiAppNorm()
{
  auto multi_app = _fe_problem.getMultiApp(_residual_multiapp_name);
  if (!multi_app)
    mooseError("Unable to find residual MultiApp '", _residual_multiapp_name, "'.");

  if (multi_app->numGlobalApps() != 1)
    mooseError("residual_multiapp requires exactly one child application; '",
               _residual_multiapp_name,
               "' has ",
               multi_app->numGlobalApps(),
               ".");

  Real residual = 0.0;
  if (multi_app->hasLocalApp(0))
    residual = multi_app->appProblemBase(0).computeResidualL2Norm();

  _communicator.max(residual);
  return residual;
}

void
DeltaPhiMultiAppConvergence::initialize()
{
  if (!_use_residual_multiapp)
  {
    DefaultMultiAppFixedPointConvergence::initialize();
    return;
  }

  Convergence::initialize();

  _fixed_point_timestep_begin_norm.assign(_max_fixed_point_its, 0.0);
  _fixed_point_timestep_end_norm.assign(_max_fixed_point_its, 0.0);
  _pp_history.str("");

  // Match the qualified fast-owner initial residual state. The outer heavy
  // snapshot is already present in this driver, but its child-directed
  // TIMESTEP_BEGIN transfers have not run yet when convergence initializes.
  _fe_problem.execMultiAppTransfers(EXEC_TIMESTEP_BEGIN, MultiAppTransfer::TO_MULTIAPP);
  _fixed_point_initial_norm = residualMultiAppNorm();
  _child_residual_previous = std::numeric_limits<Real>::max();

  _console << COLOR_MAGENTA << "Initial delegated fixed point residual norm: " << COLOR_DEFAULT
           << std::scientific << _fixed_point_initial_norm << COLOR_DEFAULT << "\n" << std::endl;
}

void
DeltaPhiMultiAppConvergence::preExecute()
{
  if (!_use_residual_multiapp)
    DefaultMultiAppFixedPointConvergence::preExecute();
}

Convergence::MooseConvergenceStatus
DeltaPhiMultiAppConvergence::checkConvergence(unsigned int n_iter)
{
  if (!_use_residual_multiapp)
  {
    const auto standard = DefaultMultiAppFixedPointConvergence::checkConvergence(n_iter);

    if (standard != MooseConvergenceStatus::CONVERGED)
      return standard;

    if (!std::isfinite(_delta_phi))
      mooseError("Non-finite delta-phi convergence metric: ", _delta_phi);

    if (_delta_phi <= _delta_phi_abs_tol)
      return MooseConvergenceStatus::CONVERGED;

    _fp_solve.setFixedPointStatus(
        FixedPointSolve::MooseFixedPointConvergenceReason::CONVERGED_NONLINEAR);
    return MooseConvergenceStatus::ITERATING;
  }

  // The driver itself is solve=false, so its nonlinear residual is identically zero.
  // Before evaluating the delegated electron residual, synchronize the raw potential
  // just returned by Poisson into the electron child. This reproduces the qualified
  // fast-owner residual: electron equations evaluated at the new Poisson iterate.
  _fe_problem.execMultiAppTransfers(EXEC_MULTIAPP_FIXED_POINT_CONVERGENCE,
                                    MultiAppTransfer::TO_MULTIAPP);

  const auto iter = n_iter - 1;
  const Real residual = residualMultiAppNorm();
  if (!std::isfinite(residual))
    mooseError("Non-finite delegated fixed-point residual: ", residual);

  _fixed_point_timestep_end_norm[iter] = residual;
  outputResidualNorm("DELEGATED_ELECTRON", _child_residual_previous, residual);
  _child_residual_previous = residual;

  if (!std::isfinite(_delta_phi))
    mooseError("Non-finite delta-phi convergence metric: ", _delta_phi);

  if (n_iter >= _min_fixed_point_its)
  {
    const bool converged_abs = residual < _fixed_point_abs_tol;
    const bool converged_rel =
        _fixed_point_initial_norm > 0.0 &&
        residual / _fixed_point_initial_norm < _fixed_point_rel_tol;

    if ((converged_abs || converged_rel) && _delta_phi <= _delta_phi_abs_tol)
    {
      _fp_solve.setFixedPointStatus(
          converged_abs ? FixedPointSolve::MooseFixedPointConvergenceReason::CONVERGED_ABS
                        : FixedPointSolve::MooseFixedPointConvergenceReason::CONVERGED_RELATIVE);
      return MooseConvergenceStatus::CONVERGED;
    }

    if (converged_abs || converged_rel)
      _fp_solve.setFixedPointStatus(
          FixedPointSolve::MooseFixedPointConvergenceReason::CONVERGED_NONLINEAR);
  }

  if (n_iter == _max_fixed_point_its)
  {
    if (_accept_max_it && _delta_phi <= _delta_phi_abs_tol)
    {
      _fp_solve.setFixedPointStatus(
          FixedPointSolve::MooseFixedPointConvergenceReason::REACH_MAX_ITS);
      return MooseConvergenceStatus::CONVERGED;
    }

    _fp_solve.setFixedPointStatus(
        FixedPointSolve::MooseFixedPointConvergenceReason::DIVERGED_MAX_ITS);
    return MooseConvergenceStatus::DIVERGED;
  }

  return MooseConvergenceStatus::ITERATING;
}
