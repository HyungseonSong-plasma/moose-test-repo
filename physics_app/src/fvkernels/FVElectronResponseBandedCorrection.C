#include "FVElectronResponseBandedCorrection.h"

#include "libmesh/elem.h"

#include <algorithm>
#include <cmath>
#include <limits>

registerMooseObject("PhysicsApp", FVElectronResponseBandedCorrection);

InputParameters
FVElectronResponseBandedCorrection::validParams()
{
  auto params = FVElementalKernel::validParams();
  params.addClassDescription(
      "Applies a nonlocal row-sum-preserving banded electron-potential Jacobian "
      "correction to the FV Poisson residual.");
  params.addRequiredParam<MooseFunctorName>(
      "anchor", "Frozen reference potential phi_anchor [V].");
  params.addRequiredParam<MooseFunctorName>(
      "beta", "Local electron susceptibility scale (e/eps0)*n_e/VTe [1/m^2].");
  params.addRequiredParam<std::vector<Real>>(
      "matrix", "Row-major dimensionless banded response matrix W.");
  params.addRequiredParam<unsigned int>("n_cells", "Number of 1D FV cells represented by W.");
  params.addRequiredParam<unsigned int>("bandwidth", "Half-bandwidth of W.");
  params.addRequiredParam<Real>("xmin", "Left edge of the 1D diagnostic mesh [m].");
  params.addRequiredParam<Real>("dx", "Uniform cell width of the 1D diagnostic mesh [m].");
  params.set<unsigned short>("ghost_layers") = 6;
  return params;
}

FVElectronResponseBandedCorrection::FVElectronResponseBandedCorrection(
    const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _anchor(getFunctor<ADReal>("anchor")),
    _beta(getFunctor<ADReal>("beta")),
    _matrix(getParam<std::vector<Real>>("matrix")),
    _n_cells(getParam<unsigned int>("n_cells")),
    _bandwidth(getParam<unsigned int>("bandwidth")),
    _xmin(getParam<Real>("xmin")),
    _dx(getParam<Real>("dx"))
{
  if (_n_cells == 0)
    paramError("n_cells", "n_cells must be positive.");
  if (_dx <= 0.0)
    paramError("dx", "dx must be positive.");
  if (_bandwidth == 0 || _bandwidth >= _n_cells)
    paramError("bandwidth", "bandwidth must lie in [1, n_cells-1].");
  if (_matrix.size() != static_cast<std::size_t>(_n_cells) * _n_cells)
    paramError("matrix", "matrix must contain exactly n_cells*n_cells entries.");
  if (getParam<unsigned short>("ghost_layers") < _bandwidth + 1)
    paramError("ghost_layers", "ghost_layers must be at least bandwidth+1.");
}

unsigned int
FVElectronResponseBandedCorrection::rowIndex(const Elem * const elem) const
{
  const Real x = elem->vertex_average()(0);
  const long idx = std::lround((x - _xmin) / _dx - 0.5);
  if (idx < 0 || idx >= static_cast<long>(_n_cells))
    mooseError("FVElectronResponseBandedCorrection: element centroid x=", x,
               " is outside the configured 1D row map.");
  return static_cast<unsigned int>(idx);
}

const Elem *
FVElectronResponseBandedCorrection::offsetElem(const Elem * start, const int offset) const
{
  if (!offset)
    return start;

  const int direction = offset > 0 ? 1 : -1;
  const Elem * elem = start;

  for (unsigned int step = 0; step < static_cast<unsigned int>(std::abs(offset)); ++step)
  {
    const Real x = elem->vertex_average()(0);
    const Elem * next = nullptr;
    Real best_distance = std::numeric_limits<Real>::max();

    for (unsigned int side = 0; side < elem->n_sides(); ++side)
    {
      const Elem * candidate = elem->neighbor_ptr(side);
      if (!candidate)
        continue;

      const Real dx = candidate->vertex_average()(0) - x;
      if ((direction > 0 && dx <= 0.0) || (direction < 0 && dx >= 0.0))
        continue;

      const Real distance = std::abs(dx);
      if (distance < best_distance)
      {
        best_distance = distance;
        next = candidate;
      }
    }

    if (!next)
      return nullptr;
    elem = next;
  }

  return elem;
}

ADReal
FVElectronResponseBandedCorrection::computeQpResidual()
{
  const auto state = determineState();
  const unsigned int i = rowIndex(_current_elem);
  const Moose::ElemArg current_arg{_current_elem, false};
  const ADReal beta_i = _beta(current_arg, state);

  ADReal response = 0.0;
  const int lo = std::max(0, static_cast<int>(i) - static_cast<int>(_bandwidth));
  const int hi = std::min(static_cast<int>(_n_cells) - 1,
                          static_cast<int>(i) + static_cast<int>(_bandwidth));

  for (int j = lo; j <= hi; ++j)
  {
    const Real w = _matrix[static_cast<std::size_t>(i) * _n_cells + j];
    if (w == 0.0)
      continue;

    const Elem * elem_j = offsetElem(_current_elem, j - static_cast<int>(i));
    if (!elem_j)
      mooseError("FVElectronResponseBandedCorrection: missing ghosted element for row ",
                 i, " column ", j, ".");

    const Moose::ElemArg arg_j{elem_j, false};
    response += w * (_var(arg_j, state) - _anchor(arg_j, state));
  }

  return beta_i * response;
}
