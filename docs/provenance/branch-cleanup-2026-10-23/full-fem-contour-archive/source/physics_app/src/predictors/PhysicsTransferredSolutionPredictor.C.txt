#include "PhysicsTransferredSolutionPredictor.h"

#include "FEProblemBase.h"
#include "MooseMesh.h"
#include "MooseVariableFieldBase.h"
#include "SystemBase.h"

#include "libmesh/elem.h"
#include "libmesh/numeric_vector.h"

#include <algorithm>
#include <cmath>
#include <limits>

registerMooseObject("PhysicsApp", PhysicsTransferredSolutionPredictor);

InputParameters
PhysicsTransferredSolutionPredictor::validParams()
{
  auto params = Predictor::validParams();
  params.addClassDescription(
      "Copies same-mesh auxiliary snapshot fields into selected nonlinear variables immediately "
      "before a nonlinear solve, providing an external Newton initial guess without changing "
      "the transient old solution state.");
  params.addRequiredParam<std::vector<VariableName>>(
      "source_variables", "Auxiliary variables containing the externally supplied guess.");
  params.addRequiredParam<std::vector<VariableName>>(
      "target_variables", "Nonlinear variables whose current solution is initialized.");
  return params;
}

PhysicsTransferredSolutionPredictor::PhysicsTransferredSolutionPredictor(
    const InputParameters & parameters)
  : Predictor(parameters),
    _source_variables(getParam<std::vector<VariableName>>("source_variables")),
    _target_variables(getParam<std::vector<VariableName>>("target_variables")),
    _last_applied_time(declareRestartableData<Real>(
        "last_applied_time", std::numeric_limits<Real>::quiet_NaN()))
{
  if (_source_variables.size() != _target_variables.size())
    paramError("target_variables",
               "source_variables and target_variables must contain the same number of entries.");
}

bool
PhysicsTransferredSolutionPredictor::shouldApply()
{
  if (!Predictor::shouldApply())
    return false;

  // A fast block can re-solve the same physical time several times during its
  // internal Gummel/fixed-point loop. Apply the external predictor only once at
  // each physical target time so later corrections keep their latest iterate.
  if (std::isfinite(_last_applied_time))
  {
    const Real scale = std::max<Real>({1.0, std::abs(_last_applied_time), std::abs(_fe_problem.time())});
    if (std::abs(_last_applied_time - _fe_problem.time()) <= 1.0e-14 * scale)
      return false;
  }

  return true;
}

void
PhysicsTransferredSolutionPredictor::apply(NumericVector<Number> & sln)
{
  _console << " Applying transferred-solution predictor with scale factor = " << _scale << std::endl;

  for (const auto i : index_range(_source_variables))
  {
    auto & source = _fe_problem.getVariable(0,
                                            _source_variables[i],
                                            Moose::VarKindType::VAR_AUXILIARY,
                                            Moose::VarFieldType::VAR_FIELD_ANY);
    auto & target = _fe_problem.getVariable(0,
                                            _target_variables[i],
                                            Moose::VarKindType::VAR_SOLVER,
                                            Moose::VarFieldType::VAR_FIELD_ANY);

    if (source.feType() != target.feType())
      paramError("source_variables",
                 "Source variable '",
                 _source_variables[i],
                 "' and target variable '",
                 _target_variables[i],
                 "' must have identical FE/FV discretizations.");

    const auto * source_solution = source.sys().currentSolution();
    if (!source_solution)
      mooseError("No current solution is available for predictor source variable '",
                 _source_variables[i],
                 "'.");

    std::vector<dof_id_type> source_dofs;
    std::vector<dof_id_type> target_dofs;

    for (const auto * elem : _fe_problem.mesh().getMesh().active_local_element_ptr_range())
    {
      source_dofs.clear();
      target_dofs.clear();
      source.getDofIndices(elem, source_dofs);
      target.getDofIndices(elem, target_dofs);

      if (source_dofs.empty() && target_dofs.empty())
        continue;

      if (source_dofs.size() != target_dofs.size())
        mooseError("Predictor source/target DOF mismatch for variables '",
                   _source_variables[i],
                   "' and '",
                   _target_variables[i],
                   "' on element ",
                   elem->id(),
                   ".");

      for (const auto j : index_range(source_dofs))
      {
        const Number predicted = (*source_solution)(source_dofs[j]);
        const Number current = sln(target_dofs[j]);
        sln.set(target_dofs[j], (1.0 - _scale) * current + _scale * predicted);
      }
    }
  }

  sln.close();
  _last_applied_time = _fe_problem.time();
}
