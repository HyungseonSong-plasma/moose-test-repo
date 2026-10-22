#include "PhysicsLowerDSurfaceCurrentProbeAux.h"

#include "FEProblemBase.h"
#include "FaceInfo.h"
#include "FVUtils.h"
#include "MooseMesh.h"
#include "MooseFunctorArguments.h"

registerMooseObject("PhysicsApp", PhysicsLowerDSurfaceCurrentProbeAux);

InputParameters
PhysicsLowerDSurfaceCurrentProbeAux::validParams()
{
  auto params = AuxKernel::validParams();
  params.addClassDescription(
      "Diagnostic: stores the signed surface-current functor on each lower-D face "
      "using exactly the same plasma-side FaceArg as PhysicsLowerDSurfaceCurrent.");
  params.addRequiredParam<MooseFunctorName>("surface_current_density", "Higher-D plasma-side signed face current [A/m^2].");
  return params;
}

PhysicsLowerDSurfaceCurrentProbeAux::PhysicsLowerDSurfaceCurrentProbeAux(const InputParameters & parameters)
  : AuxKernel(parameters),
    _surface_current_density(getFunctor<ADReal>("surface_current_density"))
{
}

Real
PhysicsLowerDSurfaceCurrentProbeAux::computeValue()
{
  const Elem * const parent = _current_elem->interior_parent();
  if (!parent)
    mooseError(name(), ": lower-D element has no interior_parent: ", _current_elem->id());
  const unsigned int side = _mesh.getHigherDSide(_current_elem);
  if (side == libMesh::invalid_uint)
    mooseError(name(), ": invalid higher-dimensional side.");

  const Elem * const neighbor = parent->neighbor_ptr(side);
  const FaceInfo * fi = (!neighbor || Moose::FV::elemHasFaceInfo(*parent, neighbor))
                            ? _mesh.faceInfo(parent, side)
                            : _mesh.faceInfo(neighbor, neighbor->which_neighbor_am_i(parent));
  if (!fi)
    mooseError(name(), ": no face info available.");

  const bool on_elem = _surface_current_density.hasFaceSide(*fi, true);
  const bool on_neighbor = _surface_current_density.hasFaceSide(*fi, false);
  if (on_elem == on_neighbor)
    mooseError(name(), ": expected exactly one plasma-side owner (on_elem=",
               on_elem, " on_neighbor=", on_neighbor, ").");

  const Elem * const face_side = on_elem ? fi->elemPtr() : fi->neighborPtr();
  if (!face_side)
    mooseError(name(), ": null face_side.");

  const Moose::FaceArg face_arg = {
      fi, Moose::FV::LimiterType::CentralDifference,
      /* elem_is_upwind = */ true,
      /* correct_skewness = */ false,
      face_side, /* state_limiter = */ nullptr};

  return MetaPhysicL::raw_value(_surface_current_density(face_arg, Moose::currentState()));
}
