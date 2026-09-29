#include "FVElectronResponseTopologyCorrection.h"

#include "libmesh/elem.h"

registerMooseObject("PhysicsApp", FVElectronResponseTopologyCorrection);

InputParameters
FVElectronResponseTopologyCorrection::validParams()
{
  auto params = FVElementalKernel::validParams();
  params.addClassDescription(
      "Applies a row-sum-preserving face-neighbor electron-potential response "
      "correction to a multidimensional FV Poisson residual.");
  params.addRequiredParam<MooseFunctorName>(
      "anchor", "Frozen reference potential phi_anchor [V].");
  params.addRequiredParam<MooseFunctorName>(
      "beta", "Local electron susceptibility scale (e/eps0)*n_e/VTe [1/m^2].");
  params.addParam<Real>(
      "strength", 1.0, "Dimensionless strength multiplying the normalized one-ring stencil.");
  params.set<unsigned short>("ghost_layers") = 2;
  return params;
}

FVElectronResponseTopologyCorrection::FVElectronResponseTopologyCorrection(
    const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _anchor(getFunctor<ADReal>("anchor")),
    _beta(getFunctor<ADReal>("beta")),
    _strength(getParam<Real>("strength"))
{
  if (_strength <= 0.0)
    paramError("strength", "strength must be positive.");
}

ADReal
FVElectronResponseTopologyCorrection::computeQpResidual()
{
  const auto state = determineState();
  const Moose::ElemArg current_arg{_current_elem, false};
  const ADReal delta_i = _var(current_arg, state) - _anchor(current_arg, state);

  ADReal neighbor_sum = 0.0;
  unsigned int neighbor_count = 0;
  for (unsigned int side = 0; side < _current_elem->n_sides(); ++side)
  {
    const Elem * neighbor = _current_elem->neighbor_ptr(side);
    if (!neighbor || !neighbor->active())
      continue;

    const Moose::ElemArg neighbor_arg{neighbor, false};
    neighbor_sum += _var(neighbor_arg, state) - _anchor(neighbor_arg, state);
    ++neighbor_count;
  }

  // A disconnected/single-cell domain has no nonlocal response to add.
  if (neighbor_count == 0)
    return 0.0;

  const ADReal neighbor_mean = neighbor_sum / static_cast<Real>(neighbor_count);
  return _beta(current_arg, state) * _strength * (delta_i - neighbor_mean);
}
