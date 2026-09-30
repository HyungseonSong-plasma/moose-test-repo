#include "FVElectronResponseTopologyCorrection.h"

#include "libmesh/elem.h"

#include <array>
#include <limits>
#include <unordered_set>
#include <utility>
#include <vector>

registerMooseObject("PhysicsApp", FVElectronResponseTopologyCorrection);

InputParameters
FVElectronResponseTopologyCorrection::validParams()
{
  auto params = FVElementalKernel::validParams();
  params.addClassDescription(
      "Applies a row-sum-preserving graph-shell or directional-band "
      "electron-potential response correction to a multidimensional FV Poisson residual.");
  params.addRequiredParam<MooseFunctorName>(
      "anchor", "Frozen reference potential phi_anchor [V].");
  params.addRequiredParam<MooseFunctorName>(
      "beta", "Local electron susceptibility scale (e/eps0)*n_e/VTe [1/m^2].");
  params.addParam<Real>(
      "strength", 1.0, "Dimensionless multiplier for the normalized response correction.");
  params.addParam<unsigned int>(
      "graph_radius", 1, "Maximum graph/path distance included in the response stencil.");
  params.addParam<std::vector<Real>>(
      "shell_weights",
      std::vector<Real>{1.0},
      "Positive per-distance weights for distances 1..graph_radius; normalized internally.");
  params.addParam<bool>(
      "directional_band",
      false,
      "Use four directed +/-radial and +/-axial face-neighbor paths instead of full graph shells.");
  params.addParam<unsigned int>(
      "radial_component", 0, "Cartesian coordinate component used as the RZ radial direction.");
  params.addParam<unsigned int>(
      "axial_component", 1, "Cartesian coordinate component used as the RZ axial direction.");
  params.addParam<Real>(
      "directional_cosine_min",
      0.25,
      "Minimum directional cosine required when selecting the next face neighbor.");
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
    _shell_weights(getParam<std::vector<Real>>("shell_weights")),
    _directional_band(getParam<bool>("directional_band")),
    _radial_component(getParam<unsigned int>("radial_component")),
    _axial_component(getParam<unsigned int>("axial_component")),
    _directional_cosine_min(getParam<Real>("directional_cosine_min"))
{
  if (_strength <= 0.0)
    paramError("strength", "strength must be positive.");
  if (_graph_radius == 0 || _graph_radius > 5)
    paramError("graph_radius", "graph_radius must lie in [1, 5].");
  if (_shell_weights.size() != _graph_radius)
    paramError("shell_weights", "shell_weights must contain exactly graph_radius entries.");
  if (getParam<unsigned short>("ghost_layers") < _graph_radius + 1)
    paramError("ghost_layers", "ghost_layers must be at least graph_radius+1.");
  if (_radial_component == _axial_component)
    paramError("axial_component", "radial_component and axial_component must differ.");
  if (_directional_cosine_min <= 0.0 || _directional_cosine_min > 1.0)
    paramError("directional_cosine_min", "directional_cosine_min must lie in (0, 1].");

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

const Elem *
FVElectronResponseTopologyCorrection::directionalNeighbor(
    const Elem * elem, const unsigned int component, const int sign) const
{
  const Point origin = elem->vertex_average();
  const Elem * best = nullptr;
  Real best_cosine = _directional_cosine_min;
  Real best_distance = std::numeric_limits<Real>::max();

  for (unsigned int side = 0; side < elem->n_sides(); ++side)
  {
    const Elem * candidate = elem->neighbor_ptr(side);
    if (!candidate || !candidate->active())
      continue;

    const Point delta = candidate->vertex_average() - origin;
    const Real distance = delta.norm();
    if (distance <= 0.0)
      continue;

    const Real directed_projection = static_cast<Real>(sign) * delta(component);
    if (directed_projection <= 0.0)
      continue;

    const Real cosine = directed_projection / distance;
    if (cosine > best_cosine ||
        (cosine == best_cosine && distance < best_distance))
    {
      best = candidate;
      best_cosine = cosine;
      best_distance = distance;
    }
  }

  return best;
}

ADReal
FVElectronResponseTopologyCorrection::computeQpResidual()
{
  const auto state = determineState();
  const Moose::ElemArg current_arg{_current_elem, false};
  const ADReal delta_i = _var(current_arg, state) - _anchor(current_arg, state);

  ADReal response = 0.0;

  if (_directional_band)
  {
    struct DirectionPath
    {
      const Elem * elem;
      unsigned int component;
      int sign;
    };

    std::array<DirectionPath, 4> paths{{
        {_current_elem, _radial_component, +1},
        {_current_elem, _radial_component, -1},
        {_current_elem, _axial_component, +1},
        {_current_elem, _axial_component, -1},
    }};

    for (unsigned int shell = 0; shell < _graph_radius; ++shell)
    {
      std::unordered_set<const Elem *> shell_elems;
      for (auto & path : paths)
      {
        if (!path.elem)
          continue;
        path.elem = directionalNeighbor(path.elem, path.component, path.sign);
        if (path.elem)
          shell_elems.insert(path.elem);
      }

      if (shell_elems.empty())
        break;

      ADReal shell_sum = 0.0;
      for (const Elem * elem : shell_elems)
      {
        const Moose::ElemArg shell_arg{elem, false};
        shell_sum += _var(shell_arg, state) - _anchor(shell_arg, state);
      }

      const ADReal shell_mean = shell_sum / static_cast<Real>(shell_elems.size());
      response += _shell_weights[shell] * (delta_i - shell_mean);
    }
  }
  else
  {
    std::unordered_set<const Elem *> visited;
    visited.insert(_current_elem);
    std::vector<const Elem *> frontier{_current_elem};

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
  }

  return _beta(current_arg, state) * _strength * response;
}
