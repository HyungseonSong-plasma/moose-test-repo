#include "PhysicsDeltaPhiMultiAppConvergence.h"

#include "FixedPointSolve.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsDeltaPhiMultiAppConvergence);

InputParameters
PhysicsDeltaPhiMultiAppConvergence::validParams()
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
  return params;
}

PhysicsDeltaPhiMultiAppConvergence::PhysicsDeltaPhiMultiAppConvergence(
    const InputParameters & parameters)
  : DefaultMultiAppFixedPointConvergence(parameters),
    _delta_phi(getPostprocessorValue("delta_phi_pp")),
    _delta_phi_abs_tol(getParam<Real>("delta_phi_abs_tol"))
{
}

Convergence::MooseConvergenceStatus
PhysicsDeltaPhiMultiAppConvergence::checkConvergence(unsigned int n_iter)
{
  const auto standard = DefaultMultiAppFixedPointConvergence::checkConvergence(n_iter);

  if (standard != MooseConvergenceStatus::CONVERGED)
    return standard;

  if (!std::isfinite(_delta_phi))
    mooseError("Non-finite delta-phi convergence metric: ", _delta_phi);

  if (_delta_phi <= _delta_phi_abs_tol)
    return MooseConvergenceStatus::CONVERGED;

  // The default residual criterion is satisfied but the coupling variable is not.
  // Continue the fixed-point loop and mark the reason as not-yet-assessed so the
  // final printed status is not misleading.
  _fp_solve.setFixedPointStatus(FixedPointSolve::MooseFixedPointConvergenceReason::CONVERGED_NONLINEAR);
  return MooseConvergenceStatus::ITERATING;
}
