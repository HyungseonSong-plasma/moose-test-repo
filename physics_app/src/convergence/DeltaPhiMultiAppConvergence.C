#include "DeltaPhiMultiAppConvergence.h"

#include "FixedPointSolve.h"

#include <cmath>

registerMooseObject("PhysicsApp", DeltaPhiMultiAppConvergence);

InputParameters
DeltaPhiMultiAppConvergence::validParams()
{
  auto params = DefaultMultiAppFixedPointConvergence::validParams();
  params.addClassDescription(
      "Gummel MultiApp convergence based on max potential-iterate change. "
      "The raw MOOSE fixed-point residual norm is disabled by default because it "
      "is dimensional and changes under physically equivalent variable rescaling.");

  // Gummel convergence should be invariant to the units/scaling of electron equations.
  params.set<bool>("disable_fixed_point_residual_norm_check") = true;
  params.set<bool>("fixed_point_force_norms") = false;

  params.addRequiredParam<PostprocessorName>(
      "delta_phi_pp",
      "Postprocessor containing max absolute potential change between the current and entering "
      "fixed-point iterates.");
  params.addRequiredRangeCheckedParam<Real>(
      "delta_phi_abs_tol", "delta_phi_abs_tol>0", "Absolute potential-iterate tolerance [V].");
  return params;
}

DeltaPhiMultiAppConvergence::DeltaPhiMultiAppConvergence(
    const InputParameters & parameters)
  : DefaultMultiAppFixedPointConvergence(parameters),
    _delta_phi(getPostprocessorValue("delta_phi_pp")),
    _delta_phi_abs_tol(getParam<Real>("delta_phi_abs_tol"))
{
}

Convergence::MooseConvergenceStatus
DeltaPhiMultiAppConvergence::checkConvergence(unsigned int n_iter)
{
  if (!std::isfinite(_delta_phi))
    mooseError("Non-finite delta-phi convergence metric: ", _delta_phi);

  _console << "Gummel max delta-phi = " << std::scientific << _delta_phi
           << " V (tol = " << _delta_phi_abs_tol << " V)" << std::endl;

  // Explicit opt-in compatibility path: retain the historical AND criterion.
  if (_has_fixed_point_norm)
  {
    const auto standard = DefaultMultiAppFixedPointConvergence::checkConvergence(n_iter);

    if (standard != MooseConvergenceStatus::CONVERGED)
      return standard;

    if (_delta_phi <= _delta_phi_abs_tol)
      return MooseConvergenceStatus::CONVERGED;

    _fp_solve.setFixedPointStatus(
        FixedPointSolve::MooseFixedPointConvergenceReason::CONVERGED_NONLINEAR);
    return MooseConvergenceStatus::ITERATING;
  }

  // Preferred Gummel criterion: convergence of the coupling variable itself.
  if (n_iter >= _min_fixed_point_its && _delta_phi <= _delta_phi_abs_tol)
  {
    _fp_solve.setFixedPointStatus(
        FixedPointSolve::MooseFixedPointConvergenceReason::CONVERGED_OBJECT);
    return MooseConvergenceStatus::CONVERGED;
  }

  if (n_iter == _max_fixed_point_its)
  {
    if (_accept_max_it)
    {
      _fp_solve.setFixedPointStatus(
          FixedPointSolve::MooseFixedPointConvergenceReason::REACH_MAX_ITS);
      return MooseConvergenceStatus::CONVERGED;
    }

    _fp_solve.setFixedPointStatus(
        FixedPointSolve::MooseFixedPointConvergenceReason::DIVERGED_MAX_ITS);
    return MooseConvergenceStatus::DIVERGED;
  }

  _fp_solve.setFixedPointStatus(
      FixedPointSolve::MooseFixedPointConvergenceReason::CONVERGED_NONLINEAR);
  return MooseConvergenceStatus::ITERATING;
}
