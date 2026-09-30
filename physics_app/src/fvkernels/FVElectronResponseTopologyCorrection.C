#include "FVElectronResponseTopologyCorrection.h"

#include "libmesh/elem.h"

#include <numeric>
#include <unordered_set>
#include <utility>
#include <vector>

registerMooseObject("PhysicsApp", FVElectronResponseTopologyCorrection);

InputParameters
FVElectronResponseTopologyCorrection::validParams()
{
  auto params = FVElementalKernel::validParams();
  params.addClassDescription(
      "Applies a row-sum-preserving graph-shell electron-potential response "
      "correction to a multidimensional FV Poisson residual.");
  params.addRequiredParam<MooseFunctorName>(
      "anchor", "Frozen reference potential phi_anchor [V].");
  params.addRequiredParam<MooseFunctorName>(
      "beta", "Local electron susceptibility scale (e/eps0)*n_e/VTe [1/m^2].");
  params.addParam<Real>(
      "strength", 1.0, "Dimensionless multiplier for the normalized graph-shell response.");
  params.addParam<unsigned int>(
      "graph_radius", 1, "Maximum exact face-graph distance included in the response stencil.");
  params.addParam<std::vector<Real>>(
      "shell_weights",
      std::vector<Real>{1.0},
      "Positive per-shell weights for graph distances 1..graph_radius; normalized internally.");
  params.set<unsigned short>("ghost_layers") = 6;
  return params;
}

FVElectronResponseTopologyCorrection::FVElectronResponseTopologyCorrection(
    const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _anchor(getFunctor<ADReal>("anchor")),
    _beta(getFunctor<ADReal>("beta")),
    _strength(getParam<Real>("strength")),
    _graph_radius(getParam<unsigned int>("graph_radius")),
    _shell_weights(getParam<std::vector<Real>>("shell_weights"))
{
  if (_strength <= 0.0)
    paramError("strength", "strength must be positive.");
  if (_graph_radius == 0 || _graph_radius > 5)
    paramError("graph_radius", "graph_radius must lie in [1, 5].");
  if (_shell_weights.size() != _graph_radius)
    paramError("shell_weights", "shell_weights must contain exactly graph_radius entries.");
  if (getParam<unsigned short>("ghost_layers") < _graph_radius + 1)
    paramError("ghost_layers", "ghost_layers must be at least graph_radius+1.");

  Real weight_sum = 0.0;
  for (const Real weight : _shell_weights)
  {
    if (weight <= 0.0)
      paramError("shell_weights", "every shell weight must be positive.");
    weight_sum += weight;
  }
  for (Real & weight : _shell_weights)
    weight /= weight_sum;
}

ADReal
FVElectronResponseTopologyCorrection::computeQpResidual()
{
  const auto state = determineState();
  const Moose::ElemArg current_arg{_current_elem, false};
  const ADReal delta_i = _var(current_arg, state) - _anchor(current_arg, state);

  std::unordered_set<const Elem *> visited;
  visited.insert(_current_elem);
  std::vector<const Elem *> frontier{_current_elem};

  ADReal response = 0.0;
  for (unsigned int shell = 0; shell < _graph_radius; ++shell)
  {
    std::vector<const Elem *> next_frontier;
    for (const Elem * elem : frontier)
      for (unsigned int side = 0; side < elem->n_sides(); ++side)
      {
        const Elem * neighbor = elem->neighbor_ptr(side);
        if (!neighbor || !neighbor->active())
          continue;
        if (visited.insert(neighbor).second)
          next_frontier.push_back(neighbor);
      }

    if (next_frontier.empty())
      break;

    ADReal shell_sum = 0.0;
    for (const Elem * elem : next_frontier)
    {
      const Moose::ElemArg shell_arg{elem, false};
      shell_sum += _var(shell_arg, state) - _anchor(shell_arg, state);
    }

    const ADReal shell_mean =
        shell_sum / static_cast<Real>(next_frontier.size());
    response += _shell_weights[shell] * (delta_i - shell_mean);
    frontier = std::move(next_frontier);
  }

  return _beta(current_arg, state) * _strength * response;
}
